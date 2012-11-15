"""
Computing bboxes for STC geometries.

A bbox coming out of this module is a 4-tuple of (ra0, de0, ra1, de1) in
ICRS degrees.

(You're right, this should be part of the dm classes; but it's enough
messy custom code that I found it nicer to break it out).
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.


from gavo import utils
from gavo.stc import conform
from gavo.stc import dm
from gavo.stc import stcsast


@utils.memoized
def getStandardFrame():
	return stcsast.parseSTCS("Position ICRS unit deg")


def _makeSphericalBbox(minRA, minDec, maxRA, maxDec):
	"""yields one or two bboxes from for spherical coordinates.

	This handles crossing the stich line as well as shooting over the pole.

	Everything here is in degrees.

	This function assumes that -360<minRA<maxRA<720 and that at least one
	of minRA, maxRA is between 0 and 360.
	"""
	if minDec<-90:
		# fold over the pole
		maxDec = max(maxDec, -minDec-180)
		minDec = -90
		minRA, maxRA = 0, 360

	if maxDec>90:
		# fold over the pole
		minDec = min(minDec, 180-maxDec)
		maxDec = 90
		minRA, maxRA = 0, 360

	if minRA<0:
		yield (0, minDec, maxRA, maxDec)
		yield (360+minRA, minDec, 360, maxDec)
	elif maxRA>360:
		yield (0, minDec, maxRA-360, maxDec)
		yield (minRA, minDec, 360, maxDec)
	else:
		yield (minRA, minDec, maxRA, maxDec)


def _computeCircleBbox(circle):
	"""helps _getBboxesFor.
	"""
	return _makeSphericalBbox(
		circle.center[0]-circle.radius,
		circle.center[1]-circle.radius,
		circle.center[0]+circle.radius,
		circle.center[1]+circle.radius)


_BBOX_COMPUTERS = {
	"Circle": _computeCircleBbox,
}


def _getBboxesFor(geo):
	"""yields one or two bboxes for a conformed geometry.

	Two bboxes are returned when the geometry overlaps the stitching point.

	A geometry is conformed if it's been conformed to what's coming back
	from getStandardFrame() above.
	"""
	geoName = geo.__class__.__name__
	if geoName not in _BBOX_COMPUTERS:
		raise STCInternalError("Do now know how to compute the bbox of"
			" %s."%geoName)
	
	for bbox in _BBOX_COMPUTERS[geoName](geo):
		yield bbox

def getBboxes(ast):
	"""iterates over the bboxes of the areas within ast.

	bboxes are (ra0, de0, ra1, de1) in ICRS degrees.
	"""
	astc = conform.conform(ast, getStandardFrame())
	for area in astc.areas:
		for bbox in _getBboxesFor(area):
			yield bbox

