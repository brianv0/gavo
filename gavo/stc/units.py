"""
Definition and conversion of units in STC

For every physical quantity, there is a standard unit defined:

* angles: deg  (we way want to use rad here)
* distances: m
* time: s

We keep dictionaries of conversion factors to those units (i.e., multiply
them to values to end up in the standard units).  The converters work
accordingly: getXFactor(fromU, toU) will return a number that converts a number
from fromU to toU by multiplication.

The main interface are functions returning converter functions.  Pass
a value in fromUnit to them and receive a value in toUnit.  Simple factors
unfortunately don't cut it here since conversion from wavelength to
frequency needs division of the value.
"""

from itertools import *
import math

from gavo.stc.common import *


toRad=math.pi/180.
oneAU = 1.49597870691e11   # IAU
onePc = oneAU/2/math.tan(0.5/3600*toRad)
lightspeed = 2.99792458e8  # SI
planckConstant = 4.13566733e-15  # CODATA 2008, in eV s
julianYear = 365.25*24*3600


def makeConverterMaker(label, conversions):
	"""returns a conversion function that converts between any of the units
	mentioned in the dict conversions.
	"""
	def getConverter(fromUnit, toUnit):
		if fromUnit not in conversions or toUnit not in conversions:
			raise STCUnitError("One of '%s' or '%s' is no valid %s unit"%(
				fromUnit, toUnit, label))
		fact = conversions[toUnit]/conversions[fromUnit]
		def convert(val):
			return fact*val
		return convert
	return getConverter

distFactors = {
	"m": 1.,
	"km": 1e-3,
	"mm": 1e3,
	"AU": 1/oneAU,  
	"pc": 1/onePc,
	"kpc": 1/(1e3*onePc),
	"Mpc": 1/(1e6*onePc),
	"lyr": 1/(lightspeed*julianYear),
}
getDistConv = makeConverterMaker("distance", distFactors)


angleFactors = {
	"deg": 1.,
	"rad": toRad,
	"h": 24./360.,
	"arcmin": 60.,
	"arcsec": 3600.,
}
getAngleConv = makeConverterMaker("angle", angleFactors)


timeFactors = {
	"s": 1.,
	"h": 1/3600.,
	"d": 1/(3600.*24),
	"a": 1/julianYear,
	"yr": 1/julianYear,
	"cy": 1/(julianYear*100),
}
getTimeConv = makeConverterMaker("time", timeFactors)


# spectral units have the additional intricacy that a factor is not
# enough when wavelength needs to be converted to a frequency.
freqFactors = {
	"Hz": 1,
	"kHz": 1e-3,
	"MHz": 1e-6,
	"GHz": 1e-9,
	"eV": planckConstant,
	"keV": planckConstant/1e3,
	"MeV": planckConstant/1e6,
	"GeV": planckConstant/1e9,
	"TeV": planckConstant/1e12,
}
getFreqConv = makeConverterMaker("frequency", freqFactors)

wlFactors = {
	"m": 1.0,
	"mm": 1e3,
	"um": 1e6,
	"nm": 1e9,
	"Angstrom": 1e10,
}
getWlConv = makeConverterMaker("wavelength", wlFactors)

def getSpectralConv(fromUnit, toUnit):
	if fromUnit in wlFactors:
		if toUnit in wlFactors:
			conv = getWlConv(fromUnit, toUnit)
		else: # toUnit is freq
			fromFunc = getWlConv(fromUnit, "m")
			toFunc = getFreqConv("Hz", toUnit)
			def conv(val):
				return toFunc(lightspeed/fromFunc(val))
	else:  # fromUnit is freq
		if toUnit in freqFactors:
			conv = getFreqConv(fromUnit, toUnit)
		else:  # toUnit is wl
			fromFunc = getFreqConv(fromUnit, "Hz")
			toFunc = getWlConv("m", toUnit)
			def conv(val):
				return toFunc(lightspeed/fromFunc(val))
	return conv


distUnits = set(distFactors) 
angleUnits = set(angleFactors)
timeUnits = set(timeFactors)
spectralUnits = set(wlFactors) | set(freqFactors)

systems = [(distUnits, getDistConv), (angleUnits, getAngleConv),
	(timeUnits, getTimeConv), (spectralUnits, getSpectralConv)]

def identity(x):
	return x


def memoized(origFun):
	cache = {}
	def fun(*args):
		if args not in cache:
			cache[args] = origFun(*args)
		return cache[args]
	return fun


@memoized
def getScalarConverter(fromUnit, toUnit):
	"""returns a function converting fromUnit values to toUnitValues.
	"""
	for units, factory in systems:
		if fromUnit in units and toUnit in units:
			return factory(fromUnit, toUnit)
	raise STCUnitError("No known conversion from '%s' to '%s'"%(
		fromUnit, toUnit))

@memoized
def getRedshiftConverter(spaceUnit, timeUnit, toUnits):
	"""returns a function converting redshifts in spaceUnit/timeUnit to
	toUnits.

	toUnits is a 2-tuple of (spaceUnit, timeUnit).  This will actually work
	for any unit of the form unit1/unit2 as long as unit2 is purely 
	multiplicative.
	"""
	try:
		toSpace, toTime = toUnits
	except ValueError:
		raise STCUnitError("%s is not a valid target unit for redshifts"%toUnits)
	spaceFun = getScalarConverter(spaceUnit, toSpace)
# Attention: We swap from and to here.  In reality, we'd have to be much
# more careful since inversion only does what we need if inversion and
# division are the same thing -- fortunately, for the units we care about
# here that's the case.
	timeFun = getScalarConverter(toTime, timeUnit)
	def convert(val):
		return spaceFun(timeFun(val))
	return convert


def _expandUnits(fromUnits, toUnits):
	"""makes sure fromUnits and toUnits have the same length.

	This is a helper for vector converters.
	"""
	if isinstance(toUnits, basestring):
		toUnits = (toUnits,)*len(fromUnits)
	if len(fromUnits)!=len(toUnits):
		raise STCUnitError("Values in %s cannot be converted to values in %s"%(
			fromUnits, toUnits))
	return toUnits

@memoized
def getVectorConverter(fromUnits, toUnits):
	"""returns a function converting from fromUnits to toUnits.

	fromUnits is a tuple, toUnits may be a tuple or a single string; in the
	latter case, all components are supposed to be of that unit.

	The resulting functions accepts sequences of proper length and returns
	tuples.
	"""
	toUnits = _expandUnits(fromUnits, toUnits)
	convs = tuple(getScalarConverter(f, t) 
		for f, t in izip(fromUnits, toUnits))
	def convert(val):
		return tuple(f(c) for f, c in izip(convs, val))
	return convert


@memoized
def getVelocityConverter(fromSpaceUnits, fromTimeUnits, toUnits):
	"""returns a function converting from fromSpaceUnits/fromTimeUnits to
	toUnits.

	fromXUnits is a tuple, toUnits may be a tuple, where each item may be
	a tuple of length fromXUnits or a a single string like in getVectorUnits.
	Spatial units come first, temporal units last.

	The resulting functions accepts sequences of proper length and returns
	tuples.
	"""
	try:
		toSpace, toTime = toUnits
	except ValueError:
		raise STCUnitError("%s is not a valid target unit for velocities"%toUnits)
	toSpace = _expandUnits(fromSpaceUnits, toSpace)
	toTime = _expandUnits(fromTimeUnits, toTime)
	convs = tuple(getRedshiftConverter(fs, ft, (ts, tt)) 
		for fs, ft, ts, tt in izip(fromSpaceUnits, fromTimeUnits, toSpace, toTime))
	def convert(val):
		return tuple(f(c) for f, c in izip(convs, val))
	return convert
