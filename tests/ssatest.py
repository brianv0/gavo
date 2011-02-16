"""
Some tests around the SSAP infrastructure.
"""

import datetime
import re

from gavo import api
from gavo import svcs
from gavo.formats import votablewrite
from gavo.helpers import testhelpers
from gavo.protocols import ssap
from gavo.utils import DEG, ElementTree
from gavo.web import vodal

import tresc

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
			getRD().getById("foocore").outputTable.getColumnByName("ssa_score"
				).description)


class _SSATable(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]

	def make(self, deps):
		conn = deps["conn"]
		dd = getRD().getById("test_import")
		data = api.makeData(dd, connection=conn)
		return data.getPrimaryTable()
	
	def clean(self, res):
		res.drop().commit()

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
		self.assertAlmostEqual(self.row1["ssa_location"].x, 10.1*DEG)


class CoreQueriesTest(_WithSSATableTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inDict, ids = sample
		inDict["REQUEST"] = "queryData"
		res = getRD().getById("s").runFromDict(inDict, "dal.xml")
		self.assertEqual(
			set([row["ssa_pubDID"].split("/")[-1] 
				for row in res.original.getPrimaryTable()]),
			set(ids))

	samples = [
		({"POS": "10%2c+15", "SIZE": "0.5"},
		["test1"]),
		({"POS": "10%2c+15", "SIZE": "2"},
		["test1", "test2"]),
		({"BAND": "/4.5e-7,6.5e-7/"},
		["test1", "test3"]),
		({"BAND": "4.5e-7/7.5e-7"},
		["test1", "test2", "test3"]),
		({"BAND": "U"},
		[]),
		({"BAND": "V,R"},
		["test2", "test3"]),
		({"TIME": "/2020-12-20T13:00:01"},
		["test1"]),
		({"FORMAT": "votable"},
		["test2"]),
		({"FORMAT": "compliant"},
		["test2"]),
		({"FORMAT": "native"},
		["test3"]),
		({"FORMAT": "image"},
		[]),
		({"FORMAT": "all"},
		["test1", "test2", "test3"]),
		({"FORMAT": "all"},
		["test1", "test2", "test3"]),
		({"TARGETNAME": "booger star,rat hole in the yard"},
		["test2", "test3"]),
		({"PUBDID": "ivo:%2f%2ftest.inv%2ftest2"},
		["test2"]),
		({"excellence": "/100"},
		["test2", "test3"]),
	]


class MetaKeyTest(_WithSSATableTest):
# these are like CoreQueries except they exercise custom logic
	def testTOP(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "TOP": 1}, "dal.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMAXREC(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "TOP": "3", "MAXREC": "1"}, "dal.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMTIMEInclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "MTIME": "%s/"%aMinuteAgo}, "dal.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 3)

	def testMTIMEExclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "MTIME": "/%s"%aMinuteAgo}, "dal.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 0)

	def testInsensitive(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			vodal.CaseSemisensitiveDict(
				{"rEQueST": "queryData", "mtime": "/%s"%aMinuteAgo}), "dal.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 0)

	def testMetadata(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "FORMAT": "METADATA"}, "dal.xml")
		self.assertEqual(res.original[0], "application/x-votable+xml")
		val = res.original[1]
		self.failUnless("<VOTABLE" in val)
		self.failUnless('name="INPUT:SIZE"' in val)
		self.failUnless("ize of the region of interest around POS" in val)
		self.failUnless(re.search('<FIELD[^>]*name="accref"', val))
		self.failUnless(re.search('<FIELD[^>]*name="excellence"', val))
		self.failUnless(re.search(
			'<FIELD[^>]*utype="ssa:Curation.PublisherDID"', val))
		self.failUnless("DaCHS test suite" in re.search(
			'<PARAM[^>]*utype="ssa:DataID.Instrument"[^>]*>', 
			val).group(0))


class CoreFailuresTest(_WithSSATableTest):
	def setUp(self):
		_WithSSATableTest.setUp(self)
		self.service = getRD().getById("s")

	def testBadRequestRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "folly"}, "dal.xml")

	def testBadBandRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "queryData", "BAND": "1/2/0.4"}, "dal.xml")

	def testBadCustomInputRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "queryData", "excellence": "banana"}, "dal.xml")

	def testSillyFrameRejected(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Cannot match against coordinates given in EGOCENTRIC frame",
			self.service.runFromDict,
			({"REQUEST": "queryData", "POS": "0%2c0;EGOCENTRIC", "SIZE": "1"}, 
				"dal.xml"))


class _RenderedSSAResponse(testhelpers.TestResource):
	resources = [("ssatable", _ssaTable)]

	def make(self, deps):
		service = getRD().getById("s")
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "TOP": "3", "MAXREC": "1"}, "dal.xml")
		rawVOT = votablewrite.getAsVOTable(res.original,
			votablewrite.VOTableContext(suppressNamespace=True, tablecoding="td"))
		return rawVOT, ElementTree.fromstring(rawVOT)

_renderedSSAResponse = _RenderedSSAResponse()


def _pprintEtree(root):
	import subprocess
	p = subprocess.Popen(["xmlstarlet", "fo"], stdin=subprocess.PIPE)
	ElementTree.ElementTree(root).write(p.stdin)
	p.stdin.close()


class SSATableTest(testhelpers.VerboseTest):
	# tests for certain properties of rendered SSA table responses

	resources = [("docAndTree", _renderedSSAResponse)]

	def testSillyNSDeclPresent(self):
		self.failUnless('xmlns:ssa="http://www.ivoa.net/xml/DalSsap/v1.0"'
			in self.docAndTree[0])
	
	def testOverflowWarning(self):
		infoEl = self.docAndTree[1].find("RESOURCE/INFO")
		self.assertEqual(infoEl.attrib["name"], "QUERY_STATUS")
		self.assertEqual(infoEl.attrib["value"], "OVERFLOW")
		self.assertEqual(infoEl.text, "Exactly 1 rows were returned."
			" This means your query probably reached\nthe match limit."
			" Increase MAXREC.")
	
	def testSSAUtype(self):
		table = self.docAndTree[1].find("RESOURCE/TABLE")
		self.failUnless(table.find("FIELD").attrib["utype"].startswith("ssa:"))

	def testTimestampCast(self):
		fields = self.docAndTree[1].findall("RESOURCE/TABLE/FIELD")
		for field in fields:
			if field.attrib["name"]=="ssa_dateObs":
				self.assertEqual(field.attrib["xtype"], "adql:TIMESTAMP")
				self.assertEqual(field.attrib["datatype"], "char")
				break
	
	def testAccrefPresent(self):
		self.failUnless("http://localhost:8080/getproduct" in self.docAndTree[0])


if __name__=="__main__":
	testhelpers.main(SSATableTest)
