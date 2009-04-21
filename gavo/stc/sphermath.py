"""
Spherical geometry and related helper functions.
"""

import math
import numarray

from gavo.stc import dm
from gavo.stc import conform
from gavo.stc import units
from gavo.stc.common import *


# Units spherical coordinates have to be in for transformation to/from
# unit vectors.
_uvSpaceUnit = ("rad", "rad", "pc")
_uvTimeUnit = ("yr", "yr", "yr")
	

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

	if rTrue==0.:  # Special case position at origin
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
		posValues = (math.atan2(y, x), math.atan2(z, rInXY), rTrue)
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
			pos, unit = pos[:2], _uvSpaceUnit[:2]
		else:
			unit = _uvSpaceUnit
		buildArgs["place"] = bPlace.change(value=pos, unit=unit)

	if bVel:
		if bVel.frame.nDim==2:
			pos, unit, tUnit = pos[:2], _uvSpaceUnit[:2], _uvTimeUnit[:2]
		else:
			unit, tUnit = _uvSpaceUnit, _uvTimeUnit
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

	if bPlace:
		_ensureSphericalFrame(bPlace)
		space = bPlace.value
		srcUnit = bPlace.unit
		if bPlace.frame.nDim==2:
			space = space+(_defaultDistance,)
			srcUnit = srcUnit+('pc',)
		space = units.getVectorConverter(srcUnit, _uvSpaceUnit)(space)
	if bVel:
		_ensureSphericalFrame(bVel)
		vel = bVel.value
		srcUnit, srcUnitT = bVel.unit, bVel.velTimeUnit
		if bVel.frame.nDim==2:
			vel = vel+(0,)
			srcUnit, srcUnitT = srcUnit+('pc',), srcUnitT+('yr',)
		vel = units.getVelocityConverter(srcUnit, srcUnitT,
			_uvSpaceUnit, _uvTimeUnit)(vel)
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
