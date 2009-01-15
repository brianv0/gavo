"""
Math-related helper functions.
"""

import datetime


def jYearToDateTime(jYear):
	"""returns a datetime.datetime instance for a fractional (julian) year.
	
	This refers to time specifications like J2001.32.
	"""
	frac, year = math.modf(float(jYear))
	# Workaround for crazy bug giving dates like 1997-13-1 on some
	# mx.DateTime versions
	if year<0:
		frac += 1
		year -= 1
	return datetime.datetime(int(year))+365.25*frac


def dateTimeToJYear(dt):
	"""returns a fractional (julian) year for a datetime.datetime instance.
	"""
	return dt.jdn/365.25-4712


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
