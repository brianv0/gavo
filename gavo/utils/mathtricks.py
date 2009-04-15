"""
Math-related helper functions.
"""

import math


secsPerJCy = 36525*24*3600.
arcsecToRad = math.pi/180/3600
radToArcsec = 1/arcsecToRad

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
