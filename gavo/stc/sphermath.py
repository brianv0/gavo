"""
Spherical geometry and related helper functions.
"""

import math
import new
import numarray

from gavo import utils
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
	if not coo.frame.isSpherical():
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


def svToSpher(sv, features=InputFeaturesAll):
	"""returns spherical pos, vel coordinates and their units for the 6-vector
	sv.

	features must be the first item of the return value of spherToSv.  Items
	will be None (or, in the case of distance and rv, missing) if they were not 
	present in the input.

	What is actually returned is a quintuple of
	position, position unit, velocity, velocity spatial unit, velocity time
	unit.

	position and velocity may be None; even in this case, the units
	are available.
	"""
	if features.relativistic:
		_pleaseEinsteinToSpher(sv)
	pos, vel = _svToSpherRaw(sv)
	if features.distGiven:
		posUnit = _svPosUnit
	else:
		pos, posUnit = pos[:2], _svPosUnit[:2]
	if features.distdGiven:
		velSUnit, velTUnit = _svVPosUnit, _svVTimeUnit
	else:
		vel, velSUnit, velTUnit = vel[:2], _svVPosUnit[:2], _svVTimeUnit[:2]
	if not features.posdGiven:
		vel = None
	return pos, posUnit, vel, velSUnit, velTUnit


def svToSpherUnits(sv, toSpaceUnit, toVelSUnit, toVelTUnit,
		features=InputFeaturesAll):
	pos, posUnit, vel, velSUnit, velTUnit = svToSpher(sv, features)
	posD, velD = len(toSpaceUnit), len(toVelSUnit)
	fixSpaceUnit = units.getVectorConverter(posUnit[:posD], toSpaceUnit)
	fixVelUnit = units.getVelocityConverter(velSUnit[:velD], velTUnit[:velD],
		toVelSUnit, toVelTUnit)
	return fixSpaceUnit(pos), fixVelUnit(vel)
	

# filled in for distances not given, in rad (units also insert this for
# parallaxes too small)
defaultDistance = units.maxDistance*units.onePc/units.oneAU
_nAN = float("NaN")

def _getSVSphericals(stcObject, features):
	"""returns (space, vel) from stcObject in units suitable for generation
	of 6-cartesian vectors.

	"Sane" defaults are inserted for missing values.

	This is a helper for spherToSV.
	"""
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
	return space, vel


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


def spherToSV(stcObject, features):
	"""returns a 6-vector of cartesian place and velocity from stcObject.

	stcObject must be in spherical coordinates.  If any of parallax,
	proper motions, and radial velocity are missing, "sane" defaults
	are substituted.

	This is basically a port of sofa's s2pv, with some elements of starpv.

	Features is a common.InputFeatures instance that will be updated
	to reflect what is given in stcObject (Yikes!).
	"""
	(alpha, delta, r), (alphad, deltad, rd
		) = _getSVSphericals(stcObject, features)
	sa, ca = math.sin(alpha), math.cos(alpha)
	sd, cd = math.sin(delta), math.cos(delta)
	x, y = r*cd*ca, r*cd*sa
	w = r*deltad*sd-cd*rd

	res = numarray.array([x, y, r*sd,
		-y*alphad-w*ca, x*alphad-w*sa, r*deltad*cd+sd*rd])
	if features.relativistic:
		_pleaseEinsteinFromSpher(res)
	return res


class SVConverter(object):
	"""A container for the conversion from spherical coordinates
	to 6-Vectors.

	You create one with an example of your data; these are values
	and units of STC objects, and everything may be None if it's
	not given.

	The resulting object has methods to6 taking values
	like the one provided by you and returning a 6-vector, and from6
	returning a pair of such values.

	Further, the converter has the attributes	distGiven,
	posdGiven, and distdGiven signifying whether these items are
	expected or valid on return.  If posVals is None, no transforms
	can be computed.

	The relativistic=True constructior argument requests that the
	transformation be Lorentz-invariant.  Do not use that, though,
	since there are unsolved numerical issues.

	The slaComp=True constructor argument requests that some
	operations exterior to the construction are done as slalib does
	them, rather than alternative approaches.
	"""
	posGiven = distGiven = posdGiven = distdGiven = True
	defaultDistance = units.maxDistance*units.onePc/units.oneAU

	def __init__(self, posVals, velVals, posUnit, velSUnit, velTUnit,
			relativistic=False, slaComp=False):
		self.relativistic, self.slaComp = relativistic, slaComp
		self._determineFeatures(posVals, velVals)
		self._computeUnitConverters(posUnit, velSUnit, velTUnit)
		self._makeTo6()
		self._makeFrom6()

	def _determineFeatures(self, posVals, velVals):
		if posVals is None:
			raise STCValueError("No conversion possible without a position.")
		if len(posVals)==2:
			self.distGiven = False
		if velVals is None:
			self.posdGiven = False
		else:
			if len(velVals)==2:
				self.distdGiven = False

	def _computeUnitConverters(self, posUnit, velSUnit, velTUnit):
		dims = len(posUnit)
		self.toSVUnitsPos = units.getVectorConverter(posUnit, 
			_svPosUnit[:dims])
		self.fromSVUnitsPos = units.getVectorConverter(posUnit, 
			_svPosUnit[:dims], True)
		if self.posdGiven:
			dims = len(velSUnit)
			self.toSVUnitsVel = units.getVelocityConverter(velSUnit, velTUnit,
				_svVPosUnit[:dims], _svVTimeUnit[:dims])
			self.fromSVUnitsVel = units.getVelocityConverter(velSUnit, velTUnit,
				_svVPosUnit[:dims], _svVTimeUnit[:dims], True)

	def _makeTo6(self):
		code = ["def to6(self, pos, vel):"]
		code.append("  pos = self.toSVUnitsPos(pos)")
		if self.posdGiven:
			code.append("  vel = self.toSVUnitsVel(vel)")
		if not self.distGiven:
			code.append("  pos = pos+(defaultDistance,)")
		if self.posdGiven:
			if not self.distdGiven:
				code.append("  vel = vel+(0,)")
		else:
			code.append("  vel = (0,0,0)")
		code.append("  (alpha, delta, r), (alphad, deltad, rd) = pos, vel")
		code.append("  sa, ca = math.sin(alpha), math.cos(alpha)")
		code.append("  sd, cd = math.sin(delta), math.cos(delta)")
		code.append("  x, y = r*cd*ca, r*cd*sa")
		code.append("  w = r*deltad*sd-cd*rd")
		code.append("  res = numarray.array([x, y, r*sd,"
			" -y*alphad-w*ca, x*alphad-w*sa, r*deltad*cd+sd*rd])")
		if self.relativistic:
			code.append("  _pleaseEinsteinFromSpher(res)")
		code.append("  return res")
		l = locals()
		exec "\n".join(code) in globals() , l
		self.to6 = new.instancemethod(l["to6"], self)

	def _makeFrom6(self):
		code = ["def from6(self, sv):"]
		if self.relativistic:
			code.append("  _pleaseEinsteinFromSpher(sv)")
		code.append("  pos, vel = _svToSpherRaw(sv)")
		if not self.distGiven:
			code.append("  pos = pos[:2]")
		code.append("  pos = self.fromSVUnitsPos(pos)")
		if self.posdGiven:
			if not self.distdGiven:
				code.append("  vel = vel[:2]")
			code.append("  vel = self.fromSVUnitsVel(vel)")
		else:
			code.append("  vel = None")
		code.append("  return pos, vel")
		l = locals()
		exec "\n".join(code) in globals() , l
		self.from6 = new.instancemethod(l["from6"], self)

		


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


def makePlainSphericalTransformer(trafoFunc, origUnit):
	"""returns a function that applies trafoMatrix to 2-spherical coordinates
	given in units.

	This is mainly a helper to transform geometries (other than Convex).
	trafoFunc is a transformation function as used by conform.conform,
	units are the units of the geometry.

	Here, we assume the given points have no motion at all, we discard
	all motions that would result from transformations, and the distance
	is unit (where that matters).
	"""
	toCartUnits = units.getVectorConverter(origUnit, ("rad", "rad"))
	fromCartUnits = units.getVectorConverter(("rad", "rad"), origUnit)
	def trafoPlain(coos):
		sv = numarray.array(spherToCart(*toCartUnits(coos))+(0,0,0))
		resVec = trafoFunc(sv, InputFeaturesPosOnly)[:3]
		return fromCartUnits(cartToSpher(resVec/vabs(resVec)))
	return trafoPlain
