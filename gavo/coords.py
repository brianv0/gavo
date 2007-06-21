"""
This module contains code to handle coordinate systems and transform
between them.
"""

import gavo
from gavo import utils
from math import sin, cos


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
	return (cos(alpha)*cos(delta),
		sin(alpha)*cos(delta),
		sin(delta))


def _test():
	import doctest, coords
	doctest.testmod(coords)


if __name__=="__main__":
	_test()
