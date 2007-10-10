"""
This module contains code to handle coordinate systems and transform
between them.
"""

import gavo
from gavo import utils
from math import sin, cos, pi
import math


class CooSys:
	"""models a single coordinate system.

	Apart from the equinox, all items are optional and will be None
	when queried while not set.

	We should probably set system as a default from equinox if not given,
	and default epoch from equinox if not given, but then again we'd have
	to have some way to say "unknown" or "from table" if we did this.
	"""
	def __init__(self, equinox, epoch=None, system=None):
		self.equinox = equinox
		self.epoch, self.system = epoch, system
	
	def getSystem(self):
		"""returns a three-tuple (equinox, epoch, system), where None
		is a possible value for both epoch and system when not known.
		"""
		return self.equinox, self.epoch, self.system


class CooSysRegistry:
	"""is a collection of coordinate systems.
	"""
	def __init__(self):
		self.systems = {}
	
	def __iter__(self):
		"""iterates over tuples of (id, equ, epoch, system).
		"""
		for id, system in self.systems:
			yield (id,)+system.getSystem()
	
	def defineSystem(self, equinox, epoch, system):
		"""adds a new coordinate system and returns a computed id for it.
		"""
		newId = "coo%03d"%len(self.systems)
		self.defineSystemWithId(newId, equinox, epoch, system)
		return newId
	
	def defineSystemWithId(self, id, equinox, epoch, system):
		self.systems[id] = CooSys(equinox, epoch, system)


def hourangleToDeg(hourAngle, sepChar=None):
	"""returns the hour angle (h m s.decimals) as a float in degrees.

	>>> "%3.8f"%hourangleToDeg("22 23 23.3")
	'335.84708333'
	>>> "%3.8f"%hourangleToDeg("22:23:23.3", ":")
	'335.84708333'
	>>> hourangleToDeg("junk")
	Traceback (most recent call last):
	Error: Invalid hourangle with sepchar None: 'junk'
	"""
	try:
		hours, minutes, seconds = hourAngle.split(sepChar)
		timeSeconds = int(hours)*3600+int(minutes)*60+float(seconds)
	except ValueError:
		raise gavo.Error("Invalid hourangle with sepchar %s: %s"%(
			repr(sepChar), repr(hourAngle)))
	return timeSeconds/3600/24*360


def dmsToDeg(dmsAngle, sepChar=" "):
	"""returns the degree minutes seconds-specified dmsAngle as a 
	float in degrees.

	>>> "%3.8f"%dmsToDeg("45 30.6")
	'45.51000000'
	>>> "%3.8f"%dmsToDeg("45:30.6", ":")
	'45.51000000'
	>>> "%3.8f"%dmsToDeg("-45 30 7.6")
	'-45.50211111'
	>>> dmsToDeg("junk")
	Traceback (most recent call last):
	Error: Invalid dms declination with sepchar ' ': 'junk'
	"""
	sign = 1
	if dmsAngle.startswith("+"):
		dmsAngle = dmsAngle[1:].strip()
	elif dmsAngle.startswith("-"):
		sign, dmsAngle = -1, dmsAngle[1:].strip()
	try:
		try:
			deg, min, sec = dmsAngle.split(sepChar)
		except ValueError:  # only deg and min given
			deg, min = dmsAngle.split(sepChar)
			sec = 0
		arcSecs = sign*(int(deg)*3600+float(min)*60+float(sec))
	except ValueError:
		raise gavo.Error("Invalid dms declination with sepchar %s: %s"%(
			repr(sepChar), repr(dmsAngle)))
	return arcSecs/3600


def computeUnitSphereCoords(alpha, delta):
	"""returns the 3d coordinates of the intersection of the direction
	vector given by the spherical coordinates alpha and delta with the
	unit sphere.

	alpha and delta are given in degrees.
	"""
	alpha, delta = utils.degToRad(alpha), utils.degToRad(delta)
	return Vector3(cos(alpha)*cos(delta),
		sin(alpha)*cos(delta),
		sin(delta))


# let's do a tiny vector type.  It's really not worth getting some dependency
# for this.
class Vector3(object):
	def __init__(self, x, y=None, z=None):
		if isinstance(x, tuple):
			self.coos = x
		else:
			self.coos = (x, y, z)

	def __str__(self):
		return "[%s,%s,%s]"%tuple(self.coos)

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

	def __add__(self, other):
		return Vector3(self.x+other.x, self.y+other.y, self.z+other.z)

	def __sub__(self, other):
		return Vector3(self.x-other.x, self.y-other.y, self.z-other.z)

	def cross(self, other):
		return Vector3(self.y*other.z-self.z*other.y,
			self.z*other.x-self.x*other.z,
			self.x*other.y-self.y*other.x)

	def getx(self): return self.coos[0]
	def setx(self, x): self.coos[0] = x
	x = property(getx, setx)
	def gety(self): return self.coos[1]
	def sety(self, y): self.coos[1] = x
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


def getTangentialUnits(cPos):
	"""returns the unit vectors for RA and Dec at the unit circle position cPos.

	We compute them by solving u_1*p_1+u_2*p_2=0 (we already know that
	u_3=0) simultaneously with u_1^2+u_2^2=1 for RA, and by computing the
	cross product of the RA unit and the radius vector for dec.

	This becomes degenerate at the poles.  If we're exactly on a pole,
	we *define* the unit vectors as (1,0,0) and (0,1,0).
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
		if deltaUnit.cross(alphaUnit)*cPos>0:
			alphaUnit = -1*alphaUnit
	else:
		if deltaUnit.cross(alphaUnit)*cPos<0:
			alphaUnit = -1*alphaUnit
	return alphaUnit, deltaUnit


def _test():
	import doctest, coords
	doctest.testmod(coords)


if __name__=="__main__":
	_test()
