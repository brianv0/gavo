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
	_testCoords = [(0, 0), (0, 60), (0, -60), 
		(40, 0), (60, -65), (40, 47),
		(130, 32), (140, -20), (250, 80), (235, -10)]

	def testBboxDepths(self):
		"""test for correct depth of bbox.
		"""
		def getCapDepthForAngle(size):
			return 1-math.cos(math.atan(utils.degToRad(math.sqrt(2)*size/2)))
		wcs = {
				"CRVAL1": 0,   "CRVAL2": 0,
				"CRPIX1": 50,  "CRPIX2": 50,
				"CD1_1": 0.01, "CD1_2": 0,
				"CD2_1": 0,    "CD2_2": 0.01,
				"NAXIS1": 100, "NAXIS2": 100,
				"CUNIT1": "deg", "CUNIT2": "deg",
			}
		bbox, center = siap.getBboxFromWCSFields(wcs)
		self.assertAlmostEqual(abs(center-Vector3(1,0,0)), 0)
		self.assertAlmostEqual(bbox[0][1]-bbox[0][0], getCapDepthForAngle(1))
		wcs["CD1_1"] = 0.1
		wcs["CD2_2"] = 0.1
		bbox, center = siap.getBboxFromWCSFields(wcs)
		self.assertAlmostEqual(bbox[0][1]-bbox[0][0], getCapDepthForAngle(10))

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
			(bbox1_xmin, bbox1_xmax), (bbox1_ymin, bbox1_ymax
				), (bbox1_zmin, bbox1_zmax) = bbox1
			(bbox2_xmin, bbox2_xmax), (bbox2_ymin, bbox2_ymax
				), (bbox2_zmin, bbox2_zmax) = bbox2
			return bbox1_xmin<=bbox2_xmin and bbox1_xmax>=bbox2_xmax\
				and bbox1_ymin<=bbox2_ymin and bbox1_ymax>=bbox2_ymax\
				and bbox1_zmin<=bbox2_zmin and bbox1_zmax>=bbox2_zmax
		boxes = []
		bbox, _ = siap.getBboxFromWCSFields(wcs)
		boxes.append(bbox)
		for i in range(10):
			wcs["CD1_1"] *= 1.1
			bbox, _ = siap.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in ra at %f, %f"%(ra, dec))
			boxes.append(bbox)
		for i in range(10):
			wcs["CD2_2"] *= 1.1
			bbox, _ = siap.getBboxFromWCSFields(wcs)
			for oldBbox in boxes:
				self.assert_(encloses(bbox, oldBbox), "enclose false negative"
					" while growing in dec at %f, %f"%(ra, dec))
			boxes.append(bbox)

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
		print "--------------------"
		print ra, dec
		print "IMG", (wcs["CRVAL1"]-wcs["CD1_1"]/raCorr(dec)*wcs["NAXIS1"]/2,
			wcs["CRVAL1"]+wcs["CD1_1"]*wcs["NAXIS1"]/2)
		def overlaps(bbox1, bbox2):
			"""returns true if bbox1 and bbox2 overlap.
			"""
			(bbox1_xmin, bbox1_xmax), (bbox1_ymin, bbox1_ymax
				), (bbox1_zmin, bbox1_zmax) = bbox1
			(bbox2_xmin, bbox2_xmax), (bbox2_ymin, bbox2_ymax
				), (bbox2_zmin, bbox2_zmax) = bbox2
			print 	((bbox2_xmin>=bbox1_xmax or bbox2_xmax<=bbox1_xmin),
				(bbox2_ymin>=bbox1_ymax or bbox2_ymax<=bbox1_ymin),
				(bbox2_zmin>=bbox1_zmax or bbox2_zmax<=bbox1_zmin))
			return not (
				(bbox2_xmin>=bbox1_xmax or bbox2_xmax<=bbox1_xmin) or
				(bbox2_ymin>=bbox1_ymax or bbox2_ymax<=bbox1_ymin) or
				(bbox2_zmin>=bbox1_zmax or bbox2_zmax<=bbox1_zmin))
		targBbox, _ = siap.getBboxFromWCSFields(wcs)
		print "img", targBbox
		overlapOffsets = [(.1, .1), (.6, .6), (.6, -.6), (-.6, .6), (-.6, .6),
			(.9, .9), (.9, -.9), (-.9, .9), (-.9, .9)]
		for da, dd in overlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da/raCorr(dec), dec+dd
			bbox, _ = siap.getBboxFromWCSFields(wcs)
			self.assert_(overlaps(bbox, targBbox), "Overlap test false negative"
				" at %s, offsets %s"%((ra, dec), (da, dd)))
		notOverlapOffsets = [(0, 1.1), (2.4, 0), (0, -1.6), (-1.6, 0), (-0.8, -1.6)]
		for da, dd in notOverlapOffsets:
			wcs["CRVAL1"], wcs["CRVAL2"] = ra+da/raCorr(dec), dec+dd
			print "ROI", (wcs["CRVAL1"]-wcs["CD1_1"]/raCorr(dec)*wcs["NAXIS1"]/2,
				wcs["CRVAL1"]+wcs["CD1_1"]*wcs["NAXIS1"]/2)
			bbox, _ = siap.getBboxFromWCSFields(wcs)
			print "roi", bbox
			self.failIf(overlaps(bbox, targBbox), "Overlap test false positive"
				" at %s, offsets %s"%((ra, dec), (da, dd)))

	def testOverlap(self):
		"""tests for bbox overlaps when moving a field around.
		"""
		for ra, dec in self._testCoords:
			self._testOverlap(ra, dec)


class TestBboxQueries(unittest.TestCase):
	"""Tests basic bbox-based queries on artificial bboxes.
	"""
	def setUp(self):
		"""fills a database table with test data.
		"""
		def computeInterfaceVals(center, size):
			return {
				"bbox_xmin": center[0]-size[0]/2.,
				"bbox_xmax": center[0]+size[0]/2.,
				"bbox_ymin": center[1]-size[1]/2.,
				"bbox_ymax": center[1]+size[1]/2.,
				"bbox_zmin": center[2]-size[2]/2.,
				"bbox_zmax": center[2]+size[2]/2.,
				"bbox_centerx": center[0],
				"bbox_centery": center[1],
				"bbox_centerz": center[2],
			}
		config.setDbProfile("test")
		tw = sqlsupport.TableWriter("bboxes", 
			[f for _, f in interfaces.UnitSphereBbox().getNodes(None)])
		tw.createTable()
		feed = tw.getFeeder()
		for center, size in [
				(Vector3(0,0,0), Vector3(1,1,1)),
				(Vector3(0,0,0), Vector3(10,0.1,1)),
				(Vector3(0,0,0), Vector3(0.1,10,1)),
				(Vector3(1,1,1), Vector3(0.1,0.1,0.1))]:
			feed(computeInterfaceVals(center, size))
		feed.close()

	# bboxes with expected numbers of returned items
	_testcases = [
		(([0.5,2], [1,2], [1,2]), (0, 0, 0, 1)),
		(([0,0.05], [-0.05,0], [-0.05,0.05]), (3, 0, 3, 3)),
		(([4,5], [-0.05,0], [-0.05,0.05]), (1, 0, 1, 1)),
		(([0.8,1.2], [0.8,1.2], [0.8,1.2]), (0, 1, 1, 1)),
	]
	_intersectionIndex = {
		"COVERS": 0,
		"ENCLOSED": 1,
		"CENTER": 2,
		"OVERLAPS": 3,
	}

	def _getCenter(self, bbox):
		return Vector3(*map(lambda a: sum(a)/float(len(a)), bbox))

	def _runTests(self, type):
		querier = sqlsupport.SimpleQuerier()
		try:
			for bbox, expected in self._testcases:
				fragment, pars = siap.getBboxQueryFromBbox(type, bbox , 
					self._getCenter(bbox), "")
				res = querier.query(
					"SELECT * FROM bboxes WHERE %s"%fragment, pars).fetchall()
				self.assertEqual(len(res), expected[self._intersectionIndex[type]], 
					"%d instead of %d matched when queriying for %s %s"%(len(res), 
					expected[self._intersectionIndex[type]], type, bbox))
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
		querier.query("DROP TABLE bboxes CASCADE")
		querier.commit()


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
			[f for _, f in interfaces.UnitSphereBbox().getNodes(None)])
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
		("0,90", "10", (0, 1, 1, 1)),
		("45,-45.6", "1", (0, 0, 0, 1)),
		("1,45", "3,1", (1, 0, 3, 3)),
		("1,47", "1.1", (0, 0, 0, 3)),
		("161,45", "3,1", (1, 0, 3, 3)),
		("161,47", "1.1", (0, 0, 0, 3)),
# XXX do some more here
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
				if type=="OVERLAPS":
					print fragment, pars
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
#		querier.query("DROP TABLE simplewcs CASCADE")
		querier.commit()


def singleTest():
	suite = unittest.makeSuite(TestWCSBbox, "test")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	#unittest.main()
	singleTest()
