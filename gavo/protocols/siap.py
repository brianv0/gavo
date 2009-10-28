"""
Generic support for querying for areas, SIAP-style.

See develNotes for info on our SIAP implementation
"""

import math
import urllib

import numpy

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo.base import coords
from gavo.protocols import products
from gavo.protocols import simbadinterface


MS = base.makeStruct


class BboxSIAPRMixin(rscdef.RMixinBase):
	"""A table mixin for simple support of SIAP.

	This currently only handles two-dimensional images.

	The columns added into the tables include

	* (certain) FITS WCS headers 
	* the primaryBbox, secondaryBbox, centerAlpha and centerDelta, nAxes, 
	  pixelSize, pixelScale, imageFormat, wcs* fields calculated by the 
	  computeBboxSIAPFields macro.   
	* imageTitle (interpolateString should come in handy for these)
	* instId -- some id for the instrument used
	* dateObs -- a timestamp of the "characteristic" observation time
	* the bandpass* values.  You're on your own with them...
	* the values of the product interface.  
	* mimetype -- the mime type of the product.

	(their definition is in the siap system RD)

	Tables mixin in bboxSIAP can be used for bbox-based SIAP querying and
	automatically mix in `the products mixin`_.

	To feed these tables, use the computeBboxSIAP and setSIAPMeta predefined 
	procs.  Since you are dealing with products, you will also need the
	defineProduct predefined rowgen in your grammar.
	"""
	name = "bboxSIAP"
	
	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/siap", "bboxSIAPcolumns")

	def processLate(self, tableDef):
		rscdef.getMixin("products").processLate(tableDef)

_mixin = BboxSIAPRMixin()
rscdef.registerRMixin(_mixin)

def getBboxFromSIAPPars(raDec, sizes, applyCosD=True):
	"""returns a bounding box in decimal ra and dec for the siap parameters
	raDec and sizes.

	If applyCosD is true, the size in alpha will be multiplied by cos(delta).
	SIAP mandates this behaviour, but for unit tests it is more confusing
	than helpful.

	>>> getBboxFromSIAPPars((40, 60), (2, 3), applyCosD=False)
	Box((41,61.5), (39,58.5))
	>>> getBboxFromSIAPPars((0, 0), (2, 3))
	Box((1,1.5), (-1,-1.5))
	"""
	alpha, delta = raDec
	sizeAlpha, sizeDelta = sizes
	if applyCosD:
		cosD = math.cos(base.degToRad(delta))
		if cosD<1e-10:
			# People can't mean that
			cosD = 1
		sizeAlpha = sizeAlpha*cosD
	if abs(delta)>89:
		return coords.Box(0, 360, coords.clampDelta(delta-sizeDelta/2.), 
			coords.clampDelta(delta+sizeDelta/2.))
	return coords.Box(
		alpha-sizeAlpha/2., alpha+sizeAlpha/2,
		coords.clampDelta(delta-sizeDelta/2.), 
		coords.clampDelta(delta+sizeDelta/2.))


def normalizeBox(bbox):
	"""returns bbox with the left corner x between 0 and 360.
	"""
	if 0<=bbox.x0<360:
		return bbox
	newx0 = coords.clampAlpha(bbox.x0)
	return bbox.translate((newx0-bbox.x0, 0))


def splitCrossingBox(bbox):
	"""splits bboxes crossing the stitch line.

	The function returns bbox, None if the bbox doesn't cross the stitch line,
	leftBox, rightBox otherwise.

	>>> splitCrossingBox(coords.Box(10, 12, -30, 30))
	(Box((12,30), (10,-30)), None)
	>>> splitCrossingBox(coords.Box(-23, 12, -30, 0))
	(Box((360,0), (337,-30)), Box((12,0), (0,-30)))
	>>> splitCrossingBox(coords.Box(300, 400, 0, 30))
	(Box((360,30), (300,0)), Box((40,30), (0,0)))
	"""
	bbox = normalizeBox(bbox)
	if bbox.x1<0 or bbox.x0>360:
		leftBox = coords.Box((coords.clampAlpha(bbox.x1), bbox.y0), (360, bbox.y1))
		rightBox = coords.Box((0, bbox.y0), (coords.clampAlpha(bbox.x0), bbox.y1))
	else:
		leftBox, rightBox = bbox, None
	return leftBox, rightBox


# XXX TODO: Maybe rework this to make it use vizierexprs.getSQLKey?
# (caution: that would mess up many unit tests...)
_intersectQueries = {
	"COVERS": "primaryBbox ~ %(<p>roiPrimary)s AND (secondaryBbox IS NULL OR"
	  " secondaryBbox ~ %(<p>roiSecondary)s)",
	"ENCLOSED": "%(<p>roiPrimary)s ~ primaryBbox AND"
		" (%(<p>roiSecondary)s IS NULL OR %(<p>roiSecondary)s ~ secondaryBbox)",
	"CENTER": "point '(%(<p>roiAlpha)s,%(<p>roiDelta)s)' @ primaryBbox OR"
		" point '(%(<p>roiAlpha)s,%(<p>roiDelta)s)' @ secondaryBbox",
	None: "(primaryBbox && %(<p>roiPrimary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiSecondary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiPrimary)s) OR" 
		" (%(<p>roiSecondary)s IS NOT NULL AND %(<p>roiSecondary)s && primaryBbox)",
	"OVERLAPS": "(primaryBbox && %(<p>roiPrimary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiSecondary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiPrimary)s) OR" 
		" (%(<p>roiSecondary)s IS NOT NULL AND %(<p>roiSecondary)s && primaryBbox)",
	}


def getBboxQueryFromBbox(intersect, bbox, center, prefix, sqlPars):
	bboxes = splitCrossingBox(bbox)
	sqlPars.update({prefix+"roiPrimary": bboxes[0], 
		prefix+"roiSecondary": bboxes[1],
		prefix+"roiAlpha": center[0],
		prefix+"roiDelta": center[1],})
	return _intersectQueries[intersect].replace("<p>", prefix) 


def dissectPositions(posStr):
	"""tries to infer RA and DEC from posStr.

	In contrast to base.parseCooPair, we are quite strict here and just
	try to cope with some bad clients that leave out the comma.
	"""
	try:
		ra, dec = map(float, posStr.split(","))
	except ValueError: # maybe a sign as separator?
		if '+' in posStr:
			ra, dec = map(float, posStr.split("+"))
		elif '-' in posStr:
			ra, dec = map(float, posStr.split("-"))
		else:
			raise ValueError("No pos")
	return ra, dec


def getBboxQuery(parameters, sqlPars, prefix="sia"):
	"""returns an SQL fragment for a SIAP query for bboxes.

	The SQL is returned as a WHERE-fragment in a string.  The parameters
	are added in the sqlPars dictionary.

	parameters is a dictionary that maps the SIAP keywords to the
	values in the query.  Parameters not defined by SIAP are ignored.
	"""
	posStr = urllib.unquote(parameters["POS"])
	try:
		ra, dec = dissectPositions(posStr)
	except (ValueError, TypeError):
		try:
			ra, dec = simbadinterface.getSimbadPositions(posStr)
		except KeyError:
			raise base.ValidationError("%s is neither a RA,DEC pair nor a simbad"
				" resolvable object"%posStr, "POS", posStr)
	try:
		sizes = map(float, parameters["SIZE"].split(","))
	except ValueError:
		raise base.ValidationError("Size specification has to be <degs> or"
			" <degs>,<degs>", "SIZE", parameters["SIZE"])
	if len(sizes)==1:
		sizes = sizes*2
	bbox = getBboxFromSIAPPars((ra, dec), sizes)
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	query = getBboxQueryFromBbox(intersect, bbox, (ra, dec), prefix, sqlPars)
	# the following are for the benefit of cutout queries.
	sqlPars["_ra"], sqlPars["_dec"] = ra, dec
	sqlPars["_sra"], sqlPars["_sdec"] = sizes
	return query


class SIAPCore(svcs.DBCore):
	"""A core doing SIAP queries.

	The main difference to a plain DB core is that we start off with
	the basic SIAP fields in the query result and a SIAP Condition in
	the condDescs.
	"""
	name_ = "siapCore"

	# columns required in our query
	copiedCols = ["centerAlpha", "centerDelta", "imageTitle", "instId",
		"dateObs", "nAxes", "pixelSize", "pixelScale", "imageFormat",
		"refFrame", "wcs_equinox", "wcs_projection", "wcs_refPixel",
		"wcs_refValues", "wcs_cdmatrix", "bandpassId", "bandpassUnit",
		"bandpassHi", "bandpassLo", "pixflags"]

	def __init__(self, parent, **kwargs):
		self.interfaceCols = _mixin.mixinTable.columns
		condDescs = kwargs.setdefault("condDescs", [])
		if "outputTable" in kwargs:
			outputTable = kwargs["outputTable"]
		else:
			outputTable = MS(svcs.OutputTableDef)
			for col in self.interfaceCols:
				outputTable.feedObject("column", svcs.OutputField.fromColumn(col))
		svcs.DBCore.__init__(self, parent, **kwargs)

svcs.registerCore(SIAPCore)


class SIAPCutoutCore(SIAPCore):
	"""A core doing SIAP plus cutouts.
	
	It has, by default, an additional column specifying the desired size of
	the image to be retrieved.  Based on this, the cutout core will tweak
	its output table such that references to cutout images will be retrieved.

	The actual process of cutting out is performed by the product core and
	renderer.
	"""
	name_ = "siapCutoutCore"

	# This should become a property or something once we 
	# compress the stuff or have images with bytes per pixel != 2
	bytesPerPixel = 2

	def __init__(self, parent, **kwargs):
		SIAPCore.__init__(self, parent, **kwargs)

	def getQueryCols(self, service, queryMeta):
		cols = svcs.DBCore.getQueryCols(self, service, queryMeta)
		for name in self.copiedCols:
			cols.append(svcs.OutputField.fromColumn(
				self.interfaceCols.getColumnByName(name)))
		d = self.interfaceCols.getColumnByName("accsize").copy(self)
		d.tablehead = "Est. file size"
		cols.append(svcs.OutputField.fromColumn(d))
		return cols

	def _fixRecord(self, record, centerAlpha, centerDelta, sizeAlpha, sizeDelta):
		"""inserts estimates for WCS values into a cutout record.
		"""
		wcsFields = coords.getWCS({
			"CUNIT1": "deg", "CUNIT2": "deg", "CTYPE1": "-----TAN",
			"CTYPE2": "-----TAN", 
			"CRVAL1": record["wcs_refValues"][0],
			"CRVAL2": record["wcs_refValues"][1],
			"CRPIX1": record["wcs_refPixel"][0],
			"CRPIX2": record["wcs_refPixel"][1],
			"CD1_1": record["wcs_cdmatrix"][0],
			"CD1_2": record["wcs_cdmatrix"][1],
			"CD2_1": record["wcs_cdmatrix"][2],
			"CD2_2": record["wcs_cdmatrix"][3],
			"LONPOLE": "180",
			"NAXIS": record["nAxes"],
			"NAXIS1": record["pixelSize"][0],
			"NAXIS2": record["pixelSize"][1],
		})
		trafo = coords.getWCSTrafo(wcsFields)
		invTrafo = coords.getInvWCSTrafo(wcsFields)
		upperLeft = invTrafo(centerAlpha-sizeAlpha/2, centerDelta-sizeDelta/2)
		lowerRight = invTrafo(centerAlpha+sizeAlpha/2, centerDelta+sizeDelta/2)
		centerPix = invTrafo(centerAlpha, centerDelta)
		record["wcs_refPixel"] = numpy.array([centerPix[0]-lowerRight[0],
			centerPix[1]-lowerRight[1]])
		record["wcs_refValues"] = numpy.array([centerAlpha, centerDelta])
		record["accref"] = products.CutoutProductKey(record["accref"],
			centerAlpha, centerDelta, sizeAlpha, sizeDelta)
		record["centerAlpha"] = centerAlpha
		record["centerDelta"] = centerDelta
		record["accsize"] = int(abs(upperLeft[0]-lowerRight[0]
			)*abs(upperLeft[1]-lowerRight[1])*self.bytesPerPixel)

	def run(self, service, inputData, queryMeta):
		res = svcs.DBCore.run(self, service, inputData, queryMeta)
		sqlPars = queryMeta["sqlQueryPars"]
		if "cutoutSize" in queryMeta.ctxArgs:
			sra = sdec = float(queryMeta.ctxArgs["cutoutSize"])
		else:
			sra, sdec = sqlPars["_sra"], sqlPars["_sdec"]
		cosD = math.cos(sqlPars["_dec"]/180*math.pi)
		if abs(cosD)>1e-5:
			sra = sra/cosD
		else:
			sra = 360
		for record in res:
			self._fixRecord(record, sqlPars["_ra"], sqlPars["_dec"], sra, sdec)
		return res

svcs.registerCore(SIAPCutoutCore)


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
