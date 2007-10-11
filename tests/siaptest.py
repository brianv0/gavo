"""
Some plausibility testing for our siap infrastructure.

Needs connectivity to the db defined in the test profile.
"""

import unittest

from gavo import nullui
from gavo import config
from gavo import sqlsupport
from gavo import interfaces
from gavo.coords import Vector3
from gavo.web import siap


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

	def _runTests(self, type):
		querier = sqlsupport.SimpleQuerier()
		try:
			for bbox, expected in self._testcases:
				fragment, pars = siap.getBboxQueryFromBbox(type, bbox , "")
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
		querier.query("DROP TABLE simplewcs CASCADE")
		querier.commit()


if __name__=="__main__":
	unittest.main()
