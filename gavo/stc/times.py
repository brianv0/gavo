"""
Helpers for time parsing and conversion.
"""

import bisect
import datetime
import math
import re

from gavo import utils
from gavo.stc.common import *

_isoDTRE = re.compile(r"(?P<year>\d\d\d\d)-?(?P<month>\d\d)-?(?P<day>\d\d)"
		r"(?:T(?P<hour>\d\d):?(?P<minute>\d\d):?"
		r"(?P<seconds>\d\d)(?P<secFracs>\.\d*)?Z?)?$")

def parseISODT(literal):
	"""returns a datetime object for a ISO time literal.

	There's no timezone support yet.

	>>> parseISODT("1998-12-14")
	datetime.datetime(1998, 12, 14, 0, 0)
	>>> parseISODT("1998-12-14T13:30:12")
	datetime.datetime(1998, 12, 14, 13, 30, 12)
	>>> parseISODT("1998-12-14T13:30:12Z")
	datetime.datetime(1998, 12, 14, 13, 30, 12)
	>>> parseISODT("1998-12-14T13:30:12.224Z")
	datetime.datetime(1998, 12, 14, 13, 30, 12, 224000)
	>>> parseISODT("19981214T133012Z")
	datetime.datetime(1998, 12, 14, 13, 30, 12)
	>>> parseISODT("junk")
	Traceback (most recent call last):
	STCLiteralError: Bad ISO datetime literal: junk
	"""
	mat = _isoDTRE.match(literal.strip())
	if not mat:
		raise STCLiteralError("Bad ISO datetime literal: %s"%literal,
			literal)
	parts = mat.groupdict()
	if parts["hour"] is None:
		parts["hour"] = parts["minute"] = parts["seconds"] = 0
	if parts["secFracs"] is None:
		parts["secFracs"] = 0
	else:
		parts["secFracs"] = "0"+parts["secFracs"]
	return datetime.datetime(int(parts["year"]), int(parts["month"]),
		int(parts["day"]), int(parts["hour"]), int(parts["minute"]), 
		int(parts["seconds"]), int(float(parts["secFracs"])*1000000))


def jdnToDateTime(jd):
	"""returns a datetime.datetime instance for a julian day number.
	"""
	return jYearToDateTime((jd-2451545.0)/365.25+2000.0)


def mjdToDateTime(mjd):
	"""returns a datetime.datetime instance for a modified julian day number.

	Beware: This loses a couple of significant digits due to transformation
	to jd.
	"""
	return jdnToDateTime(mjd+2400000.5)


def bYearToDateTime(bYear):
	"""returns a datetime.datetime instance for a fractional Besselian year.

	This uses the formula given by Lieske, J.H., A&A 73, 282 (1979).
	"""
	jdn = (bYear-1900.0)*tropicalYear+2415020.31352
	return jdnToDateTime(jdn)


def jYearToDateTime(jYear):
	"""returns a datetime.datetime instance for a fractional (julian) year.
	
	This refers to time specifications like J2001.32.
	"""
	return datetime.datetime(2000, 1, 1, 12)+datetime.timedelta(
		days=(jYear-2000.0)*365.25)


dtJ2000 = jYearToDateTime(2000.0)
dtB1950 = bYearToDateTime(1950.0)

def dateTimeToJdn(dt):
	"""returns a julian day number (including fractionals) from a datetime
	instance.
	"""
	a = (14-dt.month)//12
	y = dt.year+4800-a
	m = dt.month+12*a-3
	jdn = dt.day+(153*m+2)//5+365*y+y//4-y//100+y//400-32045
	try:
		secsOnDay = dt.hour*3600+dt.minute*60+dt.second+dt.microsecond/1e6
	except AttributeError:
		secsOnDay = 0
	return jdn+(secsOnDay-43200)/86400.

def dateTimeToMJD(dt):
	"""returns a modified mjd for a datetime instance.
	"""
	return dateTimeToJdn(dt)-2400000.5

def dateTimeToBYear(dt):
	return (dateTimeToJdn(dt)-2415020.31352)/tropicalYear+1900.0


def dateTimeToJYear(dt):
	"""returns a fractional (julian) year for a datetime.datetime instance.
	"""
	return (dateTimeToJdn(dt)-2451545)/365.25+2000


def getSeconds(td):
	"""returns the number of seconds corresponding to a timedelta object.
	"""
	return td.days*86400+td.seconds+td.microseconds*1e-6


############ Time scale conversions
# All these convert to/from TT.

_TDTminusTAI = datetime.timedelta(seconds=32.184)

def TTtoTAI(tdt):
	"""returns TAI for a (datetime.datetime) TDT.
	"""
	return tdt+_TDTminusTAI

def TAItoTT(tai):
	"""returns TAI for a (datetime.datetime) TDT.
	"""
	return tai-_TDTminusTAI


def _getTDBOffset(tdb):
	"""returns the TDB-TDT according to [EXS] 2.222-1.
	"""
	g = (357.53+0.9856003*(dateTimeToJdn(tdb)-2451545.0))/180*math.pi
	return datetime.timedelta(0.001658*math.sin(g)+0.000014*math.sin(2*g))

def TDBtoTT(tdb):
	"""returns an approximate TT from a TDB.

	The simplified formula 2.222-1 from [EXS] is used.
	"""
	return tdb-_getTDBOffset(tdb)

def TTtoTDB(tt):
	"""returns approximate TDB from TT.

	The simplified formula 2.222-1 from [EXS] is used.
	"""
	return tt+_getTDBOffset(tdb)


_L_G = 6.969291e-10  # [EXS], p. 47

def _getTCGminusTT(dt): # [EXS], 2.223-5
	return datetime.timedelta(seconds=
		_L_G*(dateTimeToJdn(dt)-2443144.5)*86400)

def TTtoTCG(tt):
	"""returns TT from TCG.

	This uses 2.223-5 from [EXS].
	"""
	return tt+_getTCGminusTT(tt)

def TCGtoTT(tcg):
	"""returns TT from TCG.

	This uses 2.223-5 from [EXS].
	"""
	return tcg+_getTCGminusTT(tcg)


_L_B = 1.550505e-8

def _getTCBminusTDB(dt): # [EXS], 2.223-2
	return datetime.timedelta(
		seconds=_L_B*(dateTimeToJdn(dt)-2443144.5)*86400)

def TCBtoTT(tcb):
	"""returns an approximate TCB from a TT.

	This uses [EXS] 2.223-2 and the approximate conversion from TDB to TT.
	"""
	return TDBtoTT(tcb+_getTCBminusTDB(tcb))

def TTtoTCB(tt):
	"""returns an approximate TT from a TCB.

	This uses [EXS] 2.223-2 and the approximate conversion from TT to TDB.
	"""
	return TTtoTDB(tt)-_getTCBminusTDB(tcb)


def _makeLeapSecondTable():
	lsTable = []
	for lsCount, lsMoment in enumerate([ # from Lenny tzinfo
			datetime.datetime(1971, 12, 31, 23, 59, 59),
			datetime.datetime(1972, 06, 30, 23, 59, 59),
			datetime.datetime(1972, 12, 31, 23, 59, 59),
			datetime.datetime(1973, 12, 31, 23, 59, 59),
			datetime.datetime(1974, 12, 31, 23, 59, 59),
			datetime.datetime(1975, 12, 31, 23, 59, 59),
			datetime.datetime(1976, 12, 31, 23, 59, 59),
			datetime.datetime(1977, 12, 31, 23, 59, 59),
			datetime.datetime(1978, 12, 31, 23, 59, 59),
			datetime.datetime(1979, 12, 31, 23, 59, 59),
			datetime.datetime(1981, 06, 30, 23, 59, 59),
			datetime.datetime(1982, 06, 30, 23, 59, 59),
			datetime.datetime(1983, 06, 30, 23, 59, 59),
			datetime.datetime(1985, 06, 30, 23, 59, 59),
			datetime.datetime(1987, 12, 31, 23, 59, 59),
			datetime.datetime(1989, 12, 31, 23, 59, 59),
			datetime.datetime(1990, 12, 31, 23, 59, 59),
			datetime.datetime(1992, 06, 30, 23, 59, 59),
			datetime.datetime(1993, 06, 30, 23, 59, 59),
			datetime.datetime(1994, 06, 30, 23, 59, 59),
			datetime.datetime(1995, 12, 31, 23, 59, 59),
			datetime.datetime(1997, 06, 30, 23, 59, 59),
			datetime.datetime(1998, 12, 31, 23, 59, 59),
			datetime.datetime(2005, 12, 31, 23, 59, 59),
			datetime.datetime(2008, 12, 31, 23, 59, 59),
		]):
		lsTable.append((lsMoment, datetime.timedelta(seconds=lsCount+10)))
	return lsTable

# A table of TAI-UTC, indexed by UTC
leapSecondTable = _makeLeapSecondTable()
del _makeLeapSecondTable
_sentinelTD = datetime.timedelta(seconds=0)

def getLeapSeconds(dt, table=leapSecondTable):
	"""returns TAI-UTC for the datetime dt.
	"""
	ind = bisect.bisect_left(leapSecondTable, (dt, _sentinelTD))
	if ind==0:
		return datetime.timedelta(seconds=9.)
	return table[ind-1][1]


def UTCtoTT(utc):
	"""returns TT from UTC.

	The leap second table is complete through 2009-5.
	>>> getLeapSeconds(datetime.datetime(1998,12,31,23,59,58))
	datetime.timedelta(0, 31)
	>>> TTtoTAI(UTCtoTT(datetime.datetime(1998,12,31,23,59,59)))
	datetime.datetime(1999, 1, 1, 0, 0, 30)
	>>> TTtoTAI(UTCtoTT(datetime.datetime(1999,1,1,0,0,0)))
	datetime.datetime(1999, 1, 1, 0, 0, 32)
	"""
	return TAItoTT(utc+getLeapSeconds(utc))


# A table of TAI-UTC, indexed by TT
ttLeapSecondTable = [(UTCtoTT(t), dt) 
	for t, dt in leapSecondTable]


def TTtoUTC(tt):
	"""returns UTC from TT.

	The leap second table is complete through 2009-5.

	>>> TTtoUTC(UTCtoTT(datetime.datetime(1998,12,31,23,59,59)))
	datetime.datetime(1998, 12, 31, 23, 59, 59)
	>>> TTtoUTC(UTCtoTT(datetime.datetime(1999,1,1,0,0,0)))
	datetime.datetime(1999, 1, 1, 0, 0)
	"""
	# XXX TODO: leap seconds need to be computed from UTC, so this will
	# be one second off in the immediate vicinity of a leap second.
	return TTtoTAI(tt)-getLeapSeconds(tt, ttLeapSecondTable)


# A dict mapping timescales to conversions to/from TT.
timeConversions = {
	"UTC": (UTCtoTT, TTtoUTC),
	"TCB": (TCBtoTT, TTtoTCB),
	"TCG": (TCGtoTT, TTtoTCG),
	"TDB": (TDBtoTT, TTtoTDB),
	"TAI": (TAItoTT, TTtoTAI),
	"TT": (utils.identity, utils.identity),
}


def getTransformFromScales(fromScale, toScale):
	try:
		toTT = timeConversions[fromScale][0]
		toTarget = timeConversions[toScale][1]
	except KeyError, key:
		raise STCValueError("Unknown timescale for transform: %s"%key)
	def transform(val):
		return toTarget(toTT(val))
	return transform


def getTransformFromSTC(fromSTC, toSTC):
	fromScale, toScale = fromSTC.time.frame.timeScale, toSTC.time.frame.timeScale
	if fromScale!=toSTC and toSTC is not None:
		return getTransformFromScales(fromScale, toScale)


def _test():
	import doctest
	from gavo.stc import times
	doctest.testmod(times)

if __name__=="__main__":
	_test()
