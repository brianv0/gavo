"""
Tests for gavo.coords.
"""

import unittest

from gavo import coords

class TestCartesian(unittest.TestCase):
	"""Tests for cartesian coordinates on the unit sphere.
	"""
	def testTangential(self):
		"""tests for correct tangential unit vectors all over the sky.
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


class TestBoxes(unittest.TestCase):
	"""Tests for boxes and their relations.
	"""
	def testOverlaps(self):
		"""tests for overlapping boxes.
		"""
		referenceBox = coords.Box(-0.5, 0.5, -0.5, 0.5)
		overlapping = [((-1,-1),(1,1)), ((-1,-1),(0,0)),
			((1,1),(0,0)),((1,1),(0.2,0.2)),
			((10,0),(0,0)),((0.2,-0.2),(-0.2,0.2))]
		for p1, p2 in overlapping:
			newBox = coords.Box(p1, p2)
			self.assert_(referenceBox.overlaps(newBox),
				"%s is not recognized as overlapping %s"%(newBox, referenceBox))
			self.assert_(newBox.overlaps(referenceBox),
				"%s is not recognized as overlapping %s"%(referenceBox, newBox))

	def testDoesNotOverlap(self):
		"""tests for boxes not overlapping.
		"""
		referenceBox = coords.Box(-0.5, 0.5, -0.5, 0.5)
		overlapping = [((-1,-1),(-0.7,-0.7)), ((1,1),(0.7,0.7)),
			((1,-10),(1.5,10)),((-1,-10),(-0.7,10)),
			((-10,1),(10,1.2)),((-10,-1),(10,-1.2))]
		for p1, p2 in overlapping:
			newBox = coords.Box(p1, p2)
			self.failIf(referenceBox.overlaps(newBox),
				"%s is flagged as overlapping %s"%(newBox, referenceBox))
			self.failIf(newBox.overlaps(referenceBox),
				"%s is flagged as overlapping %s"%(referenceBox, newBox))

	def testContains(self):
		"""tests the containment relation for boxes and points.
		"""
		referenceBox = coords.Box((10, 0), (11, 2))
		self.assert_(referenceBox.contains(coords.Box((10.5, 1), (10.7, 1.5))))
		self.assert_(referenceBox.contains((10.5, 0.5)))
		self.failIf(referenceBox.contains((0,0)))
		self.failIf(referenceBox.contains(coords.Box((10.5, 1), (11.7, 1.5))))

	def testMiscmethods(self):
		"""tests for accessors and stuff on Boxes.
		"""
		referenceBox = coords.Box((10, 0), (11, 2))
		self.assertEqual(str(referenceBox), '((11,2), (10,0))')
		self.assertEqual(referenceBox[0], (11,2))
		self.assertEqual(referenceBox[1], (10,0))

	def testDegenerate(self):
		"""tests for some border cases.
		"""
		refBox = coords.Box((1,0),(2,0))
		testBox = coords.Box((1.5,0),(2.5,0))
		self.assert_(refBox.overlaps(testBox), "Degenerate boxes do not overlap")


if __name__=="__main__":
	unittest.main()
