"""
Math-related helper functions.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import math

from gavo.utils import codetricks

DEG = math.pi/180
ARCSEC = DEG/3600

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


class getHexToBin(codetricks.CachedResource):
	"""returns a dictionary mapping hex chars to their binary expansions.
	"""
	@classmethod
	def impl(self):
		return dict(zip(
			"0123456789abcdef",
			["0000", "0001", "0010", "0011", "0100", "0101", "0110", "0111",
			 "1000", "1001", "1010", "1011", "1100", "1101", "1110", "1111",]))
		

def toBinary(anInt, desiredLength=None):
	"""returns anInt as a string with its binary digits, MSB first.

	If desiredLength is given and the binary expansion is shorter,
	the value will be padded with zeros.

	>>> toBinary(349)
	'101011101'
	>>> toBinary(349, 10)
	'0101011101'
	"""
	h2b = getHexToBin()
	res = "".join(h2b[c] for c in "%x"%anInt).lstrip("0")
	if desiredLength is not None:
		res = "0"*(desiredLength-len(res))+res
	return res


def _test():
	import doctest, mathtricks
	doctest.testmod(mathtricks)


if __name__=="__main__":
	_test()
