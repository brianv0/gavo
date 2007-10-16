"""
Some plausibility testing for our siap infrastructure.

Needs connectivity to the db defined in the test profile.
"""

import unittest
import math

from gavo import nullui
from gavo import config
from gavo import sqlsupport
from gavo import interfaces
from gavo import utils
from gavo.coords import Vector3
from gavo.web import siap


def raCorr(dec):
	return math.cos(utils.degToRad(dec))


class TestWCSBbox(unittest.TestCase):
	"""Tests conversion from WCS coordinates to bboxes and box relations.

	These tests do cos(delta) manipulations on alpha widths despite
	SIAP's prescription that no cos(delta) is done to make test cases
	comprehendable to the cartesian mind.
	"""
	_testCoords = [(20, 20), (0, 0), (0, 60), (0, -60), 
		(40, 0), (60, -65), (40, 47), (130, 32), (140, -20), 
		(250, 80), (235, -10), (150, 89), (359, -89)]

	def _testEnclosure(self, ra, dec):
		"""tests for bbox enclosure when growing a field around ra and dec.
		"""
		wcs = {
			"CRVAL1": float(ra),   "CRVAL2": float(dec),
			"CRPIX1": 50,  "CRPIX2": 50,
			"CD1_1": 0.01/raCorr(dec), "CD1_2": 0,
			"CD2_1": 0,    "CD2_2": 0.01,
			"NAXIS1": 100, "NAXIS2": 100,
			"CUNIT1": "deg", "CUNIT2": "deg",
		}
		def encloses(bbox1, bbox2):
			"""returns true if bbox1 encloses bbox2.
			"""
			b11, b12 = siap.splitCrossingBox(bbox1)
			b21, b22 = siap.splitCrossingBox(bbox2)
			return b11.contains(b21) and (not b12 or b12.contains(b22))

		boxes = []
		boxes.append(siap.getBboxFromWCSFields(wcs))
		for i in range(10):
			wcs["CD1_1"] *= 1.1
			bbox = siap.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in ra at %f, %f"%(ra, dec))
			boxes.append(bbox)
		for i in range(10):
			wcs["CD2_2"] *= 1.1
			bbox = siap.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in dec at %f, %f"%(ra, dec))
			boxes.append(bbox)
		refbox = boxes[0]
		for box in boxes[1:]:
			self.failIf(encloses(refbox, box), "enclose false positive:"
				" %s doesn't really enclose %s"%(refbox, box))

	def testEnclosures(self):
		"""tests for bbox enclosure when growing a field.
		"""
		for ra, dec in self._testCoords:
			self._testEnclosure(ra, dec)

	def _testOverlap(self, ra, dec):
		"""tests for bbox overlaps around ra and dec when moving a field around.
		"""
		wcs = {
			"CRVAL1": float(ra),   "CRVAL2": float(dec),
			"CRPIX1": 50,  "CRPIX2": 50,
			"CD1_1": 0.01, "CD1_2": 0,
			"CD2_1": 0,    "CD2_2": 0.01,
			"NAXIS1": 100, "NAXIS2": 100,
			"CUNIT1": "deg", "CUNIT2": "deg",
		}

		def overlaps(bbox1, bbox2):
			"""returns true if bbox1 and bbox2 overlap.
			"""
			b11, b12 = siap.splitCrossingBox(bbox1)
			b21, b22 = siap.splitCrossingBox(bbox2)
			return b11.overlaps(b21) or (b12 and b12.overlaps(b22)) or (
				b12 and b12.overlaps(b21)) or (b22 and b22.overlaps(b11))

		targBbox = siap.getBboxFromWCSFields(wcs)
		overlapOffsets = [(.1, .1), (.6, .6), (.6, -.6), (-.6, .6), 
			(-.6, .6), (.9, .9), (.9, -.9), (-.9, .9), (-.9, .9)]
		for da, dd in overlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da, dec+dd
			bbox = siap.getBboxFromWCSFields(wcs)
			self.assert_(overlaps(bbox, targBbox), "Overlap test false negative"
				" at %s, offsets %s"%((ra, dec), (da, dd)))
		notOverlapOffsets = [(0, 1.1), (2.4, 0), (0, -1.6), (-1.6, 0), 
			(-0.8, -1.6)]
		for da, dd in notOverlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da/raCorr(dec), dec+dd
			bbox = siap.getBboxFromWCSFields(wcs)
			self.failIf(overlaps(bbox, targBbox), "Overlap test false positive"
				" at %s, offsets %s"%((ra, dec), (da, dd)))

	def testOverlap(self):
		"""tests for bbox overlaps when moving a field around.
		"""
		for ra, dec in self._testCoords:
			self._testOverlap(ra, dec)


class TestCoordinateQueries(unittest.TestCase):
	"""Tests for actual queries on the unit sphere with trivial WCS data.
	"""
# Ok, we should refactor this and the Bbox test.
	def setUp(self):
		"""fills a database table with test data.
		"""
		from gavo.parsing import macros
		makeBbox = macros.BboxCalculator()
		def computeWCSKeys(pos, size):
			imgPix = (1000., 1000.)
			return {
				"CRVAL1": pos[0],
				"CRVAL2": pos[1],
				"CRPIX1": imgPix[0]/2.,
				"CRPIX2": imgPix[1]/2.,
				"CUNIT1": "deg",
				"CUNIT2": "deg",
				"CD1_1": size[0]/imgPix[0],
				"CD1_2": 0,
				"CD2_2": size[1]/imgPix[1],
				"CD2_1": 0,
				"NAXIS1": imgPix[0],
				"NAXIS2": imgPix[1],
			}
		config.setDbProfile("test")
		tw = sqlsupport.TableWriter("simplewcs", 
			[f for _, f in interfaces.BboxSiap().getNodes(None)])
		tw.createTable()
		feed = tw.getFeeder()
		for pos, size in [
				((0, 0), (10, 10)),
				((0, 90), (1, 1)),
				((45, -45), (1, 1)),
				((0, 45), (2.1, 1.1)),
				((1, 45), (4.1, 1.1)),
				((2, 45), (2.1, 1.1)),
				((160, 45), (2.1, 1.1)),
				((161, 45), (4.1, 1.1)),
				((162, 45), (2.1, 1.1)),
			]:
			r = computeWCSKeys(pos, size)
			makeBbox(None, r)
			feed(r)
		feed.close()

	# queries with expected numbers of returned items
	_testcases = [
		("0,0", "1", (1, 0, 1, 1)),
		("45,-45.6", "1", (0, 0, 0, 1)),
		("1,45", "3,1", (1, 0, 3, 3)),
		("1,46", "1.1", (0, 0, 0, 3)),
		("161,45", "3,1", (1, 0, 3, 3)),
		("161,46", "1.1", (0, 0, 0, 3)),
		("0,90", "360,1", (0, 1, 1, 1)),
# XXX TODO: do some more here
	]
	_intersectionIndex = {
		"COVERS": 0,
		"ENCLOSED": 1,
		"CENTER": 2,
		"OVERLAPS": 3,
	}

	def _runTests(self, type):
		querier = sqlsupport.SimpleQuerier()
		try:
			for center, size, expected in self._testcases:
				fragment, pars = siap.getBboxQuery({
					"POS": center,
					"SIZE": size,
					"INTERSECT": type})
				res = querier.query(
					"SELECT * FROM simplewcs WHERE %s"%fragment, pars).fetchall()
				self.assertEqual(len(res), expected[self._intersectionIndex[type]], 
					"%d instead of %d matched when queriying for %s %s"%(len(res), 
					expected[self._intersectionIndex[type]], type, (center, size)))
		finally:
			querier.close()

	def testCOVERS(self):
		"""test for COVERS queries.
		"""
		self._runTests("COVERS")
	
	def testENCLOSED(self):
		"""test for ENCLOSED queries.
		"""
		self._runTests("ENCLOSED")

	def testCENTER(self):
		"""test for CENTER queries.
		"""
		self._runTests("CENTER")

	def testOVERLAPS(self):
		"""test for OVERLAP queries.
		"""
		self._runTests("OVERLAPS")

	def tearDown(self):
		"""drops the test table.
		"""
		querier = sqlsupport.SimpleQuerier()
	#	querier.query("DROP TABLE simplewcs CASCADE")
		querier.commit()


def singleTest():
	suite = unittest.makeSuite(TestCoordinateQueries, "testOVERLAPS")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	unittest.main()
	#singleTest()
