"""
Math-related helper functions.
"""

import datetime


def jYearToDateTime(jYear):
	"""returns a datetime.datetime instance for a fractional (julian) year.
	
	This refers to time specifications like J2001.32.
	"""
	return datetime.datetime(2000, 1, 1, 12)+datetime.timedelta(
		days=(jYear-2000.0)*365.25)


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


def findMinimum(f, left, right, minInterval=3e-8):
	"""returns an estimate for the minimum of the single-argument function f 
	on (left,right).

	minInterval is a fourth of the smallest test interval considered.  

	For constant functions, a value close to left will be returned.

	This function should only be used on functions having exactly
	one minimum in the interval.
	"""
# replace this at some point by some better method (Num. Recip. in C, 394f)
# -- this is easy to fool and massively suboptimal.
	mid = (right+left)/2.
	offset = (right-left)/4.
	if offset<minInterval:
		return mid
	if f(left+offset)<=f(mid+offset):
		return findMinimum(f, left, mid, minInterval)
	else:
		return findMinimum(f, mid, right, minInterval)
