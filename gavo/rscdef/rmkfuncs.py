"""
Functions available to rowmaker procs.

Rowmaker procs are compiled in the namespace defined by this module.

Maybe we should allow additional modules to be specified in gavorc?
"""

import datetime
import math
import os
import pprint
import re
import sys
import time
import traceback

from gavo import base
from gavo.base import texttricks
from gavo.base import coords
from gavo.base.literals import *


from gavo.base import parseBooleanLiteral


def parseDestWithDefault(dest, defRe=re.compile(r"(\w+)\((.*)\)")):
	"""returns name, default from dests like bla(0).

	This can be used to provide defaulted targets to assignments parsed
	with _parseAssignments.
	"""
	mat = defRe.match(dest)
	if mat:
		return mat.groups()
	else:
		return dest, None


def addCartesian(result, alpha, delta):
	"""inserts c_x, c_y, and c_z for the equatorial position alpha, delta
	into result.

	c_x, c_y, and c_z are the cartesian coordinates of the intersection
	point of the radius vector of alpha, delta with the unit sphere.

	alpha and delta already have to be floats, so you probably want
	to use variables here.

	>>> r = {}; addCartesian(r, 25, 30); str(r["c_x"]), str(r["c_y"])
	('0.784885567221', '0.365998150771')
	"""
	result["c_x"], result["c_y"], result["c_z"] = coords.computeUnitSphereCoords(
		alpha, delta)


def combinePMs(result, pma, pmd):
	"""inserts pm_total (in degs/yr) and pm_posang (in degs, east over north)
	into result.

	pma and pmd have to be in degs/yr, with cos(delta) applied to pma.
	"""
	if pmAlpha is None or pmDelta is None:
		tpm = pmpa = None
	else:
		tpm = math.sqrt(pma**2+pmd**2)
		pmpa = math.atan2(pma, pmd)*360/2/math.pi
	result["pm_total"] = tpm
	result["pm_posang"] = pmpa


def hmsToDeg(literal, sepChar=":"):
	"""returns a literal like hh:mm:ss.sss as a floating point value in degrees.

	sepChar is whatever is between the individual items and defaults to
	the colon.
	"""
	return base.timeangleToDeg(literal)


def dmsToDeg(literal, sepChar=" "):
	"""returns a literal like dd mm ss.ss as a floating point value in degrees.

	sepChar is whatever is between the individualt items and defaults
	to a blank.
	"""
	return base.dmsToDeg(literal, sepChar)


def parseTime(literal, format="%H:%M:%S"):
	"""returns a datetime.timedelta object for literal parsed according
	to format.

	For format, you can the magic values !!secondsSinceMidnight,
	!!decimalHours or a strptime-like spec using the H, M, and S codes.

	>>> parseTime("89930", "!!secondsSinceMidnight")
	datetime.timedelta(1, 3530)
	>>> parseTime("23.4", "!!decimalHours")
	datetime.timedelta(0, 84240)
	>>> parseTime("3.4:5", "%H.%M:%S")
	datetime.timedelta(0, 11045)
	"""
	if format=="!!secondsSinceMidnight":
		return datetime.timedelta(seconds=float(literal))
	elif format=="!!decimalHours":
		return datetime.timedelta(hours=float(literal))
	else:
		# We can't really use prebuilt strptimes since times like 25:21:22.445
		# are perfectly ok in astronomy.
		partDict = texttricks.parsePercentExpression(literal, format)
		return datetime.timedelta(0, hours=float(partDict.get("H", 0)),
			minutes=float(partDict.get("M", 0)), seconds=float(partDict.get("S", 0)))


def parseDate(literal, format="%Y-%m-%d"):
	"""returns a datetime.date object of literal parsed according to the
	strptime-similar format.

	The function understands the special dateFormat !!julianEp 
	(stuff like 1980.89).
	"""
	if format=="!!julianEp":
		rest, year = math.modf(float(literal))
		delta = datetime.timedelta(seconds=rest*365.25*86400)
		return datetime.date(int(year), 1, 1)+delta
	return datetime.date(*time.strptime(literal, format)[:3])


def parseTimestamp(literal, format="%Y-%m-%dT%H:%M:%S"):
	"""returns a datetime.datetime object of literal parsed according to the
	strptime-similar format.
	"""
	return datetime.datetime(*time.strptime(literal, format)[:6])


def makeTimestamp(date, time):
	"""makes a datetime instance from a date and a time.
	"""
	return datetime.datetime(date.year, date.month, date.day)+time


def parseAngle(literal, format):
	"""is a macro that converts the various forms angles might be encountered
	to degrees.

	format is one of hms, dms, fracHour.

	>>> str(parseAngle("23 59 59.95", "hms"))
	'359.999791667'
	>>> "%10.5f"%parseAngle("-20 31 05.12", "dms")
	' -20.51809'
	>>> "%010.6f"%parseAngle("21.0209556", "fracHour")
	'315.314334'
	"""
	if format=="dms":
		return base.dmsToDeg(literal)
	elif format=="hms":
		return base.timeangleToDeg(literal)
	elif format=="fracHour":
		return base.fracHoursToDeg(literal)
	else:
		raise Error("Invalid format: %s"%format)


def computeMean(val1, val2):
	"""returns the mean value between two values.

	Beware: Integer division done here for the benefit of datetime calculations.

	>>> computeMean(1.,3)
	2.0
	>>> computeMean(datetime.datetime(2000, 10, 13), 
	...   datetime.datetime(2000, 10, 12))
	datetime.datetime(2000, 10, 12, 12, 0)
	"""
	return val1+(val2-val1)/2


def lastSourceElements(path, numElements):
	"""returns a path made up from the last numElements items in path.
	"""
	newPath = []
	fullPath = self.context.sourceName
	for i in range(int(numElements)):
		fullPath, part = os.path.split(fullPath)
		newPath.append(part)
	newPath.reverse()
	return os.path.join(*newPath)


def makeCallable(funcName, code, moreGlobals=None):
	"""compiles a function in the current namespace.

	code is a complete function source.  moreGlobals, if non-None,
	must be a dictionary with additional names available to the function.
	"""
	if moreGlobals:
		moreGlobals.update(globals())
	else:
		moreGlobals = globals()
	return base.compileFunction(code.rstrip(), funcName, moreGlobals)


def killBlanks(literal):
	return literal.replace(" ", "")


def parseWithNull(literal, baseParser, nullLiteral=base.Undefined,
		default=None):
	"""returns default if literal is nullLiteral, else baseParser(literal).
	"""
	if nullLiteral is not base.Undefined and literal==nullLiteral:
		return default
	res = baseParser(literal)
	if res is None:
		return default
	return res


def addRmkFunc(name, func):
	globals()[name] = func


def _test():
	import doctest, rmkfuncs
	doctest.testmod(rmkfuncs)


if __name__=="__main__":
	_test()
