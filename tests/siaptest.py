"""
Some plausibility testing for our siap infrastructure.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import unittest
import math

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.base import coords
from gavo.helpers import fitstricks
from gavo.formats import votablewrite
from gavo.protocols import siap
from gavo.utils import DEG, fitstools

import tresc


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
		self._testInvertibilityReal()
		self.wcs["CD2_1"] = 0.001
		self._testInvertibilityReal()
		self.wcs["CD1_2"] = -0.001
		self._testInvertibilityReal()


class PixelScaleTest(testhelpers.VerboseTest):
	wcs = {
		"CRPIX1": 50, "CRPIX2": 50,
		"CD1_1": 1E-04,  "CD1_2": -1E-06,
		"CD2_1": -1E-06, "CD2_2": -1E-04,
		"CTYPE1": 'RA---TAN', "CTYPE2": 'DEC--TAN',
		"CRVAL1": None, "CRVAL2": None,
		"NAXIS1": 100, "NAXIS2": 100,
		"CUNIT1": "deg", "CUNIT2": "deg",}

	def testEquator(self):
		wcs = self.wcs.copy()
		wcs["CRVAL1"], wcs["CRVAL2"] = 0, 0
		self.assertAlmostEqualVector(coords.getPixelSizeDeg(wcs), (1e-4, 1e-4))

	def testStitch(self):
		wcs = self.wcs.copy()
		wcs["CRVAL1"], wcs["CRVAL2"] = -1e-3, 0
		self.assertAlmostEqualVector(coords.getPixelSizeDeg(wcs), (1e-4, 1e-4))
	
	def testNorth(self):
		wcs = self.wcs.copy()
		wcs["CRVAL1"], wcs["CRVAL2"] = 359.99, 70
		self.assertAlmostEqualVector(coords.getPixelSizeDeg(wcs), (1e-4, 1e-4))

	def testPole(self):
		wcs = self.wcs.copy()
		wcs["CRVAL1"], wcs["CRVAL2"] = 10, -90
		rasz, decsz = coords.getPixelSizeDeg(wcs)
		self.assertAlmostEqual(decsz, 1e-4, 5)
		self.failIf(rasz>1)


def computeWCSKeys(pos, size, cutCrap=False):
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
		"LONPOLE": 180.}
	if not cutCrap:
		res.update({"imageTitle": "test image at %s"%repr(pos),
			"instId": None,
			"dateObs":55300+pos[0], 
			"refFrame": None,
			"wcs_equinox": None,
			"bandpassId": None,
			"bandpassUnit": None,
			"bandpassRefval": None,
			"bandpassLo": pos[0],
			"bandpassHi": pos[0]+size[0],
			"pixflags": None,
			"accref": "image/%s/%s"%(pos, size),
			"accsize": (30+int(pos[0]+pos[1]+size[0]+size[1]))*1024,
			"embargo": None,
			"owner": None,
		})
	return res


class _SIAPTestTable(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]
	setUpCost = 6
	
	def __init__(self, ddid):
		self.ddid = ddid
		testhelpers.TestResource.__init__(self)

	def make(self, deps):
		self.conn = deps["conn"]

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
		data.dropTables(rsc.parseNonValidating)
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


_siapTestTable = _SIAPTestTable("pgs_siaptest")

class PgSphereQueriesTest(CooQueryTestBase):
	"""tests for actual queries on the sphere with trivial WCS data.
	"""
	resources = [("data", _siapTestTable)]


class ImportTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]
	setupCost = 0.5
	noWCSRec = {
			"imageTitle": "uncalibrated image",
			"NAXIS1": 1000,
			"NAXIS2": 100,
			"NAXIS": 2,
			"dateObs": None,
			"accref": "uu",
			"accsize": None,
			"embargo": None,
			"owner": None,}

	def testPlainPGS(self):
		dd = testhelpers.getTestRD().getById("pgs_siaptest")
		data = rsc.makeData(dd, connection=self.conn, forceSource=[
			computeWCSKeys((34, 67), (0.3, 0.4))])
		try:
			table = data.tables["pgs_siaptable"]
			res = list(table.iterQuery([table.tableDef.getColumnByName(n) for
				n in ("centerAlpha", "centerDelta")], ""))[0]
			self.assertEqual(int(res["centerDelta"]), 67)
		finally:
			data.dropTables(rsc.parseNonValidating)
			self.conn.commit()
	
	def testRaisingOnNull(self):
		dd = testhelpers.getTestRD().getById("pgs_siaptest")
		self.assertRaises(base.ValidationError, 
			rsc.makeData,
			dd, connection=self.conn, forceSource=[self.noWCSRec])

	def testNullIncorporation(self):
		dd = testhelpers.getTestRD().getById("pgs_siapnulltest")
		data = rsc.makeData(dd, connection=self.conn, forceSource=[
			self.noWCSRec, computeWCSKeys((34, 67), (0.25, 0.5))])
		try:
			table = data.tables["pgs_siaptable"]
			res = list(table.iterQuery(
				[table.tableDef.getColumnByName("accref")], ""))
			self.assertEqual(res, 
				[{u'accref': u'uu'}, {u'accref': u'image/(34, 67)/(0.25, 0.5)'}])
		finally:
			data.dropTables(rsc.parseNonValidating)
			self.conn.commit()


class SIAPTestResponse(testhelpers.TestResource):
	resources = [("siapTable", _siapTestTable)]

	def make(self, deps):
		svc = testhelpers.getTestRD().getById("pgsiapsvc")
		data = svc.run("siap.xml", {"POS": "0, 0", "SIZE": "180,180"}, 
			).original
		vot = votablewrite.getAsVOTable(data,
			tablecoding="td", suppressNamespace=True)
		return vot, testhelpers.getXMLTree(vot)

_siapTestResponse = SIAPTestResponse()


class SIAPResponseTest(testhelpers.VerboseTest):

	resources = [("siapResp", _siapTestResponse)]

	def _getSTCGroup(self):
		try:
			return _siapTestResponse._stcGroup
		except AttributeError:
			_siapTestResponse._stcGroup = self.siapResp[1].find(
			".//GROUP[@utype='stc:CatalogEntryLocation']")
		return _siapTestResponse._stcGroup

	def _getFieldForUtype(self, utype):
		ref = self._getSTCGroup().find(
			"FIELDref[@utype='%s']"%utype).get("ref")
		return self.siapResp[1].find(".//FIELD[@ID='%s']"%ref)

	def testSTCDefined(self):
		self.failUnless(len(self._getSTCGroup()))
	
	def testCoverageDefined(self):
		self.assertEqual(
			self._getFieldForUtype("stc:AstroCoordArea.Polygon").get("name"),
			"coverage")

	def testSpectralDefined(self):
		self.assertEqual(
			self._getFieldForUtype("stc:AstroCoordArea.SpectralInterval.HiLimit"
				).get("name"),
			"bandpassHi")

	def testPositionDefined(self):
		self.assertEqual(
			self._getFieldForUtype("stc:AstroCoords.Position2D.Value2.C1",
				).get("name"),
			"centerAlpha")


	def testRefsysDefined(self):
		self.assertEqual(self._getSTCGroup().find(
			"PARAM[@utype='stc:AstroCoordSystem.SpaceFrame.CoordRefFrame']").get(
				"value"), "ICRS")


class ScaleHeaderTest(testhelpers.VerboseTest):
# This is a test for fitstricks.shrinkWCSHeader.
# It's here just because we already deal with wcs in this module
	def _assertCoordsMatch(self, pair1, pair2):
		self.assertAlmostEqual(pair1[0], pair2[0])
		self.assertAlmostEqual(pair1[1], pair2[1])

	def testSimple(self):
		fullHdr = fitstools.headerFromDict(
			computeWCSKeys((23, 27), (1, 2), cutCrap=True))
		halfHdr = fitstools.shrinkWCSHeader(fullHdr, 2)

		self.assertEqual(halfHdr["IMSHRINK"], 'Image scaled down 2-fold by DaCHS')
		self.assertEqual(fullHdr["NAXIS2"]/2, halfHdr["NAXIS1"])

		toPhysOld = coords.getWCSTrafo(fullHdr)
		toPhysNew = coords.getWCSTrafo(halfHdr)

		self._assertCoordsMatch(
			toPhysOld(fullHdr["CRPIX1"],fullHdr["CRPIX2"]),
			toPhysNew(halfHdr["CRPIX1"],halfHdr["CRPIX2"]))

		self._assertCoordsMatch(
			toPhysOld(1, 1), toPhysNew(1, 1))

		self._assertCoordsMatch(
			toPhysOld(fullHdr["NAXIS1"]+1,fullHdr["NAXIS2"]+1),
			toPhysNew(halfHdr["NAXIS1"]+1,halfHdr["NAXIS2"]+1))

	def testTypesFixed(self):
		fullHdr = fitstools.headerFromDict(
			computeWCSKeys((23, 27), (1, 2), cutCrap=True))
		fullHdr.update("BZERO", 32768)
		fullHdr.update("BSCALE", 1)
		fullHdr.update("BITPIX", 8)
		halfHdr = fitstools.shrinkWCSHeader(fullHdr, 2)
		self.failIf(halfHdr.has_key("BZERO"))
		self.failIf(halfHdr.has_key("BSCALE"))
		self.assertEqual(halfHdr["BITPIX"], -32)


class SIAP2GeometryStringTest(testhelpers.VerboseTest):
	def testEmpty(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 geometry: '' (expected a SIAPv2 shape name)",
			siap.parseSIAP2Geometry,
			("",))

	def testBadShape(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 geometry: 'Trash 13 14 1 4'"
			" (expected a SIAPv2 shape name)",
			siap.parseSIAP2Geometry,
			("Trash 13 14 1 4",))

	def testBadCoo(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 coordinates: 'depp 12 13'"
			" (bad floating point literal 'depp')",
			siap.parseSIAP2Geometry,
			("CIRCLE depp 12 13",))

	def testGoodCircle(self):
		res = siap.parseSIAP2Geometry("CIRCLE 143 82 13")
		self.assertEqual(res.asSTCS("Unknown"),
			"Circle Unknown 143. 82. 13.")

	def testBadCircle(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 CIRCLE: 'CIRCLE 12 13'"
			" (need exactly three numbers)",
			siap.parseSIAP2Geometry,
			("CIRCLE 12 13",))

	def testGoodRange(self): # as if there  were such a thing
		res = siap.parseSIAP2Geometry("RANGE 345 355 -13 13")
		self.assertEqual(res.asSTCS("Unknown"),
			"PositionInterval Unknown 345. -13. 355. 13.")

	def testBadRange1(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 RANGE: 'RANGE 345 355 -13'"
				" (need exactly four numbers)",
			siap.parseSIAP2Geometry,
			("RANGE 345 355 -13",))

	def testBadRange2(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 RANGE: 'RANGE 345 355 13 -13'"
				" (lower limits must be smaller than upper limits)",
			siap.parseSIAP2Geometry,
			("RANGE 345 355 13 -13",))

	def testGoodPolygon(self): # as if there  were such a thing
		res = siap.parseSIAP2Geometry("POLYGON 12 13 34 -34 35 12")
		self.assertEqual(res.asSTCS("Unknown"),
			"Polygon Unknown 12. 13. 34. -34. 35. 12.")

	def testBadPolygon(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field POS: Invalid SIAPv2 POLYGON: '12 13 34 -34 35 1...' (need"
				" more than three coordinate *pairs*)",
			siap.parseSIAP2Geometry,
			("POLYGON 12 13 34 -34 35 12 22.3290032",))


class SIAP2ServiceTest(testhelpers.VerboseTest):
	resources = [("data", _siapTestTable), 
		# we want spectra in the table so we can make sure they don't come back.
		("spectra", tresc.ssaTestTable)]

	def _doQuery(self, params):
		return base.resolveCrossId("//siap2#sitewide").run(
			"siap2.xml", params).original.getPrimaryTable()

	def testBasicCooQuery(self):
		res = self._doQuery({"POS": ["CIRCLE 4 44 0.5"]})
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(res.rows[0]["access_estsize"], 81)
		self.assertEqual(res.rows[0]["access_url"], 
			"http://localhost:8080/getproduct?key=image/(1, 45)/(4.1, 1.1)")
		for info in res.getMeta("info"):
			if info.infoName=="queryPars":
				self.assertEqual(info.getContent(), 
					"{'pos0': <pgsphere Circle Unknown 4. 44. 0.5>}")
				self.assertEqual(info.infoValue, 
					"(s_region &&%(pos0)s) AND (dataproduct_type in ('image', 'cube'))")
				break

	def testDualCooQuery(self):
		res = self._doQuery({"POS": ["CIRCLE 4 44 0.5", "RANGE 250 260 89 90"]})
		for info in res.getMeta("info"):
			if info.infoName=="queryPars":
				self.assertEqual(info.infoValue, 
					'((s_region &&%(pos0)s) OR (s_region &&%(pos1)s))'
					" AND (dataproduct_type in ('image', 'cube'))")
				self.assertEqual(info.getContent(), 
					"{'pos0': <pgsphere Circle Unknown 4. 44. 0.5>, 'pos1':"
					" <pgsphere\nPositionInterval Unknown 250. 89. 260. 90.>}")
				break
		self.assertEqual(len(res.rows), 2)

	def testBANDQuery(self):
		res = self._doQuery({"BAND": ["-Inf 0.5", "40 60", "165 +Inf"]})
		self.assertEqual(len(res.rows), 5)
		for info in res.getMeta("info"):
			if info.infoName=="queryPars":
				self.assertEqual(info.infoValue, 
					'((%(BAND1)s < em_max AND %(BAND0)s > em_min)'
					' OR (%(BAND3)s < em_max AND %(BAND2)s > em_min)'
					' OR (%(BAND5)s < em_max AND %(BAND4)s > em_min))'
					" AND (dataproduct_type in ('image', 'cube'))")

	def testCombinedQuery(self):
		res = self._doQuery({"BAND": ["-Inf 0.5", "40 60"],
			"POS": ["CIRCLE 4 44 0.5", "RANGE 250 260 89 90"]})
		for info in res.getMeta("info"):
			if info.infoName=="queryPars":
				self.assertEqual(info.infoValue, 
					'((s_region &&%(pos0)s) OR (s_region &&%(pos1)s)) AND'
					' ((%(BAND1)s < em_max AND %(BAND0)s > em_min) OR'
					' (%(BAND3)s < em_max AND %(BAND2)s > em_min))'
					" AND (dataproduct_type in ('image', 'cube'))")
		self.assertEqual(len(res.rows), 1)

	def testDPConstraint(self):
		res = self._doQuery({"INSTRUMENT": ["DaCHS test suite"]})
		# this would return the ssaptest spectra if not for the empty constraint
		self.assertEqual(len(res.rows), 0)
		# just make sure ssaptest actually is in ivoa.obscore
		spectra = list(self.spectra.connection.query(
			"SELECT * FROM ivoa.obscore"
			" WHERE instrument_name='DaCHS test suite'"))
		self.assertEqual(len(spectra), 6)

	def testDPOverride(self):
		res = self._doQuery({"INSTRUMENT": ["cube"]})
		# TODO: Add some cubes at some point
		self.assertEqual(len(res.rows), 0)
	
	def testFOV(self):
		res = self._doQuery({"FOV": ["1 2.5", "11 +Inf"]})
		self.assertEqual(len(res.rows), 6)
	
	def testTIME(self):
		res = self._doQuery({"TIME": ["-Inf 55200", "55300.5 55302.3"]})
		self.assertEqual(len(res.rows), 2)
	
	def testPOLPositive(self):
		res = self._doQuery({"POL": ["RR", "LL"]})
		self.assertEqual(len(res.rows), 9)

	def testPOLNegative(self):
		res = self._doQuery({"POL": ["I", "Q", "U", "LR", "X"]})
		self.assertEqual(len(res.rows), 0)


if __name__=="__main__":
	testhelpers.main(ImportTest)
