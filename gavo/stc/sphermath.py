"""
Spherical geometry and related helper functions.
"""

import math
import numarray

from gavo.stc import dm
from gavo.stc import conform
from gavo.stc import units
from gavo.stc.common import *

def getRotX(angle):
	"""returns a 3-rotation matrix for rotating angle radians around x.
	"""
	c, s = math.cos(angle), math.sin(angle)
	return numarray.array([[1, 0, 0], [0, c, s], [0, -s, c]])


def getRotY(angle):
	"""returns a 3-rotation matrix for rotating angle radians around y.
	"""
	c, s = math.cos(angle), math.sin(angle)
	return numarray.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])


def getRotZ(angle):
	"""returns a 3-rotation matrix for rotating angle radians around u.
	"""
	c, s = math.cos(angle), math.sin(angle)
	return numarray.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])


def getMatrixFromEulerAngles(z1, x, z2):
	"""returns a 3-rotation matrix for the z-x-z Euler angles.

	There are some functions to obtain such angles below.
	"""
	return numarray.dot(numarray.dot(getRotZ(z1), getRotX(x)),
		getRotZ(z2))


def spherToCart(theta, phi):
	"""returns a 3-cartesian unit vector pointing to longitude theta,
	latitude phi.

	The angles are in rad.
	"""
	cp = math.cos(phi)
	return math.cos(theta)*cp, math.sin(theta)*cp, math.sin(phi)


def cartToSpher(unitvector):
	"""returns spherical coordinates for a 3-unit vector.

	We do not check if unitvector actually *is* a unit vector.  The returned
	angles are in rad.
	"""
	x, y, z = unitvector
	rInXY = math.sqrt(x**2+y**2)
	if abs(rInXY)<1e-9:  # pole
		theta = 0
	else:
		theta = math.atan2(y, x)
	if theta<0:
		theta += 2*math.pi
	phi = math.atan2(z, rInXY)
	return (theta, phi)


# Units spherical coordinates have to be in for transformation to/from
# unit vectors.
_uvPosUnit = ("rad", "rad", "pc")
_uvVPosUnit = ("rad", "rad", "pc")
_uvVTimeUnit = ("cy", "cy", "cy")
	

def _uvToSpherRaw(uv):
	"""returns spherical position and velocity vectors for the cartesian
	6-vector uv.

	This is a helper for uvToSpher.

	This is based on SOFA's pv2s; the units here are given by the _rawSpherSTC
	object above; this will only work if the input of spherToUV had the
	standard coordinates.
	"""
	x,y,z,xd,yd,zd = uv
	rInXY2 = x**2+y**2
	r2 = rInXY2+z**2
	rw = rTrue = math.sqrt(r2)

	if rTrue==0.:  # Special case position at z axis
		x = xd
		y = yd
		z = zd
		rInXY2 = x**2+y**2
		r2 = rInXY2+z**2
		rw = math.sqrt(r2)

	rInXY = math.sqrt(rInXY2)
	xyp = x*xd+y*yd
	radialVel = 0
	if rw!=0:
		radialVel = (xyp+z*zd)/rw
	
	if rInXY2!=0.:
		theta = math.atan2(y, x)
		if theta<0:
			theta += 2*math.pi
		posValues = (theta, math.atan2(z, rInXY), rTrue)
		velValues = ((x*yd-y*xd)/rInXY2, (zd*rInXY2-z*xyp)/(r2*rInXY), radialVel)
	else:
		phi = 0
		if z!=0:
			phi = math.atan2(z, rInXY)
		posValues = (0, phi, rTrue)
		velValues = (0, 0, radialVel)
	return posValues, velValues


def _ensureSphericalFrame(coo):
	"""raises an error if coo's frame is not suitable for holding spherical
	coordinates.
	"""
	if (not isinstance(coo.frame, dm.SpaceFrame)
			or coo.frame.nDim==1 
			or coo.frame.flavor!="SPHERICAL"):
		raise STCValueError("%s is not a valid frame for transformable"
			" spherical coordinates."%(coo.frame))


def uvToSpher(uv, baseSTC):
	"""returns an STC object like baseSTC, but with the values of the 6-unit
	vector uv filled in.
	"""
	bPlace, bVel = baseSTC.place, baseSTC.velocity
	pos, vel = _uvToSpherRaw(uv)
	buildArgs = {}

	if bPlace:
		if bPlace.frame.nDim==2:
			pos, unit = pos[:2], _uvPosUnit[:2]
		else:
			unit = _uvPosUnit
		buildArgs["place"] = bPlace.change(value=pos, unit=unit)

	if bVel:
		if bVel.frame.nDim==2:
			pos, unit, tUnit = pos[:2], _uvVPosUnit[:2], _uvVTimeUnit[:2]
		else:
			unit, tUnit = _uvVPosUnit, _uvVTimeUnit
		buildArgs["velocity"] = bVel.change(value=vel, unit=unit,
			velTimeUnit=tUnit)

	return conform.conformUnits(baseSTC, baseSTC.change(**buildArgs))


_defaultDistance = 1e10   # filled in for distances not given, in pc

def _getUVSphericals(stcObject):
	"""returns (space, vel) from stcObject in units suitable for generation
	of 6-cartesian vectors.

	"Sane" defaults are inserted for missing values.

	This is a helper for spherToUV.
	"""
	space, vel = (0, 0, _defaultDistance), (0, 0, 0)
	bPlace, bVel = stcObject.place, stcObject.velocity

	if bPlace and bPlace.value:
		_ensureSphericalFrame(bPlace)
		space, srcUnit = bPlace.value, bPlace.unit
		if bPlace.frame.nDim==2:
			space = space+(_defaultDistance,)
			srcUnit = srcUnit+_uvPosUnit[-1:]
		space = units.getVectorConverter(srcUnit, _uvPosUnit)(space)
	if bVel and bVel.value:
		_ensureSphericalFrame(bVel)
		vel = bVel.value
		srcUnit, srcUnitT = bVel.unit, bVel.velTimeUnit
		if bVel.frame.nDim==2:
			vel = vel+(0,)
			srcUnit = srcUnit+_uvVPosUnit[-1:]
			srcUnitT = srcUnitT+_uvVTimeUnit[-1:]
		vel = units.getVelocityConverter(srcUnit, srcUnitT,
			_uvVPosUnit, _uvVTimeUnit)(vel)
	return space, vel


def spherToUV(stcObject):
	"""returns a 6-vector of cartesian place and velocity from stcObject.

	stcObject must be in spherical coordinates.  If any of parallax,
	proper motions, and radial velocity are missing, "sane" defaults
	are substituted.
	"""
	(alpha, delta, r), (alphad, deltad, rd) = _getUVSphericals(stcObject)
	sa, ca = math.sin(alpha), math.cos(alpha)
	sd, cd = math.sin(delta), math.cos(delta)
	x, y = r*cd*ca, r*cd*sa
	w = r*deltad*sd-cd*rd

	return numarray.array([x, y, r*sd,
		-y*alphad-w*ca, x*alphad-w*sa, r*deltad*cd+sd*rd])


def computeTransMatrixFromPole(poleCoo, longZeroCoo, changeHands=False): 
	"""returns a transformation matrix to transform from the reference
	system into a rotated system.

	The rotated system is defined by its pole, the spherical coordinates
	at which it has longitude zero and whether or not it is right handed.

	All angles are in rad.
	"""
	x = spherToCart(*longZeroCoo)
	z = spherToCart(*poleCoo)
	if abs(numarray.dot(x, z))>1e-5:
		raise STCValueError("%s and %s are not valid pole/zero points for"
			" a rotated coordinate system"%(poleCoo, longZeroCoo))
	y = (z[1]*x[2]-z[2]*x[1], z[2]*x[0]-z[0]*x[2], z[0]*x[1]-z[1]*x[0])
	if changeHands:
		y = (-y[0], -y[1], -y[2])
	return numarray.array([x,y,z])
