"""
Tests for gavo.coords.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import unittest

from gavo.helpers import testhelpers

from gavo import utils
from gavo.base import coords

import tresc


interestingPlaces = [ (250, 89), (0,0), (23.0, 42.0), (23.0, -42.0), 
(-23.0, 42.0), (-23.0, -42.0), (359, 0), (314.,-42.0), (0., 89.), (0, 90), 
(90, -90), (90, 90)]


def _getWCSExample(**kwargs):
	res = {
		"CUNIT1": "deg", "CUNIT2": "deg",
		"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
		"CRVAL1": 0., "CRVAL2": 0.,
		"CRPIX1": 0., "CRPIX2": 0.,
		"CD1_1": 0.001, "CD1_2": 0., 
		"CD2_1": 0., "CD2_2": 0.001, 
		"LONPOLE": 180.,
		"NAXIS1": 100, "NAXIS2": 100, "NAXIS": 2,
	}
	res.update(**kwargs)
	return res


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


class TestWCS(unittest.TestCase):
	"""Tests for WCS-handling routines in coords
	"""
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
		wcs = _getWCSExample()
		self._doIdempotencyTest(wcs)

	def testIdempotencySkew(self):
		"""tests for idempotency of WCSTrafo o InvWCSTrafo for skewed coordinates.
		"""
		wcs = _getWCSExample()
		wcs.update({"CD1_1": -0.002, "CD1_2": 0.008, "CD2_1": 0.0021, 
			"CD2_2":-0.0012})
		self._doIdempotencyTest(wcs)

	def testCalabretta(self):
		"""tests for reprodution of published example.

		The example is from Calabretta and Greisen, A&A 395 (2002), 1077,
		adapted for what we're doing.
		"""
		wcs = _getWCSExample()
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

	@unittest.skip("This is broken in pywcs")
	def testAtPole(self):
		wcs = _getWCSExample()
		wcs["CRVAL1"] = 0
		wcs["CRVAL2"] = 90
		wcs["CDELT1"] = -1.25000002E-02
		wcs["CDELT2"] = 1.25000002E-02
		wcs["CPIX1"] = 2.56516663E+02
		wcs["CPIX2"] = 2.56516663E+02
		wcs["NAXIS1"] = wcs["NAXIS2"] = 512
		print ">>>>", coords.getSpolyFromWCSFields(wcs)

	@unittest.skip("This is broken in pywcs")
	def testInvalidWCSRejection(self):
		"""tests for correct rejection of unknown WCS specs.

		*** Test disabled since astLib is much more lenient ***
		XXX TODO: reject things when NAXIS not defined since wcslib craps out then.
		"""
		wcs = _getWCSExample()
		wcs["CTYPE1"] = "Weird Stuff"
		self.assertRaises(gavo.Error, coords.getWCSTrafo, wcs)
		wcs = _getWCSExample()
		wcs["CTYPE2"] = "Weird Stuff"
		self.assertRaises(gavo.Error, coords.getWCSTrafo, wcs)
		wcs = _getWCSExample()
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

def _d(**kwargs):
	return kwargs


class SpolyTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [('conn', tresc.DBConnection())]

	@staticmethod
	def _getHeader(overrides):
		hdr = {
			"CUNIT1": "deg", "CUNIT2": "deg",
			"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
			"CRVAL1": 0., "CRVAL2": 0.,
			"CRPIX1": 0., "CRPIX2": 0.,
			"CD1_1": 0.01, "CD1_2": 0., 
			"CD2_1": 0., "CD2_2": 0.01, 
			"LONPOLE": 180.,
			"NAXIS1": 100, "NAXIS2": 100, "NAXIS": 2,
		}
		hdr.update(overrides)
		return hdr

	def assertAreaAlmostEqual(self, wcs, area):
		cursor = self.conn.cursor()
		cursor.execute("SELECT area(%(poly)s)", 
			{'poly': coords.getSpolyFromWCSFields(wcs)})
		foundArea = list(cursor)[0][0]
		cursor.close()
		self.assertAlmostEqual(foundArea/utils.DEG/utils.DEG, area)

	def _runTest(self, sample):
		overrides, area = sample
		self.assertAreaAlmostEqual(self._getHeader(overrides), area)

	SQ2 = 0.70710678118654746/100
	SQ3_2 = 0.8660254037844386/100

	samples = [
		(_d(), 0.9797985366),
		(_d(CD1_1=-0.01),0.9797985366),
		(_d(CD2_2=-0.01),0.9797985366),
		(_d(CD1_1=-0.01, CD2_2=-0.01),0.9797985366),
		(_d(CD1_1=SQ2, CD1_2=-SQ2, CD2_1=SQ2, CD2_2=SQ2),0.9797985366),
#5
		(_d(CRVAL1=45),0.9797985366),
		(_d(CRVAL2=45),0.9797985366),
		(_d(CRVAL2=89),0.9797985366),
		(_d(CRVAL2=90),0.9797985366),
		(_d(CRVAL1=180),0.9797985366),
#10
		(_d(CRVAL1=359.5),0.9797985366),
		(_d(CD1_1=0.005, CD1_2=SQ3_2, CD2_1=SQ3_2, CD2_2=0.005), 
			0.4898004649),
		(_d(CD1_1=-0.0028, CD1_2=-8.57e-5, CD2_1=-3.198e-4, CD2_2=-0.0028), 
			0.076569163),
	]


class PixelLimitsTest(testhelpers.VerboseTest):
	def testNoCutout(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRVAL1=90, CRPIX2=50))
		self.assertEqual(
			coords.getPixelLimits([(80, -10), (100, 10)], wcs),
			[])

	def testRAOnly(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRVAL1=90, CRPIX1=50,
			CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(89., -15), (91, 15)], wcs),
			[[1, 40, 60]])

	def testRAFlipped(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRVAL1=90, CRPIX1=50,
			CD1_1=0, CD2_2=0, CD1_2=0.1, CD2_1=0.1))
		self.assertEqual(
			coords.getPixelLimits([(89., -15), (91, 15)], wcs),
			[[2, 1, 10]])

	def testStitching(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRPIX1=50, CRPIX2=50,
			CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(358, 3), (3, 2)], wcs),
			[[1, 30, 80], [2, 70, 80]])

	def testNearPole(self):
#		# I'd have to read the WCS paper to figure out what's even expected
		# here, I guess.
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRPIX1=50, CRPIX2=50,
			CRVAL1=100, CRVAL2=89, CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(25, 90), (300, 87)], wcs),
			[[1, 40, 50], [2, 60, 88]])

	def testMultipleSwallowed(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRVAL1=90, CRPIX2=50,
			CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(80, -10), (100, 10), 
				(87, -2), (93, 2)], wcs),
			[])

	def testMultipleJoined(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRVAL1=90,
			CRPIX1=50, CRPIX2=50, CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(87, -4), (88, 1.5), (92, 1), (93, -3)], wcs),
			[[1, 20, 80], [2, 10, 65]])

	def testNegative(self):
		wcs, _ = coords.getSkyWCS(_getWCSExample(CRPIX1=50, CD1_1=0.1, CD2_2=0.1))
		self.assertEqual(
			coords.getPixelLimits([(-2, 0), (1, 1)], wcs),
			[[1, 30, 60], [2, 1, 10]])


if __name__=="__main__":
	testhelpers.main(SpolyTest)
