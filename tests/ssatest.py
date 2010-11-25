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
		res.drop().commit().close()


_ssaTable = _SSATable()


class ImportTest(testhelpers.VerboseTest):
	resources = [("ssaTable", _ssaTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.row1 = self.ssaTable.getRow("ivo://test.inv/test1")

	def testImported(self):
		self.assertEqual(self.row1["ssa_dstitle"], "test spectrum 1")
	
	def testLocation(self):
		self.assertEqual(self.row1["ssa_location"], None)


class CoreTest(testhelpers.VerboseTest):
	resources = [("ssaTable", _ssaTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.core = ssap.SSAPCore(
			None, 
			queriedTable=self.ssaTable.tableDef).finishElement()
		self.service = svcs.Service(
			None,
			core=self.core).finishElement()
	
	def testBadRequestRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "folly"}, "dal.xml")

	def testWithPos(self):
		self.service.runFromDict(
			{"REQUEST": "queryData", "POS": "10%2c+15", "SIZE": "0.5"}, "dal.xml")



if __name__=="__main__":
	testhelpers.main(CoreTest)
