"""
Spherical geometry and related helper functions.
"""

import math
import numarray

from gavo import utils
from gavo.stc import dm
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


def getMatrixFromEulerVector(eulerVector):
	"""returns a rotation matrix for an Euler vector.

	An euler vector gives the rotation axis, its magnitude the angle in rad.

	This function is a rip-off of SOFA's rv2m.

	eulerVector is assumed to be a numarray array.
	"""
	x, y, z = eulerVector
	phi = math.sqrt(x**2+y**2+z**2)
	sp, cp = math.sin(phi), math.cos(phi)
	f = 1-cp
	if phi!=0:
		x, y, z = eulerVector/phi
	return numarray.array([
		[x**2*f+cp, x*y*f+z*sp,  x*z*f-y*sp],
		[y*x*f-z*sp, y**2*f+cp, y*z*f+x*sp],
		[z*x*f+y*sp, z*y*f-x*sp, z**2*f+cp]])


def vabs(naVec):
	return math.sqrt(numarray.dot(naVec, naVec))


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


class _STCFeatures(object):
	"""a user-opaque object containing metadata on 6-vector conversion.
	"""
	posGiven = False
	distGiven = False
	posdGiven = False
	distdGiven = False
	relativistic = False
	slaComp = False


class _STCFeaturesAll(object):
	"""a user-opaque object containing metadata on 6-vector conversion.
	"""
	posGiven = distGiven = posdGiven = distdGiven = True
	relativistic = slaComp = False



# Units spherical coordinates have to be in for transformation to/from
# 6-vectors.
_svPosUnit = ("rad", "rad", "AU")
_svVPosUnit = ("rad", "rad", "AU")
_svVTimeUnit = ("d", "d", "d")
# Light speed in AU/d
_lightAUd = 86400.0/499.004782
	

def _svToSpherRaw(sv):
	"""returns spherical position and velocity vectors for the cartesian
	6-vector sv.

	This is a helper for svToSpher.

	This is based on SOFA's pv2s; the units here are given by the _rawSpherSTC
	object above; this will only work if the input of spherToSV had the
	standard coordinates.
	"""
	x, y, z, xd, yd, zd = sv
	rInXY2 = x**2+y**2
	r2 = rInXY2+z**2
	rw = rTrue = math.sqrt(r2)

	if rTrue==0.:  # pos is null: use velocity for position
		x, y, z = sv[3:]
		rInXY2 = x**2+y**2
		r2 = rInXY2+z**2
		rw = math.sqrt(r2)

	rInXY = math.sqrt(rInXY2)
	xyp = x*xd+y*yd
	radialVel = 0
	if rw!=0:
		radialVel = xyp/rw+z*zd/rw
	
	if rInXY2!=0.:
		theta = math.atan2(y, x)
		if abs(theta)<1e-12: # null out to avoid wrapping to 2 pi
			theta = 0
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


def _pleaseEinsteinToSpher(sv):
	"""undoes relativistic corrections from 6-vector sv.

	This follows sofa's pvstar.  sv is changed in place.
	"""
	radialProj, radialV, tangentialV = _decomposeRadial(sv[:3], sv[3:])
	betaRadial = radialProj/_lightAUd
	betaTangential = vabs(tangentialV)/_lightAUd

	d = 1.0+betaRadial
	w = 1.0-betaRadial**2-betaTangential**2
	if d==0.0 or w<0:
		return
	delta = math.sqrt(w)-1.0
	if betaRadial==0:
		radialV = (betaRadial-delta)/(betaRadial*d)*radialV
	sv[3:] = 1/d*radialV


def svToSpher(sv, baseSTC, features=_STCFeaturesAll()):
	"""returns an STC object like baseSTC, but with the values of the 6-vector 
	sv filled in.
	"""
	if features.relativistic:
		_pleaseEinsteinToSpher(sv)
	bPlace, bVel = baseSTC.place, baseSTC.velocity
	pos, vel = _svToSpherRaw(sv)
	buildArgs = {}

	if bPlace and features.posGiven:
		if bPlace.frame.nDim==2:
			pos, unit = pos[:2], _svPosUnit[:2]
		else:
			unit = _svPosUnit
		conv = units.getVectorConverter(unit, baseSTC.place.unit)
		buildArgs["place"] = bPlace.change(value=conv(pos))

	if bVel and features.posdGiven:
		if bVel.frame.nDim==2:
			pos, unit, tUnit = pos[:2], _svVPosUnit[:2], _svVTimeUnit[:2]
		else:
			unit, tUnit = _svVPosUnit, _svVTimeUnit
		conv = units.getVelocityConverter(unit, tUnit, baseSTC.velocity.unit,
			baseSTC.velocity.velTimeUnit)
		buildArgs["velocity"] = bVel.change(value=conv(vel))
	return baseSTC.change(**buildArgs)

# filled in for distances not given, in rad (units also insert this for
# parallaxes too small)
defaultDistance = units.maxDistance*units.onePc/units.oneAU
_nAN = float("NaN")

def _getSVSphericals(stcObject):
	"""returns (space, vel) from stcObject in units suitable for generation
	of 6-cartesian vectors.

	"Sane" defaults are inserted for missing values.

	This is a helper for spherToSV.
	"""
	features = _STCFeatures()
	space, vel = (0, 0, defaultDistance), (0, 0, 0)
	bPlace, bVel = stcObject.place, stcObject.velocity

	if bPlace and bPlace.value:
		_ensureSphericalFrame(bPlace)
		space, srcUnit = bPlace.value, bPlace.unit
		features.posGiven = True
		if bPlace.frame.nDim==2:
			space = space+(defaultDistance,)
			srcUnit = srcUnit+_svPosUnit[-1:]
		else:
			features.distGiven = True
		space = units.getVectorConverter(srcUnit, _svPosUnit)(space)
	if bVel and bVel.value:
		_ensureSphericalFrame(bVel)
		vel = bVel.value
		srcUnit, srcUnitT = bVel.unit, bVel.velTimeUnit
		features.posdGiven = True
		if bVel.frame.nDim==2:
			vel = vel+(0,)
			srcUnit = srcUnit+_svVPosUnit[-1:]
			srcUnitT = srcUnitT+_svVTimeUnit[-1:]
		else:
			features.distdGiven = True
		vel = units.getVelocityConverter(srcUnit, srcUnitT,
			_svVPosUnit, _svVTimeUnit)(vel)
	return features, space, vel


def _decomposeRadial(r, rd):
	"""returns the components of rd radial and tangential to r.
	"""
	rUnit = r/vabs(r)
	radialProj = numarray.dot(rUnit, rd)
	radialVector = radialProj*rUnit
	tangentialVector = rd-radialVector
	return radialProj, radialVector, tangentialVector


def _solveStumpffEquation(betaR, betaT, maxIter=100):
	"""returns the solution of XXX.

	If the solution fails to converge within maxIter iterations, it
	raises an STCError.
	"""
	curEstR, curEstT = betaR, betaT
	odd, oddel = 0, 0
	for i in range(maxIter):
		d = 1.+curEstT
		delta = math.sqrt(1.-curEstR**2-curEstT**2)-1.0
		curEstR = d*betaR+delta
		curEstT = d*betaT
		if i: # check solution so far after at least one iteration
			dd = abs(d-od)
			ddel = abs(delta-odel)
			if dd==odd and ddel==oddel:
				break
			odd = dd
			oddel = ddel
		od = d
		odel = delta
	else:
		raise STCError("6-vector relativistic correction failed to converge")
	return curEstR, curEstT, d, delta


def _pleaseEinsteinFromSpher(sv):
	"""applies relativistic corrections to the 6-vector sv.

	This follows sofa's starpv.  sv is changed in place.
	"""
	radialProj, radialV, tangentialV = _decomposeRadial(sv[:3], sv[3:])
	betaRadial = radialProj/_lightAUd
	betaTangential = vabs(tangentialV)/_lightAUd

	betaSR, betaST, d, delta = _solveStumpffEquation(betaRadial, betaTangential)
	# replace old velocity with velocity in inertial system
	if betaSR!=0:
		radialV = (d+delta/betaSR)*radialV
	sv[3:] = radialV+(d*tangentialV)


def spherToSV(stcObject, relativistic=False):
	"""returns a 6-vector of cartesian place and velocity from stcObject.

	stcObject must be in spherical coordinates.  If any of parallax,
	proper motions, and radial velocity are missing, "sane" defaults
	are substituted.

	This is basically a port of sofa's s2pv, with some elements of starpv.

	relativistic=True applies relativistic corrections on the transformation.
	Don't use this (yet), since for typical cases there are massive problems 
	with the numerics here.
	"""
	features, (alpha, delta, r), (alphad, deltad, rd
		) = _getSVSphericals(stcObject)
	sa, ca = math.sin(alpha), math.cos(alpha)
	sd, cd = math.sin(delta), math.cos(delta)
	x, y = r*cd*ca, r*cd*sa
	w = r*deltad*sd-cd*rd

	res = numarray.array([x, y, r*sd,
		-y*alphad-w*ca, x*alphad-w*sa, r*deltad*cd+sd*rd])
	features.relativistic = relativistic
	if relativistic:
		_pleaseEinsteinFromSpher(res)
	return features, res


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
