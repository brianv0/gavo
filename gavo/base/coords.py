"""
(Mostly deprecated) code to handle coordinate systems and transform 
between them.  

Basically all of this should be taken over by stc and astropysics.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import math
import new
from math import sin, cos, pi #noflake: exported names
import re

import numpy

from gavo import utils
from gavo.utils import DEG
from gavo.utils import pgsphere
from gavo.utils import pyfits


pywcs = utils.DeferredImport("pywcs")


fitsKwPat = re.compile("[A-Z0-9_-]{1,8}$")

def makePyfitsFromDict(d):
	"""returns a pyfits header with the cards of d.items().

	Only keys "looking like" FITS header keywords are used, i.e. all-uppercase
	and shorter than 9 characters.
	"""
	res = pyfits.Header()
	for key, val in d.iteritems():
		if fitsKwPat.match(key) and val is not None:
			res.update(str(key), val)
	return res


_wcsTestDict = {
	"CRVAL1": 0,   "CRVAL2": 0, "CRPIX1": 50,  "CRPIX2": 50,
	"CD1_1": 0.01, "CD1_2": 0, "CD2_1": 0,    "CD2_2": 0.01,
	"NAXIS1": 100, "NAXIS2": 100, "CUNIT1": "deg", "CUNIT2": "deg",
	"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP', "LONPOLE": 180.,
}


class Box(object):
	"""is a 2D box.

	The can be constructed either with two tuples, giving two points
	delimiting the box, or with four arguments x0, x1, y0, y1.

	To access the thing, you can either access the x[01], y[01] attributes
	or use getitem to retrieve the upper right and lower left corner.

	The slightly silly ordering of the bounding points (larger values
	first) is for consistency with Postgresql.
	"""
	def __init__(self, x0, x1, y0=None, y1=None):
		if y0 is None:
			x0, y0 = x0
			x1, y1 = x1
		lowerLeft = (min(x0, x1), min(y0, y1))
		upperRight = (max(x0, x1), max(y0, y1))
		self.x0, self.y0 = upperRight
		self.x1, self.y1 = lowerLeft
	
	def __getitem__(self, index):
		if index==0 or index==-2:
			return (self.x0, self.y0)
		elif index==1 or index==-1:
			return (self.x1, self.y1)
		else:
			raise IndexError("len(box) is always 2")

	def __str__(self):
		return "((%.4g,%.4g), (%.4g,%.4g))"%(self.x0, self.y0, self.x1, self.y1)

	def __repr__(self):
		return "Box((%g,%g), (%g,%g))"%(self.x0, self.y0, self.x1, self.y1)


def getBbox(points):
	"""returns a bounding box for the sequence of 2-sequences points.

	The thing returned is a coords.Box.

	>>> getBbox([(0.25, 1), (-3.75, 1), (-2, 4)])
	Box((0.25,4), (-3.75,1))
	"""
	xCoos, yCoos = [[p[i] for p in points] for i in range(2)]
	return Box(min(xCoos), max(xCoos), min(yCoos), max(yCoos))


def clampAlpha(alpha):
	while alpha>360:
		alpha -= 360
	while alpha<0:
		alpha += 360
	return alpha


def clampDelta(delta):
	return max(-90, min(90, delta))


def straddlesStitchingLine(minRA, maxRA):
	"""returns true if something bordered by minRA and maxRA presumably straddles
	the stitching line.

	This assumes minRA<maxRA, and that "something" is less than 180 degrees in
	longitude.

	Angles are in degrees here.
	"""
	return maxRA>270 and minRA<90


def _calcFootprintMonkeypatch(self, hdr=None, undistort=True):
	"""returns the coordinates of the four corners of an image.

	This is for monkeypatching pywcs, which at least up to 1.11 does
	really badly when non-spatial coordinates are present.  This method
	relies on the _monkey_naxis_lengths attribute left by getWCS to
	figure out the axis lengths.

	pywcs' hdr argument is always ignored here.
	"""
	naxis1, naxis2 = self._monkey_naxis_lengths
	corners = [[1,1],[1,naxis2], [naxis1,naxis2], [naxis1, 1]]
	if undistort:
		return self.all_pix2sky(corners, 1)
	else:
		return self.wcs_pix2sky(corners,1)


def _monkeypatchWCS(wcsObj, naxis, wcsFields):
	"""monkeypatches pywcs instances for DaCHS' purposes.
	"""
	wcsObj._dachs_header = wcsFields
	wcsObj.longAxis = naxis[0]
	if len(naxis)>1:
		wcsObj.latAxis = naxis[1]
	wcsObj._monkey_naxis_lengths = [wcsFields.get("NAXIS%d"%i)
		for i in naxis]
	wcsObj.origCalcFootprint = wcsObj.calcFootprint
	wcsObj.calcFootprint = new.instancemethod(_calcFootprintMonkeypatch, 
		wcsObj, wcsObj.__class__)


def getWCS(wcsFields, naxis=(1,2), relax=True):
	"""returns a WCS instance from wcsFields
	
	wcsFields can be either a dictionary or a pyfits header giving
	some kind of WCS information, or an pywcs.WCS instance that is
	returned verbatim.

	This will return None if no (usable) WCS information is found in the header.

	We monkeypatch the resulting pywcs structure quite a bit.  Among
	others:

	* calcFootprint takes into account the naxis kw parameter
	* there's longAxis and latAxis attributes taken from naxis
	* there's _dachs_header, containing the incoming k-v pairs
	* there's _monkey_naxis_length, the lengths along the WCS axes.
	"""
	if isinstance(wcsFields, pywcs.WCS):
		return wcsFields
	if isinstance(wcsFields, dict):
		wcsFields = makePyfitsFromDict(wcsFields)

	# pywcs will invent identity transforms if no WCS keys are present.
	# Hence. we do some sanity checking up front to weed those out.
	if (not wcsFields.has_key("CD1_1") 
			and not wcsFields.has_key("CDELT1")
			and not wcsFields.has_key("PC1_1")):
		return None
	
	# workaround for a bug in pywcs 1.11: .*_ORDER=0 must not happen
	for key in ["AP_ORDER", "BP_ORDER", "A_ORDER", "B_ORDER"]:
		if wcsFields.get(key)==0:
			del wcsFields[key]

	wcsObj = pywcs.WCS(wcsFields, relax=relax, naxis=naxis)

	_monkeypatchWCS(wcsObj, naxis, wcsFields)
	return wcsObj


def pix2foc(wcsFields, pixels):
	"""returns the focal plane coordindates for the 2-sequence pixels.

	(this is a thin wrapper intended to abstract for pix2sky's funky
	calling convention; also, we fix on the silly "0 pixel is 1 convention")
	"""
	wcsObj = getWCS(wcsFields)
	val = wcsObj.pix2foc((pixels[0],), (pixels[1],), 1)
	return val[0][0], val[1][0]


def pix2sky(wcsFields, pixels):
	"""returns the sky coordindates for the 2-sequence pixels.

	(this is a thin wrapper intended to abstract for pix2sky's funky
	calling convention; also, we fix on the silly "0 pixel is 1 convention")
	"""
	wcsObj = getWCS(wcsFields)
	val = wcsObj.all_pix2sky((pixels[0],), (pixels[1],), 1)
	return val[0][0], val[1][0]


def sky2pix(wcsFields, longLat):
	"""returns the pixel coordindates for the 2-sequence longLad.

	(this is a thin wrapper intended to abstract for sky2pix's funky
	calling convention; also, we fix on the silly "0 pixel is 1 convention")
	"""
	val = getWCS(wcsFields).wcs_sky2pix((longLat[0],), (longLat[1],), 1)
	return val[0][0], val[1][0]


def getPixelSizeDeg(wcsFields):
	"""returns the sizes of a pixel at roughly the center of the image for
	wcsFields.

	Near the pole, this gets a bit weird; we do some limitation of the width
	of RA pixels there.
	"""
	wcs = getWCS(wcsFields)
	width, height = wcs._dachs_header["NAXIS1"], wcs._dachs_header["NAXIS2"]
	cosDelta = max(0.01, math.cos(pix2sky(wcs, (width/2, height/2))[1]*DEG))

	p0 = pix2sky(wcs, (width/2, height/2))
	p1 = pix2sky(wcs, (width/2+1, height/2))
	p2 = pix2sky(wcs, (width/2, height/2+1))
	return abs(p1[0]-p0[0])*cosDelta, abs(p2[1]-p0[1])


def getWCSTrafo(wcsFields):
	"""returns a callable transforming pixel to physical coordinates.

	wcsFields is passed to getWCS, see there for legal types.
	"""
	wcs = getWCS(wcsFields)
	return lambda x, y: pix2sky(wcs, (x, y))


def getInvWCSTrafo(wcsFields):
	"""returns a callable transforming physical to pixel coordinates.

	wcsFields is passed to getWCS, see there for legal types.
	"""
	wcs = getWCS(wcsFields)
	return lambda ra, dec: sky2pix(wcs, (ra,dec))


def getBboxFromWCSFields(wcsFields):
	"""returns a bbox and a field center for WCS FITS header fields.

	wcsFields is passed to getWCS, see there for legal types.

	Warning: this is different from wcs.calcFootprint in that
	we keep negative angles if the stitching line is crossed; also,
	no distortions or anything like that are taken into account.

	This code is only used for bboxSIAP, and you must not use it
	for anything else; it's going to disappear with it.
	"""
 	wcs = getWCS(wcsFields)
	width, height = float(wcs._dachs_header["NAXIS1"]
		), float(wcs._dachs_header["NAXIS2"])
	cA, cD = pix2sky(wcs, (width/2., height/2.))
	wA, wD = getPixelSizeDeg(wcs)
	wA *= width/2.
	wD *= height/2.
	# Compute all "corners" to ease handling of corner cases
	bounds = [(cA+wA, cD+wD), (cA-wA, cD-wD), (cA+wA, cD-wD),
		(cA-wA, cD+wD)]
	bbox = getBbox(bounds)
	if bbox[0][1]>89:
		bbox = Box((0, clampDelta(bbox[0][1])), (360, clampDelta(bbox[1][1])))
	if bbox[1][1]<-89:
		bbox = Box((0, clampDelta(bbox[0][1])), (360, clampDelta(bbox[1][1])))
	return bbox


def getSpolyFromWCSFields(wcsFields):
	"""returns a pgsphere spoly corresponding to wcsFields

	wcsFields is passed to getWCS, see there for legal types.

	The polygon returned is computed by using the four corner points
	assuming a rectangular image.  This typically is only loosely related
	to a proper spherical polygon describing the shape, as image boundaries
	in the usual projects are not great circles.

	Also, the spoly will be in the coordinate system of the WCS.  If that
	is not ICRS, you'll probably get something incompatible with most of the
	VO.
	"""
	wcs = getWCS(wcsFields)
	return pgsphere.SPoly([pgsphere.SPoint.fromDegrees(*p)
		for p in wcs.calcFootprint(wcs._dachs_header)])


def getCenterFromWCSFields(wcsFields, spatialAxes=(1,2)):
	"""returns RA and Dec of the center of an image described by wcsFields.

	This will use the 1-based axes given by spatialAxes to figure out
	the pixel lengths of the axes.
	"""
	wcs = getWCS(wcsFields)
	center1 = wcs._dachs_header["NAXIS%s"%spatialAxes[0]]/2.
	center2 = wcs._dachs_header["NAXIS%s"%spatialAxes[1]]/2.
	return pix2sky(wcs, (center1, center2))


def getCoveringCircle(wcsFields, spatialAxes=(1,2)):
	"""returns a pgsphere.scircle large enough to cover the image
	described by wcsFields.
	"""
	wcs = getWCS(wcsFields)
	center = getCenterFromWCSFields(wcs)

	height, width = (wcs._dachs_header["NAXIS%s"%spatialAxes[0]],
		wcs._dachs_header["NAXIS%s"%spatialAxes[1]])
	radius = max(
			getGCDist(center, pix2sky(wcs, corner))
		for corner in [(0, 0), (height, 0), (0, width), (height, width)])

	return pgsphere.SCircle(pgsphere.SPoint.fromDegrees(*center),
		radius*DEG)


def getSkyWCS(hdr):
	"""returns a pair of a pywcs.WCS instance and a sequence of 
	the spatial axes.

	This will be None, () if no WCS could be discerned.  There's some
	heuristics involved in the identification of the spatial coordinates
	that will probably fail for unconventional datasets.
	"""
	wcsAxes = []
	# heuristics: iterate through CTYPEn, anything that's got
	# a - is supposed to be a position (needs some refinement :-)
	for ind in range(1, hdr["NAXIS"]+1):
		if "-" in hdr.get("CTYPE%s"%ind, ""):
			wcsAxes.append(ind)

	if not wcsAxes:
		# more heuristics to be inserted here
		return None, ()

	if len(wcsAxes)!=2:
		raise utils.ValidationError("This FITS has !=2"
			" spatial WCS axes.  Please contact the DaCHS authors and"
			" make them support it.", "PUBDID")

	return getWCS(hdr, naxis=wcsAxes), wcsAxes


def getPixelLimits(cooPairs, wcsFields):
	"""returns pixel cutout slices for covering cooPairs in an image with
	wcsFields.

	cooPairs is a sequence of (ra, dec) tuples.  wcsFields is a DaCHS-enhanced
	pywcs.WCS instance.

	Behaviour if cooPairs use a different coordinate system from wcsFields
	is undefined at this point.

	Each cutout slice is a tuple of (FITS axis number, lower limit, upper limit).

	If cooPairs is off the wcsFields coverage, a null cutout on the longAxis
	is returned.
	"""
	latAxis = wcsFields.latAxis
	longAxis = wcsFields.longAxis
	latPixels = wcsFields._dachs_header["NAXIS%d"%latAxis]
	longPixels = wcsFields._dachs_header["NAXIS%d"%longAxis]

	# pywcs does really funny things when we "wrap around".  Therefore, we
	# clamp values to be within the pywcs-safe region.  Note that
	# due to spherical magic this is not enough to ensure +/-Inf behaviour
	# for SODA
	cooPairs = [(
			min(359.99999, max(-89.9999, ra)), 
			min(89.9999, max(-89.9999, dec)))
		for ra, dec in cooPairs]

	slices = []
	pixelFootprint = numpy.asarray(
		numpy.round(wcsFields.wcs_sky2pix(cooPairs, 1)), numpy.int32)
	pixelLimits = [
		[min(pixelFootprint[:,0]), max(pixelFootprint[:,0])],
		[min(pixelFootprint[:,1]), max(pixelFootprint[:,1])]]
	
	# see if we're completely off coverage
	if pixelLimits[0][1]<0 or pixelLimits[1][1]<0:
		return [[longAxis, 0, 0]]
	if pixelLimits[0][0]>longPixels or pixelLimits[1][0]>latPixels:
		return [[longAxis, 0, 0]]

	# now crop to the actual pixel values
	pixelLimits = [
		[max(pixelLimits[0][0], 1), min(pixelLimits[0][1], longPixels)],
		[max(pixelLimits[1][0], 1), min(pixelLimits[1][1], latPixels)]]

	if pixelLimits[0]!=[1, longPixels]:
		slices.append([longAxis]+pixelLimits[0])
	if pixelLimits[1]!=[1, latPixels]:
		slices.append([latAxis]+pixelLimits[1])
	return slices


# let's do a tiny vector type.  It's really not worth getting some dependency
# for this.
class Vector3(object):
	"""is a 3d vector that responds to both .x... and [0]...

	>>> x, y = Vector3(1,2,3), Vector3(2,3,4)
	>>> x+y
	Vector3(3.000000,5.000000,7.000000)
	>>> 4*x
	Vector3(4.000000,8.000000,12.000000)
	>>> x*4
	Vector3(4.000000,8.000000,12.000000)
	>>> x*y
	20
	>>> "%.6f"%abs(x)
	'3.741657'
	>>> print abs((x+y).normalized())
	1.0
	"""
	def __init__(self, x, y=None, z=None):
		if isinstance(x, tuple):
			self.coos = x
		else:
			self.coos = (x, y, z)

	def __repr__(self):
		return "Vector3(%f,%f,%f)"%tuple(self.coos)

	def __str__(self):
		def cutoff(c):
			if abs(c)<1e-10:
				return 0
			else:
				return c
		rounded = [cutoff(c) for c in self.coos]
		return "[%.2g,%.2g,%.2g]"%tuple(rounded)

	def __getitem__(self, index):
		return self.coos[index]

	def __mul__(self, other):
		"""does either scalar multiplication if other is not a Vector3, or
		a scalar product.
		"""
		if isinstance(other, Vector3):
			return self.x*other.x+self.y*other.y+self.z*other.z
		else:
			return Vector3(self.x*other, self.y*other, self.z*other)
	
	__rmul__ = __mul__

	def __div__(self, scalar):
		return Vector3(self.x/scalar, self.y/scalar, self.z/scalar)

	def __add__(self, other):
		return Vector3(self.x+other.x, self.y+other.y, self.z+other.z)

	def __sub__(self, other):
		return Vector3(self.x-other.x, self.y-other.y, self.z-other.z)

	def __abs__(self):
		return math.sqrt(self.x**2+self.y**2+self.z**2)

	def cross(self, other):
		return Vector3(self.y*other.z-self.z*other.y,
			self.z*other.x-self.x*other.z,
			self.x*other.y-self.y*other.x)

	def normalized(self):
		return self/abs(self)

	def getx(self): return self.coos[0]
	def setx(self, x): self.coos[0] = x
	x = property(getx, setx)
	def gety(self): return self.coos[1]
	def sety(self, y): self.coos[1] = y
	y = property(gety, sety)
	def getz(self): return self.coos[2]
	def setz(self, z): self.coos[2] = z
	z = property(getz, setz)


def sgn(a):
	if a<0:
		return -1
	elif a>0:
		return 1
	else:
		return 0


def computeUnitSphereCoords(alpha, delta):
# TODO: replaced by mathtricks.spherToCart
	"""returns the 3d coordinates of the intersection of the direction
	vector given by the spherical coordinates alpha and delta with the
	unit sphere.

	alpha and delta are given in degrees.

	>>> print computeUnitSphereCoords(0,0)
	[1,0,0]
	>>> print computeUnitSphereCoords(0, 90)
	[0,0,1]
	>>> print computeUnitSphereCoords(90, 90)
	[0,0,1]
	>>> print computeUnitSphereCoords(90, 0)
	[0,1,0]
	>>> print computeUnitSphereCoords(180, -45)
	[-0.71,0,-0.71]
	"""
	return Vector3(*utils.spherToCart(alpha*DEG, delta*DEG))


def dirVecToCelCoos(dirVec):
	"""returns alpha, delta in degrees for the direction vector dirVec.

	>>> dirVecToCelCoos(computeUnitSphereCoords(25.25, 12.125))
	(25.25, 12.125)
	>>> dirVecToCelCoos(computeUnitSphereCoords(25.25, 12.125)*16)
	(25.25, 12.125)
	>>> "%g,%g"%dirVecToCelCoos(computeUnitSphereCoords(25.25, 12.125)+
	...   computeUnitSphereCoords(30.75, 20.0))
	'27.9455,16.0801'
	"""
	dirVec = dirVec.normalized()
	alpha = math.atan2(dirVec.y, dirVec.x)
	if alpha<0:
		alpha += 2*math.pi
	return alpha*180./math.pi, math.asin(dirVec.z)*180./math.pi


def getTangentialUnits(cPos):
	"""returns the unit vectors for RA and Dec at the unit circle position cPos.

	We compute them by solving u_1*p_1+u_2*p_2=0 (we already know that
	u_3=0) simultaneously with u_1^2+u_2^2=1 for RA, and by computing the
	cross product of the RA unit and the radius vector for dec.

	This becomes degenerate at the poles.  If we're exactly on a pole,
	we *define* the unit vectors as (1,0,0) and (0,1,0).

	Orientation is a pain -- the convention used here is that unit delta
	always points to the pole.

	>>> cPos = computeUnitSphereCoords(45, -45)
	>>> ua, ud = getTangentialUnits(cPos)
	>>> print abs(ua), abs(ud), cPos*ua, cPos*ud
	1.0 1.0 0.0 0.0
	>>> print ua, ud
	[-0.71,0.71,0] [-0.5,-0.5,-0.71]
	>>> ua, ud = getTangentialUnits(computeUnitSphereCoords(180, 60))
	>>> print ua, ud
	[0,-1,0] [0.87,0,0.5]
	>>> ua, ud = getTangentialUnits(computeUnitSphereCoords(0, 60))
	>>> print ua, ud
	[0,1,0] [-0.87,0,0.5]
	>>> ua, ud = getTangentialUnits(computeUnitSphereCoords(0, -60))
	>>> print ua, ud
	[0,1,0] [-0.87,0,-0.5]
	"""
	try:
		normalizer = 1/math.sqrt(cPos.x**2+cPos.y**2)
	except ZeroDivisionError:
		return Vector3(1,0,0), Vector3(0,1,0)
	alphaUnit = normalizer*Vector3(cPos.y, -cPos.x, 0)
	deltaUnit = normalizer*Vector3(cPos.x*cPos.z, cPos.y*cPos.z,
		-cPos.x**2-cPos.y**2)
	# now orient the vectors: in delta, we always look towards the pole
	if sgn(cPos.z)!=sgn(deltaUnit.z):
		deltaUnit = -1*deltaUnit  # XXX this breaks on the equator
	# The orientation of alphaUnit depends on the hemisphere
	if cPos.z<0:  # south
		if deltaUnit.cross(alphaUnit)*cPos<0:
			alphaUnit = -1*alphaUnit
	else:  # north
		if deltaUnit.cross(alphaUnit)*cPos>0:
			alphaUnit = -1*alphaUnit
	return alphaUnit, deltaUnit


def movePm(alphaDeg, deltaDeg, pmAlpha, pmDelta, timeDiff, foreshort=0):
	"""returns alpha and delta for an object with pm pmAlpha after timeDiff.

	pmAlpha has to have cos(delta) applied, everything is supposed to be
	in degrees, the time unit is yours to choose.
	"""
	alpha, delta = alphaDeg/180.*math.pi, deltaDeg/180.*math.pi
	pmAlpha, pmDelta = pmAlpha/180.*math.pi, pmDelta/180.*math.pi
	sd, cd = math.sin(delta), math.cos(delta)
	sa, ca = math.sin(alpha), math.cos(alpha)
	muAbs = math.sqrt(pmAlpha**2+pmDelta**2);
	muTot = muAbs+0.5*foreshort*timeDiff;

	if muAbs<1e-20:
		return alphaDeg, deltaDeg
	# this is according to Mueller, 115 (4.94)
	dirA = pmAlpha/muAbs;
	dirD = pmDelta/muAbs;
	sinMot = sin(muTot*timeDiff);
	cosMot = cos(muTot*timeDiff);

	dirVec = Vector3(-sd*ca*dirD*sinMot - sa*dirA*sinMot + cd*ca*cosMot,
		-sd*sa*dirD*sinMot + ca*dirA*sinMot + cd*sa*cosMot,
		+cd*dirD*sinMot + sd*cosMot)
	return dirVecToCelCoos(dirVec)


def getGCDist(pos1, pos2):
	"""returns the distance along a great circle between two points.

	The distance is in degrees, the input positions are in degrees.
	"""
	scalarprod = computeUnitSphereCoords(*pos1)*computeUnitSphereCoords(*pos2)
	# cope with numerical trouble
	if scalarprod>=1:
		return 0
	return math.acos(scalarprod)/DEG


def _test():
	import doctest, coords
	doctest.testmod(coords)


if __name__=="__main__":
	_test()
