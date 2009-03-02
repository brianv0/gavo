"""
Helpers for time parsing and conversion.
"""

import datetime
import re

from gavo.stc import common

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
		raise common.STCLiteralError("Bad ISO datetime literal: %s"%literal,
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


def jYearToDateTime(jYear):
	"""returns a datetime.datetime instance for a fractional (julian) year.
	
	This refers to time specifications like J2001.32.
	"""
	return datetime.datetime(2000, 1, 1, 12)+datetime.timedelta(
		days=(jYear-2000.0)*365.25)


def jdnToDateTime(jd):
	"""returns a datetime.datetime instance for a julian day number.
	"""
	return jYearToDateTime((jd-2451545.0)/365.25+2000.0)


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


def dateTimeToJYear(dt):
	"""returns a fractional (julian) year for a datetime.datetime instance.
	"""
	return (dateTimeToJdn(dt)-2451545)/365.25+2000


def _test():
	import doctest
	from gavo.stc import times
	doctest.testmod(times)

if __name__=="__main__":
	_test()
