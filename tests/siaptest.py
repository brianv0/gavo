"""
Some plausibility testing for our siap infrastructure.

Needs connectivity to the db defined in the test profile.
"""

import unittest
import math

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo.base import coords
from gavo.helpers import testhelpers
from gavo.protocols import siap
from gavo.utils import DEG

import tresc


def raCorr(dec):
	return math.cos(dec*DEG)


class TestWCSTrafos(unittest.TestCase):
	"""Tests for transformations between WCS and pixel coordinates.
	"""
	wcs = {
		"CRVAL1": 0,   "CRVAL2": 0,
		"CRPIX1": 50,  "CRPIX2": 50,
		"CD1_1": 0.01, "CD1_2": 0,
		"CD2_1": 0,    "CD2_2": 0.01,
		"NAXIS1": 100, "NAXIS2": 100,
		"CUNIT1": "deg", "CUNIT2": "deg",
		"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
		"LONPOLE": 180.,
		"NAXIS": 2,
	}

	def _testInvertibilityReal(self):
		for crvals in [(0,0), (40,60), (125,-60), (238,80)]:
			self.wcs["CRVAL1"], self.wcs["CRVAL2"] = crvals
			for crpixs in [(0,0), (50,50), (100,100), (150,0)]:
				self.wcs["CRPIX1"], self.wcs["CRPIX2"] = crpixs
				for pixpos in [(0,0), (50, 50), (0, 100), (100, 0)]:
					fwTrafo = coords.getWCSTrafo(self.wcs)
					bwTrafo = coords.getInvWCSTrafo(self.wcs)
					x, y = bwTrafo(*fwTrafo(*pixpos))
					self.assertAlmostEqual(x, pixpos[0], 5)
					self.assertAlmostEqual(y, pixpos[1], 5)

	def testInvertibility(self):
		"""tests if transformations from/to WCS are invertible.
		"""
		self._testInvertibilityReal()
		self.wcs["CD2_1"] = 0.001
		self._testInvertibilityReal()
		self.wcs["CD1_2"] = -0.001
		self._testInvertibilityReal()


class TestWCSBbox(unittest.TestCase):
	"""Tests for conversion from WCS coordinates to bboxes and box relations.

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
			"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
			"LONPOLE": 180.,
			"NAXIS": 2,
		}
		def encloses(bbox1, bbox2):
			"""returns true if bbox1 encloses bbox2.
			"""
			b11, b12 = siap.splitCrossingBox(bbox1)
			b21, b22 = siap.splitCrossingBox(bbox2)
			return b11.contains(b21) and (not b12 or b12.contains(b22))

		boxes = []
		boxes.append(coords.getBboxFromWCSFields(wcs))
		for i in range(10):
			wcs["CD1_1"] *= 1.1
			wcs["CD2_2"] *= 1.0001
			bbox = coords.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in ra at %f, %f"%(ra, dec))
			boxes.append(bbox)
		for i in range(7):
			wcs["CD2_2"] *= 1.1
			wcs["CD1_1"] *= 1.0001
			bbox = coords.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in dec at %f, %f -- %s %s"%(ra, dec, bbox, oldBbox))
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
			"CTYPE1": 'RA---TAN-SIP', "CTYPE2": 'DEC--TAN-SIP',
			"LONPOLE": 180.,
			"NAXIS": 2,
		}

		def overlaps(bbox1, bbox2):
			"""returns true if bbox1 and bbox2 overlap.
			"""
			b11, b12 = siap.splitCrossingBox(bbox1)
			b21, b22 = siap.splitCrossingBox(bbox2)
			return b11.overlaps(b21) or (b12 and b12.overlaps(b22)) or (
				b12 and b12.overlaps(b21)) or (b22 and b22.overlaps(b11))

		targBbox = coords.getBboxFromWCSFields(wcs)
		overlapOffsets = [(.1, .1), (.6, .6), (.6, -.6), (-.6, .6), 
			(-.6, .6), (.9, .9), (.9, -.9), (-.9, .9), (-.9, .9)]
		for da, dd in overlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da, dec+dd
			bbox = coords.getBboxFromWCSFields(wcs)
			self.assert_(overlaps(bbox, targBbox), "Overlap test false negative"
				" at %s, offsets %s"%((ra, dec), (da, dd)))
		if abs(dec)>85:
			# These overlap in RA always
			return
		notOverlapOffsets = [(0, 1.1), (2.4, 0), (0, -1.6), (-1.6, 0), 
			(-0.8, -1.6)]
		for da, dd in notOverlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da/raCorr(dec), dec+dd
			bbox = coords.getBboxFromWCSFields(wcs)
			self.failIf(overlaps(bbox, targBbox), "Overlap test false positive"
				" at %s, offsets %s"%((ra, dec), (da, dd)))

	def testOverlap(self):
		"""tests for bbox overlaps when moving a field around.
		"""
		for ra, dec in self._testCoords:
			self._testOverlap(ra, dec)


class _SIAPTestTable(testhelpers.TestResource):
	"""Base class for SIAP test tables.
	"""
	resources = [("conn", tresc.dbConnection)]
	setUpCost = 6
	
	def __init__(self, ddid):
		self.ddid = ddid
		testhelpers.TestResource.__init__(self)

	def make(self, deps):
		self.conn = deps["conn"]

		def computeWCSKeys(pos, size):
			imgPix = (1000., 1000.)
			res = {
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
				"NAXIS": 2,
				"CTYPE1": 'RA---TAN-SIP', 
				"CTYPE2": 'DEC--TAN-SIP',
				"LONPOLE": 180.,
				"imageTitle": "test image",
				"instId": None,
				"dateObs": None,
				"refFrame": None,
				"wcs_equinox": None,
				"bandpassId": None,
				"bandpassUnit": None,
				"bandpassRefval": None,
				"bandpassHi": None,
				"bandpassLo": None,
				"pixflags": None,
				"accref": "image%s%s"%(pos, size),
				"accsize": None,
				"embargo": None,
				"owner": None,
			}
			return res
		rd = testhelpers.getTestRD()
		dd = rd.getById(self.ddid)
		return rsc.makeData(dd, connection=self.conn, forceSource=[
			computeWCSKeys(pos, size) for pos, size in [
				((0, 0), (10, 10)),
				((0, 90), (1, 1)),
				((45, -45), (1, 1)),
				((0, 45), (2.1, 1.1)),
				((1, 45), (4.1, 1.1)),
				((2, 45), (2.1, 1.1)),
				((160, 45), (2.1, 1.1)),
				((161, 45), (4.1, 1.1)),
				((162, 45), (2.1, 1.1))]])

	def clean(self, data):
		data.dropTables()
		self.conn.commit()


class CooQueryTestBase(testhelpers.VerboseTest):
	"""base class for functional testing of the SIAP code.
	"""
	data = None

	# queries with expected numbers of returned items
	_testcases = [
		("0,0", "1", (1, 0, 1, 1)),
		("45,-45.6", "1", (0, 0, 0, 1)),
		("1,45", "3,1", (1, 0, 3, 3)),
		("1,46", "1.1", (0, 0, 0, 3)),
		("161,45", "3,1", (1, 0, 3, 3)),
		("161,46", "1.1", (0, 0, 0, 3)),
		("0,90", "360,2", (0, 1, 1, 1)),
# XXX TODO: do some more here
	]
	_intersectionIndex = {
		"COVERS": 0,
		"ENCLOSED": 1,
		"CENTER": 2,
		"OVERLAPS": 3,
	}

	def _runTests(self, type):
		if self.data is None:  # only do something if given data (see below)
			return
		table = self.data.getPrimaryTable()
		for center, size, expected in self._testcases:
			pars = {}
			fragment = siap.getQuery(table.tableDef, {
				"POS": center,
				"SIZE": size,
				"INTERSECT": type}, pars)
			res = list(table.query(
				"SELECT * FROM %s WHERE %s"%(table.tableName, fragment), 
				pars))
			self.assertEqual(len(res), expected[self._intersectionIndex[type]], 
				"%d instead of %d matched when queriying for %s %s"%(len(res), 
				expected[self._intersectionIndex[type]], type, (center, size)))

	# queries with expected numbers of returned items
	_testcases = [
		("0,0", "1", (1, 0, 1, 1)),
		("45,-45.6", "1", (0, 0, 0, 1)),
		("1,45", "3,1", (1, 0, 3, 3)),
		("1,46", "1.1", (0, 0, 0, 3)),
		("161,45", "3,1", (1, 0, 3, 3)),
		("161,46", "1.1", (0, 0, 0, 3)),
		("0,90", "360,2", (0, 1, 1, 1)),
# XXX TODO: do some more here
	]

	def testCOVERS(self):
		self._runTests("COVERS")
	
	def testENCLOSED(self):
		self._runTests("ENCLOSED")
	
	def testCENTER(self):
		self._runTests("CENTER")
	
	def testOVERLAPS(self):
		self._runTests("OVERLAPS")


class BboxQueriesTest(CooQueryTestBase):
	"""tests for actual queries on the unit sphere with trivial WCS data.
	"""
	resources = [("data", _SIAPTestTable("bbox_siaptest"))]


class PgSphereQueriesTest(CooQueryTestBase):
	"""tests for actual queries on the unit sphere with trivial WCS data.
	"""
	resources = [("data", _SIAPTestTable("pgs_siaptest"))]



def singleTest():
	suite = unittest.makeSuite(TestWCSBbox, "testEnc")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	testhelpers.main(PgSphereQueriesTest)
