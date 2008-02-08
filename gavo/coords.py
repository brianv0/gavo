"""
This module contains code to handle coordinate systems and transform
between them.
"""

import gavo
from gavo import utils
from math import sin, cos, pi
import math

import _gavoext


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
		for id, system in self.systems.items():
			yield (id,)+system.getSystem()
	
	def defineSystem(self, equinox="J2000", epoch=None, system="eq.FK5"):
		"""adds a new coordinate system and returns a computed id for it.
		"""
		newId = "coo%03d"%len(self.systems)
		self.defineSystemWithId(newId, equinox, epoch, system)
		return newId
	
	def defineSystemWithId(self, id, equinox, epoch, system):
		self.systems[id] = CooSys(equinox, epoch, system)


def hourangleToDeg(hourAngle, sepChar=" "):
	"""returns the hour angle (h m s.decimals) as a float in degrees.

	>>> "%3.8f"%hourangleToDeg("22 23 23.3")
	'335.84708333'
	>>> "%3.8f"%hourangleToDeg("22:23:23.3", ":")
	'335.84708333'
	>>> "%3.8f"%hourangleToDeg("222323.3", "")
	'335.84708333'
	>>> hourangleToDeg("junk")
	Traceback (most recent call last):
	Error: Invalid hourangle with sepchar ' ': 'junk'
	"""
	try:
		if sepChar=="":
			parts = hourAngle[:2], hourAngle[2:4], hourAngle[4:]
		else:
			parts = hourAngle.split(sepChar)
		if len(parts)==3:
			hours, minutes, seconds = parts
		elif len(parts)==2:
			hours, minutes = parts
			seconds = 0
		else:
			raise ValueError("Too many parts")
		timeSeconds = int(hours)*3600+float(minutes)*60+float(seconds)
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
		if sepChar=="":
			parts = dmsAngle[:2], dmsAngle[2:4], dmsAngle[4:]
		else:
			parts = dmsAngle.split(sepChar)
		if len(parts)==3:
			deg, min, sec = parts
		elif len(parts)==2:
			deg, min = parts
			sec = 0
		else:
			raise ValueError("Invalid # of parts")
		arcSecs = sign*(int(deg)*3600+float(min)*60+float(sec))
	except ValueError:
		raise gavo.Error("Invalid dms declination with sepchar %s: %s"%(
			repr(sepChar), repr(dmsAngle)))
	return arcSecs/3600


def degToHourangle(deg, sepChar=" ", secondFracs=3):
	"""converts a float angle in degrees to an hour angle.
	>>> degToHourangle(0)
	'0 00 00.000'
	>>> degToHourangle(122.056, secondFracs=1)
	'8 08 13.4'
	>>> degToHourangle(359.2222, secondFracs=4, sepChar=":")
	'23:56:53.3280'
	>>> "%.4f"%hourangleToDeg(degToHourangle(256.25, secondFracs=9))
	'256.2500'
	"""
	rest, hours = math.modf(deg/360.*24)
	rest, minutes = math.modf(rest*60)
	return sepChar.join(["%d"%int(hours), "%02d"%int(minutes), 
		"%0*.*f"%(secondFracs+3, secondFracs, rest*60)])


def degToDms(deg, sepChar=" ", secondFracs=2):
	"""converts a float angle in degrees to a sexagesimal string.
	>>> degToDms(0)
	'+0 00 00.00'
	>>> degToDms(-23.50, secondFracs=4)
	'-23 30 00.0000'
	>>> "%.4f"%dmsToDeg(degToDms(-25.6835, sepChar=":"), sepChar=":")
	'-25.6835'
	"""
	rest, degs = math.modf(deg)
	rest, minutes = math.modf(rest*60)
	return sepChar.join(["%+d"%int(degs), "%02d"%abs(int(minutes)), 
		"%0*.*f"%(secondFracs+3, secondFracs, abs(rest*60))])


_wcsTestDict = {
	"CRVAL1": 0,   "CRVAL2": 0, "CRPIX1": 50,  "CRPIX2": 50,
	"CD1_1": 0.01, "CD1_2": 0, "CD2_1": 0,    "CD2_2": 0.01,
	"NAXIS1": 100, "NAXIS2": 100, "CUNIT1": "deg", "CUNIT2": "deg",
}


def getBbox(points):
	"""returns a bounding box for the sequence of 2-sequences points.

	The thing returned is a coords.Box.

	>>> getBbox([(0.25, 1), (-3.75, 1), (-2, 4)])
	Box(((0.25,4), (-3.75,1)))
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


def getWCSTrafo(wcsFields):
	"""returns a callable transforming pixel to physical coordinates.

	XXX TODO: This doesn't yet evaluate the projection.
	XXX TODO: This doesn't do anything sensible on the poles.
	"""
	if wcsFields["CUNIT1"].strip()!="deg" or wcsFields["CUNIT2"].strip()!="deg":
		raise Error("Can only handle deg units")

	def ptte(val):
		return float(val)

	alpha, delta = float(wcsFields["CRVAL1"]), float(wcsFields["CRVAL2"])
	refpixX, refpixY = float(wcsFields["CRPIX1"]), float(wcsFields["CRPIX2"])
	caa, cad = ptte(wcsFields["CD1_1"]), ptte(wcsFields["CD1_2"]) 
	cda, cdd = ptte(wcsFields["CD2_1"]), ptte(wcsFields["CD2_2"]) 

	def pixelToSphere(x, y):
		return (alpha+(x-refpixX)*caa+(y-refpixY)*cad,
			clampDelta(delta+(x-refpixX)*cda+(y-refpixY)*cdd))
	return pixelToSphere


def getInvWCSTrafo(wcsFields):
	"""returns a callable transforming physical to pixel coordinates.

	XXX TODO: see getWCSTrafo.
	"""
	if wcsFields["CUNIT1"].strip()!="deg" or wcsFields["CUNIT2"].strip()!="deg":
		raise Error("Can only handle deg units")

	def ptte(val):
		"""parses an element of the transformation matrix.
		"""
		return float(val)

	alphaC, deltaC = float(wcsFields["CRVAL1"]), float(wcsFields["CRVAL2"])
	refpixX, refpixY = float(wcsFields["CRPIX1"]), float(wcsFields["CRPIX2"])
	caa, cad = ptte(wcsFields["CD1_1"]), ptte(wcsFields["CD1_2"]) 
	cda, cdd = ptte(wcsFields["CD2_1"]), ptte(wcsFields["CD2_2"]) 
	norm = 1/float(caa*cdd-cad*cda)

	def sphereToPixel(alpha, delta):
		ap, dp = (alpha-alphaC), (delta-deltaC)
		return (ap*cdd-dp*cad)*norm+refpixX, (-cda*ap+caa*dp)*norm+refpixY
	return sphereToPixel


def getCornerPointsFromWCSFields(wcsFields):
	"""returns the corner points of the field defined by (fairly plain)
	WCS values in the dict wcsFields.

	>>> d = _wcsTestDict.copy()
	>>> map(str, getCornerPointsFromWCSFields(d)[0])
	['-0.5', '-0.5']
	>>> d["CRVAL1"] = 50; map(str, getCornerPointsFromWCSFields(d)[0])
	['49.5', '-0.5']
	>>> d["CRVAL2"] = 30; map(str, getCornerPointsFromWCSFields(d)[0])
	['49.5', '29.5']
	"""
	pixelToSphere = getWCSTrafo(wcsFields)
	width, height = float(wcsFields.get("NAXIS1", 2030)), float(
			wcsFields.get("NAXIS2", "800"))
	cornerPoints = [pixelToSphere(0, 0),
		pixelToSphere(0, height), pixelToSphere(width, 0),
		pixelToSphere(width, height)]
	return cornerPoints


def getBboxFromWCSFields(wcsFields):
	"""returns a cartesian bbox and a field center for (fairly simple) WCS
	FITS header fields.
	"""
	return getBbox(getCornerPointsFromWCSFields(wcsFields))


def getCenterFromWCSFields(wcsFields):
	"""returns RA and Dec of the center of an image described by wcsFields.
	"""
	pixelToSphere = getWCSTrafo(wcsFields)
	return pixelToSphere(float(wcsFields.get("NAXIS1", 2030))/2., float(
			wcsFields.get("NAXIS2", "800"))/2.)


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
	def sety(self, y): self.coos[1] = x
	y = property(gety, sety)
	def getz(self): return self.coos[2]
	def setz(self, z): self.coos[2] = z
	z = property(getz, setz)


class Box(object):
	"""is a 2D box.

	The can be constructed either with two tuples, giving two points
	delimiting the box, or with four arguments x0, x1, y0, y1.

	To access the thing, you can either access the x[01], y[01] attributes
	or use getitem to retrieve the upper right and lower left corner.

	The slightly silly ordering of the bounding points (larger values
	first) is for consistency with Postgresql.

	Boxes can be serialized to/from Postgresql BOXes.

	>>> b1 = Box(0, 1, 0, 1)
	>>> b2 = Box((0.5, 0.5), (1.5, 1.5))
	>>> b1.overlaps(b2)
	True
	>>> b2.contains(b1)
	False
	>>> b2.contains(None)
	False
	>>> b2[0]
	(1.5, 1.5)
	"""
	def __init__(self, x0, x1, y0=None, y1=None):
		if y0==None:
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
		return "((%g,%g), (%g,%g))"%(self.x0, self.y0, self.x1, self.y1)

	def __repr__(self):
		return "Box(%s)"%str(self)

	def overlaps(self, other):
		if other==None:
			return False
		return not (
			(self.x1>other.x0 or self.x0<other.x1) or
			(self.y1>other.y0 or self.y0<other.y1))

	def contains(self, other):
		if other==None:
			return False
		if isinstance(other, Box):
			return (self.x0>=other.x0 and self.x1<=other.x1 and
				self.y0>=other.y0 and self.y1<=other.y1)
		else: # other is assumed to be a 2-sequence interpreted as a point.
			x, y = other
			return self.x0>=x>=self.x1 and self.y0>=y>=self.y1
	
	def translate(self, vec):
		dx, dy = vec
		return Box((self.x0+dx, self.y0+dy), (self.x1+dx, self.y1+dy))


def sgn(a):
	if a<0:
		return -1
	elif a>0:
		return 1
	else:
		return 0


def computeUnitSphereCoords(alpha, delta):
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
	alpha, delta = utils.degToRad(alpha), utils.degToRad(delta)
	return Vector3(cos(alpha)*cos(delta),
		sin(alpha)*cos(delta),
		sin(delta))


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


try:
	import ephem

	_sysConverters = {
		("J2000", "B1950"): _gavoext.fk524,
	}

	def convertSys(alpha, delta, srcEq, destEq):
		"""returns alpha and delta in the destination Equinox.

		alpha and delta must be degrees, srcEq and destEq must come from
		a controlled vocabulary (like "J2000" or "B1950"); see _sysConverters.
		>>> "%.4f %.4f"%convertSys(82.1119567, -74.962704, "J2000", "B1950")
		'82.5000 -75.0000'
		>>> "%.4f %.4f"%convertSys(100.29064705, -20.048423505, "J2000", "B1950")
		'99.7500 -20.0000'
		"""
		try:
			return _sysConverters[srcEq, destEq](alpha, delta)
		except KeyError:
			raise gavo.Error("Don't know how to transform from %s to %s"%(
				srcEq, destEq))

except ImportError:  # pyephem not available
	pass


def _test():
	import doctest, coords
	doctest.testmod(coords)


if __name__=="__main__":
	_test()
