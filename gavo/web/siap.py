"""
Generic support for querying for areas, SIAP-style
"""

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


def getBboxFromSiapPars(raDec, sizes):
	"""returns a cartesian bBox for a position and a size.

	Both parameters are pairs in decimal degrees.
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 0), (1, 1))]
	['1.0000, 1.0000', '-0.0087, 0.0087', '-0.0087, 0.0087']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((0, 90), (1, 1))]
	['-0.0087, 0.0087', '-0.0087, 0.0087', '1.0000, 1.0000']
	>>> ["%.4f, %.4f"%t for t in getBboxFromSiapPars((45, -45), (5, 5))]
	['0.4473, 0.5527', '0.4473, 0.5527', '-0.7380, -0.6763']
	"""
	cPos = coords.computeUnitSphereCoords(*raDec)
	sizeAlpha, sizeDelta = map(utils.degToRad, sizes)
	unitAlpha, unitDelta = coords.getTangentialUnits(cPos)
	cornerPoints = [
		cPos-sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
		cPos+sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
		cPos-sizeAlpha/2*unitAlpha+sizeDelta/2*unitDelta,
		cPos+sizeAlpha/2*unitAlpha+sizeDelta/2*unitDelta
	]
	return getBbox(cornerPoints)


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


def getBboxQueryFromBbox(intersect, bbox, prefix):
	xbb, ybb, zbb = bbox
	return _intersectQueries[intersect].replace("PREFIX", prefix), {
		prefix+"xmin": xbb[0], prefix+"xmax": xbb[1],
		prefix+"ymin": ybb[0], prefix+"ymax": ybb[1],
		prefix+"zmin": zbb[0], prefix+"zmax": zbb[1],
		prefix+"xcenter": (xbb[0]+xbb[1])/2., 
		prefix+"ycenter": (ybb[0]+ybb[1])/2., 
		prefix+"zcenter": (zbb[0]+zbb[1])/2., }


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
	bbox = getBboxFromSiapPars(raDec, sizes)
	intersect = parameters.get("INTERSECT", "OVERLAPS")
	return getBboxQueryFromBbox(intersect, bbox, prefix)


def _test():
	import doctest, siap
	doctest.testmod(siap)


if __name__=="__main__":
	_test()
