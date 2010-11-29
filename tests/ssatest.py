"""
Some tests around the SSAP infrastructure.
"""

import datetime

from gavo import api
from gavo import svcs
from gavo.protocols import ssap
from gavo.helpers import testhelpers


def getRD():
	return testhelpers.getTestRD("ssatest.rd")


class RDTest(testhelpers.VerboseTest):
# tests for some aspects of the ssap rd.
	def testUtypes(self):
		srcTable = getRD().getById("hcdtest")
		self.assertEqual("ssa:Access.Reference",
			srcTable.getColumnByName("accref").utype)

	def testDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_spectralSI").value, 
			"m")

	def testNullDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_creator").value, 
			None)

	def testOverriddenParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_instrument").value, 
			"DaCHS test suite")

	def testNormalizedDescription(self):
		self.failUnless("matches your query" in
			getRD().getById("hcdouttest").getColumnByName("ssa_score"
				).description)


class _SSATable(testhelpers.TestResource):
	def make(self, deps):
		dd = getRD().getById("test_import")
		data = api.makeData(dd)
		return data.getPrimaryTable()
	
	def clean(self, res):
		res.commit().close()
#		res.drop().commit().close()

_ssaTable = _SSATable()


class _WithSSATableTest(testhelpers.VerboseTest):
	resources = [("ssaTable", _ssaTable)]


class ImportTest(_WithSSATableTest):
	def setUp(self):
		_WithSSATableTest.setUp(self)
		self.row1 = self.ssaTable.getRow("ivo://test.inv/test1")

	def testImported(self):
		self.assertEqual(self.row1["ssa_dstitle"], "test spectrum 1")
	
	def testLocation(self):
		self.assertEqual(self.row1["ssa_location"], None)




class CoreResultTest(_WithSSATableTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inDict, ids = sample
		res = getRD().getById("s").runFromDict(inDict, "dal.xml")
		self.assertEqual(
			set([row["ssa_pubDID"].split("/")[-1] 
				for row in res.original.getPrimaryTable()]),
			set(ids))

	samples = [
		({"REQUEST": "queryData", "POS": "10%2c+15", "SIZE": "0.5"},
		["test1"]),
		({"REQUEST": "queryData", "POS": "10%2c+15", "SIZE": "2"},
		["test1", "test2"]),
		({"REQUEST": "queryData", "BAND": "/4.5e-7,6.5e-7/"},
		["test1", "test3"]),
		({"REQUEST": "queryData", "BAND": "4.5e-7/7.5e-7"},
		["test1", "test2", "test3"]),
		({"REQUEST": "queryData", "BAND": "U"},
		[]),
		({"REQUEST": "queryData", "BAND": "V,R"},
		["test2", "test3"]),
		({"REQUEST": "queryData", "TIME": "/2020-12-20T13:00:01"},
		["test1"]),
		({"REQUEST": "queryData", "FORMAT": "votable"},
		["test2"]),
		({"REQUEST": "queryData", "FORMAT": "compliant"},
		["test2"]),
		({"REQUEST": "queryData", "FORMAT": "native"},
		["test3"]),
		({"REQUEST": "queryData", "FORMAT": "image"},
		[]),
		({"REQUEST": "queryData", "FORMAT": "all"},
		["test1", "test2", "test3"]),
	]


class CoreFailuresTest(_WithSSATableTest):
	def setUp(self):
		_WithSSATableTest.setUp(self)
		self.service = getRD().getById("s")

	def testBadRequestRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "folly"}, "dal.xml")

	def testBadBandRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "queryData", "BAND": "1/2/0.4"})


if __name__=="__main__":
	testhelpers.main(CoreResultTest)
