"""
Generic support for querying for areas, SIAP-style
"""

import math

from gavo import coords
from gavo import utils


def getBbox(points):
	"""returns a bounding box for the sequence of Vector3 instances points.

	Actually, any 3-sequence would do for a point.  The bbox is
	returned as a 3-sequence [(minx, maxx),...(minz, maxz)].

	>>> getBbox([(0.25, 1, 3), (-3.75, 1, -3), (-2, 1, 2)])
	[(-3.75, 0.25), (1, 1), (-3, 3)]
	"""
	xCoos, yCoos, zCoos = [[p[i] for p in points] for i in range(3)]
	return [
		(min(xCoos), max(xCoos)),
		(min(yCoos), max(yCoos)),
		(min(zCoos), max(zCoos))]


def getCornerPointsFromSiapPars(raDec, sizes, applyCosD=False):
	cPos = coords.computeUnitSphereCoords(*raDec)
	sizeAlpha, sizeDelta = map(utils.degToRad, sizes)
	unitAlpha, unitDelta = coords.getTangentialUnits(cPos)
	if applyCosD:
		unitAlpha = unitAlpha*math.cos(utils.degToRad(raDec[1]))
	cornerPoints = [
		cPos-sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
		cPos+sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
		cPos-sizeAlpha/2*unitAlpha+sizeDelta/2*unitDelta,
		cPos+sizeAlpha/2*unitAlpha+sizeDelta/2*unitDelta
	]
	return cornerPoints, cPos


def getBboxFromSiapPars(raDec, sizes, applyCosD=False):
	"""returns a cartesian bbox and a field center for a position and a size.

	Both parameters are pairs in decimal degrees.

	This uses an "almost-flat" assumption: We compute  normal
	vectors of the tangential plane at raDec and scale them with sizes
	to obtain a candidate rectangle.  The final bounding box is amended
	by adding the intersection points of the four corner vectors with
	the unit sphere.

	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 0), (1, 1))[0]]
	['0.9999, 1.0000', '-0.0087, 0.0087', '-0.0087, 0.0087']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 0), (10, 10))[0]]
	['0.9925, 1.0000', '-0.0873, 0.0873', '-0.0873, 0.0873']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 0), (10, 1))[0]]
	['0.9962, 1.0000', '-0.0873, 0.0873', '-0.0087, 0.0087']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 90), (1, 1))[0]]
	['-0.0087, 0.0087', '-0.0087, 0.0087', '0.9999, 1.0000']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((45, -45), (5, 5))[0]]
	['0.4465, 0.5527', '0.4465, 0.5527', '-0.7380, -0.6750']
	"""
	cornerPoints, cPos = getCornerPointsFromSiapPars(raDec, sizes,
		applyCosD)
	cornerPoints = cornerPoints+[v.normalized() for v in cornerPoints]
	return getBbox(cornerPoints), cPos


def getCornerPointsFromWCSFields(wcsFields):
	if wcsFields["CUNIT1"].strip()!="deg" or wcsFields["CUNIT2"].strip()!="deg":
		raise Error("Can only handle deg units")

	def ptte(val):
		"""parses an element of the transformation matrix.

		val has the unit degrees/pixel, we return radians/pixel for
		our unit sphere scheme.
		"""
		return utils.degToRad(float(val))

	cPos = coords.computeUnitSphereCoords(float(wcsFields["CRVAL1"]),
		float(wcsFields["CRVAL2"]))
	alphaUnit, deltaUnit = coords.getTangentialUnits(cPos)
	refpixX, refpixY = float(wcsFields["CRPIX1"]), float(wcsFields["CRPIX2"])
	caa, cad = ptte(wcsFields["CD1_1"]), ptte(wcsFields["CD1_2"]) 
	cda, cdd = ptte(wcsFields["CD2_1"]), ptte(wcsFields["CD2_2"]) 
	xPixelDirection = caa*alphaUnit+cad*deltaUnit
	yPixelDirection = cda*alphaUnit+cdd*deltaUnit

	def pixelToSphere(x, y):
		"""returns unit sphere coordinates for pixel coordinates x,y.
		"""
		return cPos+(x-refpixX)*xPixelDirection+(y-refpixY)*yPixelDirection

	width, height = float(wcsFields.get("NAXIS1", 2030)), float(
			wcsFields.get("NAXIS2", "800"))
	cornerPoints = [pixelToSphere(0, 0),
		pixelToSphere(0, height), pixelToSphere(width, 0),
		pixelToSphere(width, height)]
	return cornerPoints, pixelToSphere(width/2, height/2)


def getBboxFromWCSFields(wcsFields):
	"""returns a cartesian bbox and a field center for (fairly simple) WCS
	FITS header fields.

	For caveats, see getBboxFromSiapPars.
	"""
	cornerPoints, center = getCornerPointsFromWCSFields(wcsFields)
	cornerPoints = cornerPoints+[v.normalized() for v in cornerPoints]
	return getBbox(cornerPoints), center


_intersectQueries = {
	"COVERS": "bbox_xmin<=%(PREFIXxmin)s AND bbox_xmax>=%(PREFIXxmax)s"
		" AND bbox_ymin<=%(PREFIXymin)s AND bbox_ymax>=%(PREFIXymax)s"
		" AND bbox_zmin<=%(PREFIXzmin)s AND bbox_zmax>=%(PREFIXzmax)s",
	"ENCLOSED": "bbox_xmin>=%(PREFIXxmin)s AND bbox_xmax<=%(PREFIXxmax)s"
		" AND bbox_ymin>=%(PREFIXymin)s AND bbox_ymax<=%(PREFIXymax)s"
		" AND bbox_zmin>=%(PREFIXzmin)s AND bbox_zmax<=%(PREFIXzmax)s",
	"CENTER": "bbox_xmin<=%(PREFIXxcenter)s AND bbox_xmax>=%(PREFIXxcenter)s"
		" AND bbox_ymin<=%(PREFIXycenter)s AND bbox_ymax>=%(PREFIXycenter)s"
		" AND bbox_zmin<=%(PREFIXzcenter)s AND bbox_zmax>=%(PREFIXzcenter)s",
	"OVERLAPS": "NOT (%(PREFIXxmin)s>bbox_xmax OR %(PREFIXxmax)s<bbox_xmin"
		" OR %(PREFIXymin)s>bbox_ymax OR %(PREFIXymax)s<bbox_ymin"
		" OR %(PREFIXzmin)s>bbox_zmax OR %(PREFIXzmax)s<bbox_zmin)"}


def getBboxQueryFromBbox(intersect, bbox, center, prefix):
	xbb, ybb, zbb = bbox
	return _intersectQueries[intersect].replace("PREFIX", prefix), {
		prefix+"xmin": xbb[0], prefix+"xmax": xbb[1],
		prefix+"ymin": ybb[0], prefix+"ymax": ybb[1],
		prefix+"zmin": zbb[0], prefix+"zmax": zbb[1],
		prefix+"xcenter": center.x,
		prefix+"ycenter": center.y,
		prefix+"zcenter": center.z, }


def getBboxQuery(parameters, prefix="sia"):
	"""returns an SQL fragment for a SIAP query for bboxes.

	The SQL is returned as a WHERE-fragment in a string and a dictionary
	to fill the variables required.

	parameters is a dictionary that maps the SIAP keywords to the
	values in the query.  Parameters not defined by SIAP are ignored.
	"""
	raDec = map(float, parameters["POS"].split(","))
	sizes = map(float, parameters["SIZE"].split(","))
	if len(sizes)==1:
		sizes = sizes*2
	bbox, center = getBboxFromSiapPars(raDec, sizes)
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	return getBboxQueryFromBbox(intersect, bbox, center, prefix)


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
