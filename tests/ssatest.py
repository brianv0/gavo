"""
Some tests around the SSAP infrastructure.
"""

import datetime
import re

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import products
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
			getRD().getById("hcdtest").getParamByName("ssa_timeSI").value, 
			"s")

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


class _WithSSATableTest(testhelpers.VerboseTest):
	resources = [("ssaTable", tresc.ssaTestTable)]


class ImportTest(_WithSSATableTest):

	def testImported(self):
		row = self.ssaTable.getRow("data/spec1.ssatest")
		self.assertEqual(row["ssa_dstitle"], "test spectrum 1")
	
	def testLocation(self):
		row = self.ssaTable.getRow("data/spec1.ssatest")
		self.assertAlmostEqual(row["ssa_location"].x, 10.1*DEG)


class CoreQueriesTest(_WithSSATableTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inDict, ids = sample
		inDict["REQUEST"] = "queryData"
		res = getRD().getById("s").runFromDict(inDict, "ssap.xml")
		self.assertEqual(
			set([row["ssa_pubDID"].split("/")[-1] 
				for row in res.original.getPrimaryTable()]),
			set(ids))

	samples = [
		({"POS": "10,+15", "SIZE": "0.5", "FORMAT": "votable"},
			["test1"]),
		({"POS": "10,+15", "SIZE": "2", "FORMAT": "votable"},
			["test1", "test2"]),
		({"BAND": "/4.5e-7,6.5e-7/", "FORMAT": "votable"},
			["test1", "test3"]),
		({"BAND": "4.5e-7/7.5e-7", "FORMAT": "votable"},
			["test1", "test2", "test3"]),
		({"BAND": "U", "FORMAT": "votable"},
			[]),
#5
		({"BAND": "V,R", "FORMAT": "votable"},
			["test2", "test3"]),
		({"TIME": "/2020-12-20T13:00:01", "FORMAT": "votable"},
			["test1"]),
		({"FORMAT": "votable"},
			["test1", "test2", "test3"]),
		({"FORMAT": "compliant"},
			["test1", "test2", "test3"]),
		({"FORMAT": "native"},
			["test3"]),
#10
		({"FORMAT": "image"},
			[]),
		({"FORMAT": "all"},
			["test1", "test2", "test3"]),
		({"FORMAT": "ALL"},
			["test1", "test2", "test3"]),
		({"TARGETNAME": "booger star,rat hole in the yard"},
			["test2", "test3"]),
		({"PUBDID": "ivo:%2f%2ftest.inv%2ftest2"},
			["test2"]),
#15
		({"excellence": "/100"},
			["test2", "test3"]),
		({"POS": "10,+15"}, # POS without SIZE is ignored
			["test1", "test2", "test3"]),
		({"SIZE": "30"}, # splat sends SIZE without POS; ignore it in this case.
			["test1", "test2", "test3"]),
		({"WILDTARGET": "BIG*"},
			["test1"]),
		({"WILDTARGETCASE": "BIG*"},
			[]),
#20
		({"WILDTARGET": "b??g*"},
			["test2"]),
		({"WILDTARGET": "\*"},
			[]),
		({"WILDTARGET": "[br][oa]*"},
			["test2", "test3"]),
	]


class CoreMiscTest(_WithSSATableTest):
	def testRejectWithoutREQUEST(self):
		inDict= {"POS": "12,12",
			"SIZE": "1"}
		self.assertRaisesWithMsg(base.ValidationError,
			"Missing or invalid value for REQUEST.",
			getRD().getById("s").runFromDict,
			(inDict, "ssap.xml"))


class GetDataTest(_WithSSATableTest):
	def testGetdataDeclared(self):
		res = getRD().getById("c").runFromDict(
			{"REQUEST": "queryData"}, "ssap.xml")
		tree = testhelpers.getXMLTree(res.original[1])
		gpTable = tree.xpath('//TABLE[@name="generationParameters"]')[0]
		formats = [el.get("value")
			for el in gpTable.xpath("PARAM[@name='FORMAT']/VALUES/OPTION")]
		self.failUnless("application/fits" in formats)

	def testNormalServicesReject(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"No getData support on ivo://x-unregistred/data/ssatest/s",
			getRD().getById("s").runFromDict,
			({"REQUEST": "getData"}, "ssap.xml"))

	def testRejectWithoutPUBDID(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"PUBDID mandatory for getData",
			getRD().getById("c").runFromDict,
			({"REQUEST": "getData"}, "ssap.xml"))

	def testGetdataVOT(self):
		res = getRD().getById("c").runFromDict(
			{"REQUEST": "getData", "PUBDID": 'ivo://test.inv/test1'}, "ssap.xml")
		mime, payload = res.original
		self.assertEqual(mime, "application/x-votable+xml")
		self.failUnless('xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01'
			in payload)
		self.failUnless('QJtoAAAAAABAm2g' in payload)

	def testGetdataText(self):
		res = getRD().getById("c").runFromDict(
			{"REQUEST": "getData", "PUBDID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain"}, "ssap.xml")
		mime, payload = res.original
		self.failUnless("1754.0\t1754.0\n1755.0\t1753.0\n"
			"1756.0\t1752.0" in payload)


class CoreNullTest(_WithSSATableTest):
# make sure empty parameters of various types are just ignored.
	totalRecs = 6

	def _getNumMatches(self, inDict):
		inDict["REQUEST"] = "queryData"
		return len(getRD().getById("s").runFromDict(inDict, "ssap.xml"
			).original.getPrimaryTable().rows)
	
	def testSomeNULLs(self):
		self.assertEqual(self._getNumMatches({"TIME": "", "POS": ""}), 
			self.totalRecs)
	
	def testBANDNULL(self):
		self.assertEqual(self._getNumMatches({"BAND": ""}), self.totalRecs)

	def testFORMATNULL(self):
		self.assertEqual(self._getNumMatches({"FORMAT": ""}), self.totalRecs)

	def testFORMATALL(self):
		self.assertEqual(self._getNumMatches({"FORMAT": "ALL"}), self.totalRecs)


class MetaKeyTest(_WithSSATableTest):
# these are like CoreQueries except they exercise custom logic
	def testTOP(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "TOP": 1}, "ssap.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMAXREC(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "TOP": "3", "MAXREC": "1"}, "ssap.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMTIMEInclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "MTIME": "%s/"%aMinuteAgo}, "ssap.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 6)

	def testMTIMEExclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "MTIME": "/%s"%aMinuteAgo}, "ssap.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 0)

	def testInsensitive(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = getRD().getById("s").runFromDict(
			vodal.CaseSemisensitiveDict(
				{"rEQueST": "queryData", "mtime": "/%s"%aMinuteAgo}), "ssap.xml")
		self.assertEqual(len(res.original.getPrimaryTable()), 0)

	def testMetadata(self):
		res = getRD().getById("s").runFromDict(
			{"REQUEST": "queryData", "FORMAT": "Metadata"}, "ssap.xml")
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
			{"REQUEST": "folly"}, "ssap.xml")

	def testBadBandRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "queryData", "BAND": "1/2/0.4"}, "ssap.xml")

	def testBadCustomInputRejected(self):
		self.assertRaises(api.ValidationError, self.service.runFromDict,
			{"REQUEST": "queryData", "excellence": "banana"}, "ssap.xml")

	def testSillyFrameRejected(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Cannot match against coordinates given in EGOCENTRIC frame",
			self.service.runFromDict,
			({"REQUEST": "queryData", "POS": "0,0;EGOCENTRIC", "SIZE": "1"}, 
				"ssap.xml"))

	def testMalformedSize(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"'all' is not a valid literal for SIZE",
			self.service.runFromDict,
			({"REQUEST": "queryData", "POS": "0,0", "SIZE": "all"}, 
				"ssap.xml"))


class _RenderedSSAResponse(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		res = getRD().getById("c").runFromDict(
			{"REQUEST": "queryData", "TOP": "3", "MAXREC": "1"}, "ssap.xml")
		rawVOT = res.original[-1]
		return rawVOT, testhelpers.getXMLTree(rawVOT, debug=False)

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
		infoEl = self.docAndTree[1].xpath(
			"//RESOURCE/INFO[@name='QUERY_STATUS']")[0]
		self.assertEqual(infoEl.attrib["value"], "OVERFLOW")
		self.assertEqual(infoEl.text, "Exactly 1 rows were returned.  This means your query probably reached the match limit.  Increase MAXREC.")
	
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

	def testEverythingExpanded(self):
		self.failIf("\\" in self.docAndTree[0])




class SDMRenderTest(testhelpers.VerboseTest):
	resources = [("ssatable", tresc.ssaTestTable)]

	def testUnknownURI(self):
		pk = _FakeRAccref.fromString(
			"dcc://data.ssatest/mksdm?data/ssatest/foobar")
		pk.setProductsRow({
			"accref": "data/ssatest/foobar",
			"accessPath": "dcc://data.ssatest/mksdm?foobar",
			"mime": "application/fits"})
		prod = list(base.makeStruct(products.ProductsGrammar, groups=[]
			).parse([pk]))[0]["source"]
		self.assertEqual(prod.name, "foobar")
		self.assertEqual(prod.core, getRD().getById("mksdm"))
		self.assertRaisesWithMsg(
			svcs.UnknownURI,
			"No spectrum with accref foobar known here",
			list,
			(prod.iterData(),))


class _FakeRAccref(products.RAccref):
	"""a RAccref that lets you manually provide a productsRow.
	"""
	def setProductsRow(self, val):
		defaults = {
			"embargo": None,
			"mime": "application/x-votable+xml",}
		defaults.update(val)
		self._productsRowCache = defaults


class _RenderedSDMResponse(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		rAccref = _FakeRAccref.fromString("bar")
		rAccref.setProductsRow({
			"accref": "spec1.ssatest.vot",
			"accessPath": "dcc://data.ssatest/mksdm?data/spec1.ssatest.vot",})
		prod = products.getProductForRAccref(rAccref)
		rawVOT = "".join(prod.iterData(svcs.QueryMeta({"_TDENC": True})))
		return rawVOT, testhelpers.getXMLTree(rawVOT)


class SDMTableTest(testhelpers.VerboseTest):
# tests for core and rendering of Spectral Data Model VOTables.
	resources = [("stringAndTree", _RenderedSDMResponse())]

	def _getUniqueByXPath(self, xpath, root=None):
		if root is None:
			root = self.stringAndTree[1]
		resSet = root.xpath(xpath)
		self.assertEqual(len(resSet), 1)
		return resSet[0]

	def testParameterSet(self):
		res = self._getUniqueByXPath("//PARAM[@name='ssa_pubDID']")
		self.assertEqual(res.get('value'), 'ivo://test.inv/test1')

	def testSpecGroupsPresent(self):
		group = self._getUniqueByXPath("//GROUP[@utype='spec:Target']")
		ref = self._getUniqueByXPath(
			'//PARAMref[@utype="spec:Spectrum.Target.Name"]')
		self.failIf(ref.get("ref") is None)
	
	def testReferentialIntegrity(self):
		#open("zw.vot", "w").write(self.stringAndTree[0])
		tree = self.stringAndTree[1]
		knownIds = set()
		for element in tree.xpath("//*[@ID]"):
			knownIds.add(element.get("ID"))
		for element in tree.xpath("//*[@ref]"):
			self.failUnless(element.get("ref") in knownIds,
				"%s is referred to but no element with this id present"%
					element.get("ref"))

	def testDataPresent(self):
		tree = self.stringAndTree[1]
		firstRow = tree.xpath("//TR")[0]
		self.assertEqual(
			[el.text for el in firstRow.xpath("TD")],
			["3000.0", "30.0"])

	def testContainerUtypes(self):
		tree = self.stringAndTree[1]
		votRes = tree.xpath("//RESOURCE")[0]
		self.assertEqual(votRes.get("utype"), "spec:Spectrum")
		table = votRes.xpath("//TABLE")[0]
		self.assertEqual(table.get("utype"), "spec:Spectrum")

	def testAccrefMappedAndUtype(self):
		# the product link is made in a hack in SDMCore.
		tree = self.stringAndTree[1]
		p = tree.xpath("//PARAM[@utype='spec:Spectrum.Access.Reference']")[0]
		self.failUnless(p.get("value").startswith("http"))


class _RenderedSEDResponse(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		rAccref = _FakeRAccref.fromString("bar?dm=sed")
		rAccref.setProductsRow({
			"accref": "spec1.ssatest.vot",
			"accessPath": "dcc://data.ssatest/mksdm?data/spec1.ssatest.vot",})
		prod = products.getProductForRAccref(rAccref)
		rawVOT = "".join(prod.iterData(svcs.QueryMeta({"_TDENC": True})))
		return rawVOT, testhelpers.getXMLTree(rawVOT)


class SEDTableTest(testhelpers.VerboseTest):
# Once we have an actual implementation of the SED data model, do
# this properly (right now, it's a horrendous hack just to
# please specview)
	resources = [("stringAndTree", _RenderedSEDResponse())]

	def testContainerUtypes(self):
		tree = self.stringAndTree[1]
		votRes = tree.xpath("//RESOURCE")[0]
		self.assertEqual(votRes.get("utype"), "sed:SED")
		table = votRes.xpath("//TABLE")[0]
		self.assertEqual(table.get("utype"), "sed:Segment")

	def testSpectUtype(self):
		spectField = self.stringAndTree[1].xpath("//FIELD[@name='spectral']")[0]
		self.assertEqual(spectField.get("utype"), 
			"sed:Segment.Points.SpectralCoord.Value")

	def testFluxUtype(self):
		spectField = self.stringAndTree[1].xpath("//FIELD[@name='flux']")[0]
		self.assertEqual(spectField.get("utype"), 
			"sed:Segment.Points.Flux.Value")


if __name__=="__main__":
	base.DEBUG = True
	testhelpers.main(SEDTableTest)
