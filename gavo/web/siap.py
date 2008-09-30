"""
Generic support for querying for areas, SIAP-style.

See develNotes for info on our SIAP implementation
"""

import math

import numarray

import gavo
from gavo import coords
from gavo import datadef
from gavo import interfaces
from gavo import resourcecache
from gavo import simbadinterface
from gavo import utils
from gavo.parsing import parsehelpers
from gavo.parsing.contextgrammar import InputKey
from gavo.web import core
from gavo.web import vizierexprs
from gavo.web import standardcores


def getBboxFromSiapPars(raDec, sizes, applyCosD=True):
	"""returns a bounding box in decimal ra and dec for the siap parameters
	raDec and sizes.

	If applyCosD is true, the size in alpha will be multiplied by cos(delta).
	SIAP mandates this behaviour, but for unit tests it is more confusing
	than helpful.

	>>> getBboxFromSiapPars((40, 60), (2, 3), applyCosD=False)
	Box((41,61.5), (39,58.5))
	>>> getBboxFromSiapPars((0, 0), (2, 3))
	Box((1,1.5), (-1,-1.5))
	"""
	alpha, delta = raDec
	sizeAlpha, sizeDelta = sizes
	if applyCosD:
		cosD = math.cos(utils.degToRad(delta))
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
# (caution: that unfortunately messes up many unit tests...)
_intersectQueries = {
	"COVERS": "primaryBbox ~ %(<p>roiPrimary)s AND (secondaryBbox IS NULL OR"
	  " secondaryBbox ~ %(<p>roiSecondary)s)",
	"ENCLOSED": "%(<p>roiPrimary)s ~ primaryBbox AND"
		" (%(<p>roiSecondary)s IS NULL OR %(<p>roiSecondary)s ~ secondaryBbox)",
	"CENTER": "point '(%(<p>roiAlpha)s,%(<p>roiDelta)s)' @ primaryBbox OR"
		" point '(%(<p>roiAlpha)s,%(<p>roiDelta)s)' @ secondaryBbox",
	"OVERLAPS": "(primaryBbox && %(<p>roiPrimary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiSecondary)s) OR"
		" (secondaryBbox IS NOT NULL AND secondaryBbox && %(<p>roiPrimary)s) OR" 
		" (%(<p>roiSecondary)s IS NOT NULL AND %(<p>roiSecondary)s && primaryBbox)",
	}


def getBboxQueryFromBbox(intersect, bbox, center, prefix):
	bboxes = splitCrossingBox(bbox)
	return _intersectQueries[intersect].replace("<p>", prefix), {
		prefix+"roiPrimary": bboxes[0], 
		prefix+"roiSecondary": bboxes[1],
		prefix+"roiAlpha": center[0],
		prefix+"roiDelta": center[1],
		}


def getBboxQuery(parameters, prefix="sia"):
	"""returns an SQL fragment for a SIAP query for bboxes.

	The SQL is returned as a WHERE-fragment in a string and a dictionary
	to fill the variables required.

	parameters is a dictionary that maps the SIAP keywords to the
	values in the query.  Parameters not defined by SIAP are ignored.
	"""
	try:
		ra, dec = map(float, parameters["POS"].split(","))
	except (ValueError, TypeError):
		try:
			ra, dec = simbadinterface.getSimbadPositions(parameters["POS"])
		except KeyError:
			raise gavo.ValidationError("%s is neither a RA,DEC pair nor a simbad"
				" resolvable object"%parameters["POS"], "POS")
	try:
		sizes = map(float, parameters["SIZE"].split(","))
	except ValueError:
		raise gavo.ValidationError("Size specification has to be <degs> or"
			" <degs>,<degs>", "SIZE")
	if len(sizes)==1:
		sizes = sizes*2
	bbox = getBboxFromSiapPars((ra, dec), sizes)
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	query, pars = getBboxQueryFromBbox(intersect, bbox, (ra, dec), prefix)
	# the following are for the benefit of cutout queries.
	pars["_ra"], pars["_dec"] = ra, dec
	pars["_sra"], pars["_sdec"] = sizes
	return query, pars


class SiapCondition(standardcores.CondDesc):
	"""is a condition descriptor for a plain SIAP query.
	"""
	def __init__(self, initvals={}):
		vals = {
			"inputKeys": [ 
				InputKey(dest="POS", dbtype="text", unit="deg,deg",
					ucd="pos.eq", description="J2000.0 Position, RA,DEC decimal degrees"
					" (e.g., 234.234,-32.45)", tablehead="Position", optional=False,
					source="POS"),
				InputKey(dest="SIZE", dbtype="text", unit="deg,deg",
					description="Size in decimal degrees"
					" (e.g., 0.2 or 1,0.1)", tablehead="Field size", optional=False,
					source="SIZE"),
				InputKey.fromDataField(datadef.DataField(dest="INTERSECT", 
					dbtype="text", 
					description="Should the image cover, enclose, overlap the ROI or"
					" contain its center?",
					tablehead="Intersection type", default="OVERLAPS", 
					values=datadef.Values(options=["OVERLAPS", "COVERS", "ENCLOSED", 
						"CENTER"]), 
					source="INTERSECT")),
				InputKey(dest="FORMAT", dbtype="text", 
					description="Requested format of the image data",
					tablehead="Output format", default="image/fits",
					values=datadef.Values(options=["image/fits", "METADATA"]),
					widgetFactory='Hidden', source="FORMAT"),
			]}
		vals.update(initvals)
		super(SiapCondition, self).__init__(initvals=vals)
	
	def asSQL(self, inPars, sqlPars):
		if not self.inputReceived(inPars):
			return ""
		fragment, pars = getBboxQuery(inPars)
		sqlPars.update(pars)
		return "(%s) AND imageFormat=%%(%s)s"%(fragment,
			vizierexprs.getSQLKey("imageFormat", inPars["FORMAT"], sqlPars))

core.registerCondDesc("siap", SiapCondition)


class HumanSiapCondition(SiapCondition):
	def __init__(self, initvals={}):
		vals = {
			"inputKeys": [
				InputKey(dest="POS", dbtype="text", unit="deg,deg",
					ucd="pos.eq", description="J2000.0 Position, RA,DEC, or Simbad object"
					" (e.g., 234.234,-32.45)", tablehead="Position", optional=False,
					source="POS"),
				InputKey(dest="SIZE", dbtype="text", unit="deg,deg",
					description="Match size in decimal degrees"
					" (e.g., 0.2 or 1,0.1)", tablehead="Field size", optional=False,
					source="SIZE"),
				InputKey(dest="INTERSECT", 
					dbtype="text", 
					description="Should the image cover, enclose, overlap the ROI or"
					" contain its center?",
					tablehead="Intersection type", default="COVERS", 
					values=datadef.Values(options=["OVERLAPS", "COVERS", "ENCLOSED", 
						"CENTER"]), 
					source="INTERSECT", widgetFactory='Hidden'),
				InputKey(dest="FORMAT", dbtype="text", 
					description="Requested format of the image data",
					tablehead="Output format", default="image/fits",
					values=datadef.Values(options=["image/fits", "METADATA"]),
					widgetFactory='Hidden', source="FORMAT"),
				]}
		vals.update(initvals)
		super(HumanSiapCondition, self).__init__(initvals=vals)

	def asSQL(self, inPars, sqlPars):
		if not self.inputReceived(inPars):
			return ""
		pos = inPars["POS"]
		try:
			ra, dec = parsehelpers.parseCooPair(pos)
		except ValueError:
			data = resourcecache.getSesame("web").query(pos)
			if not data:
				raise gavo.ValidationError("%r is neither a RA,DEC pair nor a simbad"
				" resolvable object"%inPars.get("POS", "Not given"), "POS")
			ra, dec = float(data["RA"]), float(data["dec"])
		return super(HumanSiapCondition, self).asSQL({
			"POS": "%f, %f"%(ra, dec), "SIZE": inPars["SIZE"],
			"INTERSECT": inPars["INTERSECT"], "FORMAT": inPars["FORMAT"]}, sqlPars)

core.registerCondDesc("humanSiap", HumanSiapCondition)


class SiapCutoutCore(standardcores.DbBasedCore):
	"""is a core doing siap and handing through query parameters to
	the product delivery asking it to only retrieve certain portions
	of images.
	"""
	# field keys we need in our DB query
	copiedFields = ["centerAlpha", "centerDelta", "imageTitle", "instId",
		"dateObs", "nAxes", "pixelSize", "pixelScale", "imageFormat",
		"refFrame", "wcs_equinox", "wcs_projection", "wcs_refPixel",
		"wcs_refValues", "wcs_cdmatrix", "bandpassId", "bandpassUnit",
		"bandpassHi", "bandpassLo", "pixflags"]
	# This should become a nodebuilder property or something once we 
	# compress the stuff or have images with bytes per pixel != 2
	bytesPerPixel = 2
	# XXX TODO: this hack suppresses tar output.  Ideally, we'd support
	# tars of cutouts as well.  I guess that's an easy change in producttar,
	# but I'm in a hurry now
	notar = True

	def __init__(self, *args, **kwargs):
		self.interfaceFields = dict([(d.get_dest(), d)
			for d in interfaces.getInterface("bboxSiap").siapFields])
		standardcores.DbBasedCore.__init__(self, *args, **kwargs)

	def getQueryFields(self, queryMeta):
		fields = standardcores.DbBasedCore.getQueryFields(self, queryMeta)
		for name in self.copiedFields:
			fields.append(datadef.OutputField.fromDataField(
				self.interfaceFields[name]))
		d = self.interfaceFields["accref"].copy()
		d.set_displayHint("type=product,nopreview=True")
		fields.append(datadef.OutputField.fromDataField(d))
		d = self.interfaceFields["accsize"].copy()
		d.set_tablehead("Est. file size")
		fields.append(datadef.OutputField.fromDataField(d))
		return fields

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
		record["wcs_refPixel"] = numarray.array([centerPix[0]-lowerRight[0],
			centerPix[1]-lowerRight[1]])
		record["wcs_refValues"] = numarray.array([centerAlpha, centerDelta])
		record["accref"] = record["accref"]+"&ra=%s&dec=%s&sra=%s&sdec=%s"%(
			centerAlpha, centerDelta, sizeAlpha, sizeDelta)
		record["centerAlpha"] = centerAlpha
		record["centerDelta"] = centerDelta
		record["accsize"] = int(abs(upperLeft[0]-lowerRight[0]
			)*abs(upperLeft[1]-lowerRight[1])*self.bytesPerPixel)

	def _parseOutput(self, dbResponse, outputDef, sqlPars, queryMeta):
		if "cutoutSize" in queryMeta.ctxArgs:
			sra = sdec = float(queryMeta.ctxArgs["cutoutSize"][0])
		else:
			sra, sdec = sqlPars["_sra"], sqlPars["_sdec"]
		res = super(SiapCutoutCore, self)._parseOutput(
			dbResponse, outputDef, sqlPars, queryMeta)
		cosD = math.cos(sqlPars["_dec"]/180*math.pi)
		if abs(cosD)>1e-5:
			sra = sra/cosD
		else:
			sra = 360
		for record in res.getPrimaryTable():
			self._fixRecord(record, sqlPars["_ra"], sqlPars["_dec"], sra, sdec)
		return res

core.registerCore("siapcutout", SiapCutoutCore)


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
