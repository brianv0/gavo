"""
Generic support for querying for areas, SIAP-style.

See develNotes for info on our SIAP implementation
"""

import math

from gavo import coords
from gavo import simbadinterface
from gavo import utils


def clampAlpha(alpha):
	while alpha>360:
		alpha -= 360
	while alpha<0:
		alpha += 360
	return alpha


def clampDelta(delta):
	return max(-90, min(90, delta))


def getBbox(points):
	"""returns a bounding box for the sequence of 2-sequences points.

	The thing returned is a coords.Box.

	>>> getBbox([(0.25, 1), (-3.75, 1), (-2, 4)])
	Box(((0.25,4), (-3.75,1)))
	"""
	xCoos, yCoos = [[p[i] for p in points] for i in range(2)]
	return coords.Box(min(xCoos), max(xCoos), min(yCoos), max(yCoos))


def getBboxFromSiapPars(raDec, sizes, applyCosD=True):
	"""returns a bounding box in decimal ra and dec for the siap parameters
	raDec and sizes.

	If applyCosD is true, the size in alpha will be multiplied by cos(delta).
	SIAP mandates this behaviour, but for unit tests it is more confusing
	than helpful.

	>>> getBboxFromSiapPars((40, 60), (2, 3), applyCosD=False)
	Box(((41,61.5), (39,58.5)))
	>>> getBboxFromSiapPars((0, 0), (2, 3))
	Box(((1,1.5), (-1,-1.5)))
	"""
	alpha, delta = raDec
	sizeAlpha, sizeDelta = sizes
	if applyCosD:
		cosD = math.cos(utils.degToRad(delta))
		if cosD<1e-10:
			# People can't mean that
			cosD = 1
		sizeAlpha = sizeAlpha*cosD
	return coords.Box(
		alpha-sizeAlpha/2., alpha+sizeAlpha/2,
		clampDelta(delta-sizeDelta/2.), clampDelta(delta+sizeDelta/2.))


_wcsTestDict = {
	"CRVAL1": 0,   "CRVAL2": 0, "CRPIX1": 50,  "CRPIX2": 50,
	"CD1_1": 0.01, "CD1_2": 0, "CD2_1": 0,    "CD2_2": 0.01,
	"NAXIS1": 100, "NAXIS2": 100, "CUNIT1": "deg", "CUNIT2": "deg",
}


def getWCSTrafo(wcsFields):
	"""returns a callable transforming pixel to physical coordinates.

	XXX TODO: This doesn't yet evaluate the projection.
	XXX TODO: This doesn't do anything sensible on the poles.
	"""
	if wcsFields["CUNIT1"].strip()!="deg" or wcsFields["CUNIT2"].strip()!="deg":
		raise Error("Can only handle deg units")

	def ptte(val):
		"""parses an element of the transformation matrix.

		val has the unit degrees/pixel, we return radians/pixel for
		our unit sphere scheme.
		"""
		return float(val)

	alpha, delta = float(wcsFields["CRVAL1"]), float(wcsFields["CRVAL2"])
	refpixX, refpixY = float(wcsFields["CRPIX1"]), float(wcsFields["CRPIX2"])
	caa, cad = ptte(wcsFields["CD1_1"]), ptte(wcsFields["CD1_2"]) 
	cda, cdd = ptte(wcsFields["CD2_1"]), ptte(wcsFields["CD2_2"]) 

	def pixelToSphere(x, y):
		"""returns unit sphere coordinates for pixel coordinates x,y.
		"""
		return (alpha+(x-refpixX)*caa+(y-refpixY)*cad,
			clampDelta(delta+(x-refpixX)*cda+(y-refpixY)*cdd))
	return pixelToSphere


def getCornerPointsFromWCSFields(wcsFields):
	"""returns the corner points of the field defined by (fairly plain)
	WCS values in the dict wcsFields.

	>>> d = _wcsTestDict.copy()
	>>> map(str, getCornerPointsFromWCSFields(d)[0])
	['-0.5', '-0.5']
	>>> d["CRVAL1"] = 50; map(str, getCornerPointsFromWCSFields(d)[0])
	['49.5', '-0.5']
	>>> d["CRVAL2"] = 30; map(str, getCornerPointsFromWCSFields(d)[0])
	['49.5', '29.5']
	"""
	pixelToSphere = getWCSTrafo(wcsFields)
	width, height = float(wcsFields.get("NAXIS1", 2030)), float(
			wcsFields.get("NAXIS2", "800"))
	cornerPoints = [pixelToSphere(0, 0),
		pixelToSphere(0, height), pixelToSphere(width, 0),
		pixelToSphere(width, height)]
	return cornerPoints


def getBboxFromWCSFields(wcsFields):
	"""returns a cartesian bbox and a field center for (fairly simple) WCS
	FITS header fields.
	"""
	return getBbox(getCornerPointsFromWCSFields(wcsFields))


def getCenterFromWCSFields(wcsFields):
	"""returns RA and Dec of the center of an image described by wcsFields.
	"""
	pixelToSphere = getWCSTrafo(wcsFields)
	return pixelToSphere(float(wcsFields.get("NAXIS1", 2030))/2., float(
			wcsFields.get("NAXIS2", "800"))/2.)


def normalizeBox(bbox):
	"""returns bbox with the left corner x between 0 and 360.
	"""
	if 0<=bbox.x0<360:
		return bbox
	newx0 = clampAlpha(bbox.x0)
	return bbox.translate((newx0-bbox.x0, 0))


def splitCrossingBox(bbox):
	"""splits bboxes crossing the stitch line.

	The function returns bbox, None if the bbox doesn't cross the stitch line,
	leftBox, rightBox otherwise.

	>>> splitCrossingBox(coords.Box(10, 12, -30, 30))
	(Box(((12,30), (10,-30))), None)
	>>> splitCrossingBox(coords.Box(-23, 12, -30, 0))
	(Box(((360,0), (337,-30))), Box(((12,0), (0,-30))))
	>>> splitCrossingBox(coords.Box(300, 400, 0, 30))
	(Box(((360,30), (300,0))), Box(((40,30), (0,0))))
	"""
	bbox = normalizeBox(bbox)
	if bbox.x1<0 or bbox.x0>360:
		leftBox = coords.Box((clampAlpha(bbox.x1), bbox.y0), (360, bbox.y1))
		rightBox = coords.Box((0, bbox.y0), (clampAlpha(bbox.x0), bbox.y1))
	else:
		leftBox, rightBox = bbox, None
	return leftBox, rightBox


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
		ra, dec = simbadinterface.getSimbadPositions(parameters["POS"])
	sizes = map(float, parameters["SIZE"].split(","))
	if len(sizes)==1:
		sizes = sizes*2
	bbox = getBboxFromSiapPars((ra, dec), sizes)
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	return getBboxQueryFromBbox(intersect, bbox, (ra, dec), prefix)


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
