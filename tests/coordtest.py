"""
Tests for gavo.coords.
"""

import unittest

import gavo
from gavo.base import coords


interestingPlaces = [ (250, 89), (0,0), (23.0, 42.0), (23.0, -42.0), 
(-23.0, 42.0), (-23.0, -42.0), (359, 0), (314.,-42.0), (0., 89.), (0, 90), 
(90, -90), (90, 90)]


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


class TestWCS(unittest.TestCase):
	"""Tests for WCS-handling routines in coords
	"""
	def _getWCSExample(self):
		return {
			"CUNIT1": "deg", "CUNIT2": "deg",
			"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
			"CRVAL1": 0, "CRVAL2": 0,
			"CRPIX1": 0, "CRPIX2": 0,
			"CD1_1": 0.001, "CD1_2": 0, 
			"CD2_1": 0, "CD2_2": 0.001, 
			"LONPOLE": 180.,
			"NAXIS1": 100, "NAXIS2": 100, "NAXIS": 2,
		}

	def _doIdempotencyTest(self, wcs):
		for ra, dec in interestingPlaces:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra, dec
			proj = coords.getWCSTrafo(wcs)
			inv = coords.getInvWCSTrafo(wcs)
			for pxCoo in [(0, 0), (200, 200), (-200, 200), (200, -200), 
					(-200, -200)]:
				wCoo = proj(*pxCoo)
				res = inv(*wCoo)
				self.assertAlmostEqual(pxCoo[0], res[0], 8, "Failure in x for %f, %f "
					"(%d,%d): %f vs. %f"%(ra, dec, pxCoo[0], pxCoo[1], pxCoo[0], res[0]))
				self.assertAlmostEqual(pxCoo[1], res[1], 8, "Failure in y for %f, %f "
					"(%d,%d): %f vs. %f"%(ra, dec, pxCoo[0], pxCoo[1], pxCoo[1], res[1]))

	def testIdempotencyPos(self):
		"""tests for idempotency of WCSTrafo o InvWCSTrafo over the sky.
		"""
		wcs = self._getWCSExample()
		self._doIdempotencyTest(wcs)

	def testIdempotencySkew(self):
		"""tests for idempotency of WCSTrafo o InvWCSTrafo for skewed coordinates.
		"""
		wcs = self._getWCSExample()
		wcs.update({"CD1_1": -0.002, "CD1_2": 0.008, "CD2_1": 0.0021, 
			"CD2_2":-0.0012})
		self._doIdempotencyTest(wcs)

	def testCalabretta(self):
		"""tests for reprodution of published example.

		The example is from Calabretta and Greisen, A&A 395 (2002), 1077,
		adapted for what we're doing.
		"""
		wcs = self._getWCSExample()
		wcs.update({
			"CRPIX1": 256, "CRPIX2": 257,
			"CRVAL1": 45.83, "CRVAL2": 63.57,
			"CD1_1": -0.003, "CD1_2": 0,
			"CD2_1": 0, "CD2_2": 0.003})
		proj = coords.getWCSTrafo(wcs)
		for coos, expected in [
				((1,2), (47.503264, 62.795111)),
				((1,512), (47.595581, 64.324332)),
				((511,512), (44.064419, 64.324332)),
				]:
			res = proj(*coos)
			self.assertAlmostEqual(expected[0], res[0], 5)
			self.assertAlmostEqual(expected[1], res[1], 5)
	
	def _testInvalidWCSRejection(self):
		"""tests for correct rejection of unknown WCS specs.

		*** Test disabled since astLib is much more lenient ***
		XXX TODO: reject things when NAXIS not defined since wcslib craps out then.
		"""
		wcs = self._getWCSExample()
		wcs["CTYPE1"] = "Weird Stuff"
		self.assertRaises(gavo.Error, coords.getWCSTrafo, wcs)
		wcs = self._getWCSExample()
		wcs["CTYPE2"] = "Weird Stuff"
		self.assertRaises(gavo.Error, coords.getWCSTrafo, wcs)
		wcs = self._getWCSExample()
		wcs["CUNIT1"] = "arcsec"
		self.assertRaises(gavo.Error, coords.getWCSTrafo, wcs)


class TestMovePm(unittest.TestCase):
	"""Tests for working proper motion application.
	"""
	def testMovePm(self):
		self.assertEqual("%.8f %.8f"%coords.movePm(23, 50, 0., 0., 2),
			"23.00000000 50.00000000")
		self.assertEqual("%.8f %.8f"%coords.movePm(23, 50, 0.001, 0.001, 20),
			"23.03112743 50.01999584")
		self.assertEqual("%.8f %.8f"%coords.movePm(23, -50, -0.001, 0.004, -20),
			"23.03116636 -50.07999583")
		self.assertEqual("%.8f %.8f"%coords.movePm(232, -80, -0.001, 0.004, -20),
			"232.11609464 -80.07998004")


class TestGetGCDist(unittest.TestCase):
	def testGcDist(self):
		self.assertAlmostEqual(coords.getGCDist((0, 0), (0, 0)), 0)
		for dec in range(-90, 91, 30):
			self.assertAlmostEqual(coords.getGCDist((0, 0), (0, dec)), abs(dec))
		for ra in range(0, 181, 30):
			self.assertAlmostEqual(coords.getGCDist((0, 0), (ra, 0)), ra)
		for ra in range(180, 361, 30):
			self.assertAlmostEqual(coords.getGCDist((0, 0), (ra, 0)), 360-ra)


def singleTest():
	suite = unittest.makeSuite(TestMovePm, "test")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	unittest.main()
	#singleTest()
