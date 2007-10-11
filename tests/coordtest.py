"""
Tests for gavo.coords.
"""

import unittest

from gavo import coords

class TestCartesian(unittest.TestCase):
	"""Tests for cartesian coordinates on the unit sphere.
	"""
	def testTangential(self):
		"""tests tangential unit vectors all over the sky.
		"""
		for alpha in range(0, 360, 10):
			for delta in range(-90, 90, 10):
				cPos = coords.computeUnitSphereCoords(alpha, delta)
				ua, ud = coords.getTangentialUnits(cPos)
				self.assertAlmostEqual(cPos*ua, 0, msg="unit alpha not perp cPos")
				self.assertAlmostEqual(cPos*ud, 0, msg="unit delta not perp cPos")
				self.assertAlmostEqual(ua*ud, 0, msg="unit vectors not perp")
				self.assert_(ud[2]*delta>=0,
					"unit delta doesn't point to pole.")
				if delta<0:
					self.assert_(ua.cross(ud)*cPos<0, "unit alpha points backwards")
				else:
					self.assert_(ua.cross(ud)*cPos>0, "unit alpha points backwards")


if __name__=="__main__":
	unittest.main()
