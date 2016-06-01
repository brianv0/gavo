"""
Some tests around the SSAP infrastructure.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import gc
import re
import tempfile

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import products
from gavo.protocols import sdm
from gavo.protocols import ssap
from gavo.utils import DEG, ElementTree, pyfits

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
			None)
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_fluxucd").value, 
			"phot.flux.density;em.wl")


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


class _SSATestRowmaker(testhelpers.TestResource):
	def make(self, ignored):
		rd = testhelpers.getTestRD("ssatest")
		td = rd.getById("hcdtest").change(onDisk=False)
		rowmaker = rd.getById("makeRow").compileForTableDef(td)
		vars = {"dstitle": "testing",
			"id": "f",
			"specstart": 10,
			"specend": 20,
			"specext": 10,
			"bandpass": "ultracool",
			"alpha": 1,
			"delta": -81.,
			"dateObs": 2455000.3,
			"targetName": "f star",
			"prodtblAccref": "test/junk",
			"prodtblOwner": None,
			"prodtblEmbargo": None,
			"prodtblPath": "/a/b/c",
			"prodtblTable": "test.none",
			"prodtblMime": "text/wirr",
			"prodtblFsize": -23,
			"redshift": None,
		}

		def wrappedRowmaker(updates):
			actualVars = vars.copy()
			actualVars.update(updates)
			return rowmaker(actualVars, td)

		return wrappedRowmaker


class ProcTest(testhelpers.VerboseTest):
	resources = [("rowmaker", _SSATestRowmaker())]

	def testObsDateMJD(self):
		self.assertEqual(self.rowmaker({"dateObs": 54200.25})["ssa_dateObs"],
			54200.25)

	def testObsDateJD(self):
		self.assertEqual(self.rowmaker({"dateObs": 2454200.25})["ssa_dateObs"],
			54199.75)

	def testObsDateISO(self):
		self.assertAlmostEqual(self.rowmaker({"dateObs": "1998-10-23T05:04:02"})[
			"ssa_dateObs"],
			51109.211134259123)

	def testObsDateTimestamp(self):
		self.assertAlmostEqual(self.rowmaker({"dateObs": 
			datetime.datetime(1998, 10, 23, 05, 04, 02)})[
			"ssa_dateObs"],
			51109.211134259123)

	def testObsDateNULL(self):
		self.assertEqual(self.rowmaker({"dateObs": None})["ssa_dateObs"],
			None)


class _WithSSATableTest(testhelpers.VerboseTest):
	resources = [("ssaTable", tresc.ssaTestTable)]
	renderer = "ssap.xml"

	def runService(self, id, params, renderer=None):
		if renderer is None:
			renderer = self.renderer
		return getRD().getById(id).run(renderer, params)


class ImportTest(_WithSSATableTest):

	def testImported(self):
		row = self.ssaTable.getRow("data/spec1.ssatest")
		self.assertEqual(row["ssa_dstitle"], "test spectrum 1")
	
	def testLocation(self):
		row = self.ssaTable.getRow("data/spec1.ssatest")
		self.assertAlmostEqual(row["ssa_location"].x, 10.1*DEG)


class ImportProcTest(testhelpers.VerboseTest):
	def testStandardPubDID(self):
		table = rsc.makeData(getRD().getById("test_macros")).getPrimaryTable()
		self.failUnless(table.rows[0]["pubDID"].startswith(
			"ivo://x-unregistred/~?data/spec"))


class CoreQueriesTest(_WithSSATableTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inDict, ids = sample
		inDict["REQUEST"] = "queryData"
		res = self.runService("s", inDict)
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
		({"PUBDID": "ivo://test.inv/test2"},
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
		({"FLUXCALIB": "CALIBRATED"},
			[]),
		({"FLUXCALIB": "unCALIBRATED"},
			['test1', 'test3', 'test2']),
#25
		({"SPECRP": "/1e-13"},
			[]),
		({"SPECRP": "1e-13/"},
			['test1', 'test3', 'test2']),
		({"SPATRES": "/1e-13"},
			['test1', 'test3', 'test2']), # (no spatial resolution given in test set)
		({"SPATRES": "1e-13/"},
			['test1', 'test3', 'test2']),
		({"WAVECALIB": "calibrated"},
			['test1', 'test3', 'test2']),
#30
		({"WAVECALIB": "approximate"},
			[]),
		({"COLLECTION": "test set"},
			['test1', 'test3', 'test2']),
		({"COLLECTION": "Test set"},
			[]),
		({"FORMAT": "application/x-votable+xml,image/fits"},
			["test1", "test2", "test3"]),

	]


class CoreMiscTest(_WithSSATableTest):
	def testRejectWithoutREQUEST(self):
		inDict= {"POS": "12,12",
			"SIZE": "1"}
		self.assertRaisesWithMsg(base.ValidationError,
			"Field REQUEST: Missing or invalid value for REQUEST.",
			self.runService,
			("s", inDict))
	
	def testDefaultRequest(self):
		service = getRD().getById("s")
		service.setProperty("defaultRequest", "querydata")
		try:
			res = self.runService("s", 
				{"BAND": "4.5e-7/7.5e-7", "FORMAT": "votable"})
			self.assertEqual(
				set([row["ssa_pubDID"].split("/")[-1] 
					for row in res.original.getPrimaryTable()]),
				set(["test1", "test2", "test3"]))
		finally:
			service.clearProperty("defaultRequest")


class _SDMDatalinkMetaData(testhelpers.TestResource):
	resources = [("ssaTable", tresc.ssaTestTable)]

	def make(self, dependents):
		res = getRD().getById("c").run("ssap.xml", 
			{"REQUEST": "queryData"})
		tree = testhelpers.getXMLTree(res.original[1], debug=False)
		return (tree.xpath('//RESOURCE[@type="meta"]')[0],
			tree.xpath('//RESOURCE[@type="meta"]')[1], tree)


class SDMDatalinkMetaTest(testhelpers.VerboseTest):
	resources = [("data", _SDMDatalinkMetaData())]

	def testEnumeration(self):
		formats = [el.get("value")
			for el in self.data[0].xpath(
				"GROUP[@name='inputParams']/PARAM[@name='FORMAT']/VALUES/OPTION")]
		self.failUnless("application/fits" in formats)

	def testLimits(self):
		self.assertAlmostEqual(
			float(self.data[0].xpath(
				"GROUP/PARAM[@name='LAMBDA_MAX']/VALUES/MIN")[0].get("value")),
			4e-7)
		self.assertAlmostEqual(
			float(self.data[0].xpath(
				"GROUP/PARAM[@name='LAMBDA_MIN']/VALUES/MAX")[0].get("value")), 
			8e-7)

	def testLeftOverEnumeration(self):
		self.assertEqual(set(el.get("value") for el in 
				self.data[0].xpath("GROUP/PARAM[@name='FLUXCALIB']/VALUES/OPTION")), 
			set(['UNCALIBRATED', 'RELATIVE']))

	def testAccessURLGivenDS(self):
		self.assertEqual(self.data[0].xpath(
				"PARAM[@name='accessURL']")[0].get("value"),
			"http://localhost:8080/data/ssatest/dl/dlget")

	def testIdColDeclaredDS(self):
		param = self.data[0].xpath("GROUP/PARAM[@name='ID']")[0]
		self.assertEqual(param.get("ucd"), "meta.id;meta.main")
		self.assertEqual(param.get("ref"), "ssa_pubDID")

	def testAccessURLGivenDL(self):
		self.assertEqual(self.data[1].xpath(
				"PARAM[@name='accessURL']")[0].get("value"),
			"http://localhost:8080/data/ssatest/dl/dlmeta")
	
	def testIdColDeclaredDL(self):
		param = self.data[1].xpath("GROUP/PARAM[@name='ID']")[0]
		self.assertEqual(param.get("ucd"), "meta.id;meta.main")
		srcField = self.data[-1].xpath(
			"//FIELD[@ID='%s']"%param.get("ref"))[0]
		self.assertEqual(srcField.get("name"), "ssa_pubDID")
	

class SDMDatalinkTest(_WithSSATableTest):

	renderer = "dlget"

	def testRejectWithoutPUBDID(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field ID: ID is mandatory with dlget",
			self.runService,
			("dl", {}))

	def testVOTDelivery(self):
		res = self.runService("dl",
			{"ID": 'ivo://test.inv/test1', "FORMAT": "application/x-votable+xml"})
		mime, payload = res.original
		self.assertEqual(mime, "application/x-votable+xml")
		self.failUnless('xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01'
			in payload)
		self.failUnless('QJtoAAAAAABAm2g' in payload)

	def testTextDelivery(self):
		res = self.runService("dl",
			{"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain"})
		mime, payload = res.original
		self.failUnless(isinstance(payload, str))
		self.failUnless("1754.0\t1754.0\n1755.0\t1753.0\n"
			"1756.0\t1752.0" in payload)

	def testCutoutFull(self):
		res = self.runService("dl",
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["text/plain"], "LAMBDA_MIN": ["1.762e-7"],
				"LAMBDA_MAX": ["1.764e-7"]})
		mime, payload = res.original
		self.assertEqual(payload, 
			'1762.0\t1746.0\n1763.0\t1745.0\n1764.0\t1744.0\n')
		self.failIf('<TR><TD>1756.0</TD>' in payload)

	def testCutoutHalfopen(self):
		res = self.runService("dl",
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["application/x-votable+xml;serialization=tabledata"], 
				"LAMBDA_MIN": ["1.927e-7"]})
		mime, payload = res.original
		self.failUnless('xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01'
			in payload)
		self.failUnless('<TR><TD>1927.0</TD><TD>1581.0</TD>' in payload)
		self.failIf('<TR><TD>1756.0</TD>' in payload)
		tree = testhelpers.getXMLTree(payload, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@utype="
			"'spec:Spectrum.Char.SpectralAxis.Coverage.Bounds.Start']"
			)[0].get("value"), "1.927e-07")
		self.assertAlmostEqual(float(tree.xpath("//PARAM[@utype="
			"'spec:Spectrum.Char.SpectralAxis.Coverage.Bounds.Extent']"
			)[0].get("value")), 1e-10)

	def testEmptyCutoutFails(self):
		res = self.runService("dl", {"ID": 'ivo://test.inv/test1', 
				"FORMAT": "application/x-votable+xml",
				"LAMBDA_MAX": "1.927e-8"})
		mime, payload = res.original
		self.assertTrue('<STREAM encoding="base64"></STREAM>' in payload)

	def testOriginalCalibOk(self):
		mime, payload = self.runService("dl",
			{"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain", 
				"FLUXCALIB": "UNCALIBRATED"}).original
		self.failUnless(payload.endswith("1928.0	1580.0\n"))

	def testNormalize(self):
		mime, payload = getRD().getById("dl").run("ssap.xml",
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": "application/x-votable+xml;serialization=tabledata", 
				"LAMBDA_MIN": ["1.9e-7"], "LAMBDA_MAX": ["1.92e-7"], 
				"FLUXCALIB": "RELATIVE"}).original
		self.failUnless("<TD>1900.0</TD><TD>0.91676" in payload)
		tree = testhelpers.getXMLTree(payload, debug=False)
		self.assertEqual(tree.xpath(
			"//PARAM[@utype='spec:Spectrum.Char.FluxAxis.Calibration']")[0].get(
				"value"),
			"RELATIVE")

	def testBadCalib(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field FLUXCALIB: 'ferpotschket' is not a valid value for FLUXCALIB",
			self.runService,
			("dl", {"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain", 
				"FLUXCALIB": ["ferpotschket"]}))

	def testBadPubDID(self):
		self.assertRaisesWithMsg(svcs.UnknownURI,
			"No spectrum with this pubDID known here (pubDID: ivo://test.inv/bad)",
			self.runService,
				("dl", {"ID": 'ivo://test.inv/bad'}))

	def testRandomParamFails(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field (various): The following parameter(s) are"
			" not accepted by this service: warp",
			self.runService,
			("dl", {"ID": 'ivo://test.inv/test1', 
				"warp": "infinity"}))

	def testCoreForgetting(self):
		gns = testhelpers.getMemDiffer()
		res = self.runService("dl",
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["text/plain"], "LAMBDA_MIN": ["1.762e-7"],
				"LAMBDA_MAX": ["1.764e-7"]})
		del res

		gc.collect()
		ns = gns()
		self.assertEqual(ns, [], "Spectrum cutout left garbage.")


class CoreNullTest(_WithSSATableTest):
# make sure empty parameters of various types are just ignored.
	totalRecs = 6

	def _getNumMatches(self, inDict):
		inDict["REQUEST"] = "queryData"
		return len(self.runService("s", inDict,
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
		res = self.runService("s",
			{"REQUEST": "queryData", "TOP": 1})
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMAXREC(self):
		res = self.runService("s",
			{"REQUEST": "queryData", "TOP": "3", "MAXREC": "1"})
		self.assertEqual(len(res.original.getPrimaryTable()), 1)

	def testMTIMEInclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = self.runService("s",
			{"REQUEST": "queryData", "MTIME": "%s/"%aMinuteAgo})
		self.assertEqual(len(res.original.getPrimaryTable()), 6)

	def testMTIMEExclusion(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = self.runService("s",
			{"REQUEST": "queryData", "MTIME": "/%s"%aMinuteAgo})
		self.assertEqual(len(res.original.getPrimaryTable()), 0)

	def testInsensitive(self):
		aMinuteAgo = datetime.datetime.utcnow()-datetime.timedelta(seconds=60)
		res = self.runService("s",
			utils.CaseSemisensitiveDict(
				{"rEQueST": "queryData", "mtime": "/%s"%aMinuteAgo}))
		self.assertEqual(len(res.original.getPrimaryTable()), 0)


class _RenderedSSAMetadata(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		res = getRD().getById("s").run("ssap.xml",
			{"REQUEST": "queryData", "FORMAT": "Metadata"})
		assert res.original[0]=="application/x-votable+xml"
		rawVOT = res.original[-1]
		return rawVOT, testhelpers.getXMLTree(rawVOT, debug=False)

class SSAMetaResponseTest(testhelpers.VerboseTest):
	resources = [("meta", _RenderedSSAMetadata())]

	def testIsVOTable(self):
		self.assertTrue("<VOTABLE" in self.meta[0])
	
	def testSizeInput(self):
		matches = self.meta[1].xpath("//PARAM[@name='INPUT:SIZE']")
		self.assertEqual(len(matches), 1)
		par = matches[0]
		self.assertEqual(par[0].text,
			"Size of the region of interest around POS")

	def testStandardFieldPresent(self):
		self.assertTrue(re.search('<FIELD[^>]*name="accref"', self.meta[0]))

	def testCustomFieldPresent(self):
		self.assertTrue(re.search('<FIELD[^>]*name="excellence"', self.meta[0]))
	
	def testUtypeGiven(self):
		matches = self.meta[1].xpath("//FIELD[@utype='ssa:Curation.PublisherDID']")
		self.assertEqual(len(matches), 1)
	
	def testInstrumentDefined(self):
		matches = self.meta[1].xpath("//PARAM[@utype='ssa:DataID.Instrument']")
		self.assertEqual(matches[0].get("value"), "DaCHS test suite")
	
	def testMAXREC(self):
		matches = self.meta[1].xpath("//PARAM[@name='INPUT:MAXREC']")
		self.assertEqual(len(matches), 1)
		self.assertEqual(matches[0].get("datatype"), "int")
	
	def testVERB(self):
		matches = self.meta[1].xpath("//PARAM[@name='INPUT:VERB']")
		self.assertEqual(len(matches), 1)
		self.assertEqual(
			matches[0].xpath("VALUES/OPTION[@value='1']")[0].get("name"),
			"terse")


class CoreFailuresTest(_WithSSATableTest):
	def testBadRequestRejected(self):
		self.assertRaises(api.ValidationError, self.runService, "s",
			{"REQUEST": "folly"})

	def testBadBandRejected(self):
		self.assertRaises(api.ValidationError, self.runService, "s",
			{"REQUEST": "queryData", "BAND": "1/2/0.4"})

	def testBadCustomInputRejected(self):
		self.assertRaises(api.ValidationError, self.runService, "s",
			{"REQUEST": "queryData", "excellence": "banana"})

	def testSillyFrameRejected(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field POS: Cannot match against coordinates given in EGOCENTRIC frame",
			self.runService,
			("s", {"REQUEST": "queryData", "POS": "0,0;EGOCENTRIC", "SIZE": "1"}))

	def testMalformedSize(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field SIZE: 'all' is not a valid literal for SIZE",
			self.runService,
			("s", {"REQUEST": "queryData", "POS": "0,0", "SIZE": "all"}))


class _RenderedSSAResponse(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		res = getRD().getById("c").run("ssap.xml",
			{"REQUEST": "queryData", "TOP": "4", "MAXREC": "4",
				"FORMAT": "votable", "_DBOPTIONS_ORDER": ["-ssa_targname"]})
		rawVOT = res.original[-1]
		return rawVOT, testhelpers.getXMLTree(rawVOT, debug=False)

_renderedSSAResponse = _RenderedSSAResponse()


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
		self.assertEqual(infoEl.text, "Exactly 4 rows were returned.  This means your query probably reached the match limit.  Increase MAXREC.")
	
	def testSSAUtype(self):
		table = self.docAndTree[1].find("RESOURCE/TABLE")
		self.failUnless(table.find("FIELD").attrib["utype"].startswith("ssa:"))

	def testTimestampCast(self):
		fields = self.docAndTree[1].findall("RESOURCE/TABLE/FIELD")
		for field in fields:
			if field.attrib["name"]=="ssa_dateObs":
				self.assertEqual(field.attrib["xtype"], "mjd")
				self.assertEqual(field.attrib["datatype"], "double")
				break
	
	def testAccrefPresent(self):
		self.failUnless("http://localhost:8080/getproduct" in self.docAndTree[0])

	def testEverythingExpanded(self):
		self.failIf("\\" in self.docAndTree[0])

	def testLocationArray(self):
		locationField = self.docAndTree[1].xpath(
			"//FIELD[@utype='ssa:Char.SpatialAxis.Coverage.Location.Value']")[0]
		self.assertEqual(locationField.attrib["name"], "location_arr")

		arrIndex = list(f for f in locationField.getparent().iterchildren()
				if f.tag=='FIELD').index(locationField)
		valEl = self.docAndTree[1].xpath(
			"//TABLEDATA/TR[1]/TD[%s]"%(arrIndex+1))[0]
		self.failUnless(re.match("10.10000[0-9]* 15.199999[0-9]*", valEl.text))

		valEl = self.docAndTree[1].xpath(
			"//TABLEDATA/TR[4]/TD[%s]"%(arrIndex+1))[0]
		self.failUnless(re.match("NaN NaN", valEl.text))

		valEl = self.docAndTree[1].xpath(
			"//TABLEDATA/TR[4]/TD[%s]"%(arrIndex-1))[0]
		self.failUnless(re.match("NaN", valEl.text))
		valEl = self.docAndTree[1].xpath(
			"//TABLEDATA/TR[4]/TD[%s]"%(arrIndex))[0]
		self.failUnless(re.match("NaN", valEl.text))

	def testPreviewColumn(self):
		previewField = self.docAndTree[1].xpath(
			"//FIELD[@ucd='meta.ref.url;datalink.preview']")[0]
		previewIndex = list(f for f in previewField.getparent().iterchildren()
			if f.tag=='FIELD').index(previewField)
		self.assertEqual(self.docAndTree[1].xpath(
			"//TABLEDATA/TR[1]/TD[%s]"%(previewIndex+1))[0].text,
			"http://localhost:8080/getproduct/data/spec1.ssatest.vot?preview=True")

	def testDatalinkResourcePresent(self):
		_, tree = self.docAndTree
		self.assertEqual(len(tree.xpath(
			"//RESOURCE[@utype='adhoc:service']")), 2)
		# TODO: if the datalink meta link is what we want, add a few tests
		# for that here.


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
		return rawVOT, testhelpers.getXMLTree(rawVOT, debug=False)


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
		group = self._getUniqueByXPath("//GROUP[@utype='spec:Spectrum.Target']")
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

	def testAccrefMapped(self):
		# the product link is made in a hack in SDMCore.
		tree = self.stringAndTree[1]
		p = tree.xpath("//PARAM[@name='accref']")[0]
		self.failUnless(p.get("value").startswith("http"))

	def testDescriptionOverridden(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath("//FIELD[@name='spectral']/DESCRIPTION")[0].text,
			"Wavelength")
	
	def testDescriptionDefault(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath("//FIELD[@name='flux']/DESCRIPTION")[0].text,
			"The dependent variable of this spectrum ("
			"see the ucd for its physical meaning)")
	
	def testSpectralUnitUsed(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath("//FIELD[@name='spectral']")[0].get("unit"),
			"Angstrom")

	def testSSAMetadataUnchanged(self):
		# FIXME: I guess SDM *should* adapt ssa metadata to whatever is
		# used in the spectra themselves.  Right now, the metadata units
		# are fixed by SSA, so DaCHS must not  do any conversions here
		p = self.stringAndTree[1].xpath("//PARAM[@name='ssa_specstart']")[0]
		self.assertEqual(p.get("unit"), "m")
		self.assertEqual(p.get("value"), "4e-07")


class _RenderedSDM2Response(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		ssaRow = list(deps["ssatable"].iterQuery(
			fragment="accref='data/spec2.ssatest'"))[0]
		_, rawVOT = sdm.formatSDMData(
			sdm.makeSDMDataForSSARow(ssaRow, 
				deps["ssatable"].tableDef.rd.getById("sdmdata"), "2"),
			base.votableType+";serialization=tabledata")
		return rawVOT, testhelpers.getXMLTree(rawVOT, debug=False)


class SDM2TableTest(testhelpers.VerboseTest):
	resources = [("stringAndTree", _RenderedSDM2Response())]

	def _getUniqueByXPath(self, xpath, root=None):
		if root is None:
			root = self.stringAndTree[1]
		resSet = root.xpath(xpath)
		self.assertEqual(len(resSet), 1)
		return resSet[0]

	def testPosition(self):
		res = self._getUniqueByXPath(
			"//PARAM[@utype='spec2:Char.SpatialAxis.Coverage.Location.Value']")
		self.assertEqual(res.get('value'), 
			'10.999999998889821 14.0000000011914')

	def testParameterSet(self):
		res = self._getUniqueByXPath(
			"//PARAM[@utype='spec2:DataID.DatasetID']")
		self.assertEqual(res.get('value'), 'ivo://test.inv/test2')

	def testSpecGroupsPresent(self):
		group = self._getUniqueByXPath("//GROUP[@utype='spec2:Target']")
		ref = self._getUniqueByXPath(
			'//PARAMref[@utype="spec2:Target.Name"]')
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
		table = tree.xpath("//TABLE")[0]
		self.assertEqual(table.get("utype"), "spec2:Spectrum")

	def testAccref(self):
		# the product link is made in a hack in SDMCore.
		tree = self.stringAndTree[1]
		p = tree.xpath("//PARAM[@ucd='meta.ref.url;meta.dataset']")[0]
		self.failUnless(p.get("value").startswith("http"))

	def testDescriptionOverridden(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath(
				"//FIELD[@utype='spec2:Data.SpectralAxis.Value']/DESCRIPTION")[0].text,
			"Wavelength")
	
	def testDescriptionDefault(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath(
				"//FIELD[@utype='spec2:Data.FluxAxis.Value']/DESCRIPTION")[0].text,
			"The dependent variable of this spectrum ("
			"see the ucd for its physical meaning)")
	
	def testSpectralUnitUsed(self):
		tree = self.stringAndTree[1]
		self.assertEqual(
			tree.xpath("//FIELD[@utype='spec2:Data.SpectralAxis.Value']"
				)[0].get("unit"),
			"Angstrom")

	def testSSAMetadataUnchanged(self):
		# FIXME: I guess SDM *should* adapt ssa metadata to whatever is
		# used in the spectra themselves.  Right now, the metadata units
		# are fixed by SSA, so DaCHS must not  do any conversions here
		p = self.stringAndTree[1].xpath(
			"//PARAM[@utype='spec2:Char.SpectralAxis.Coverage.Bounds.Start']")[0]
		self.assertEqual(p.get("unit"), "m")
		self.assertEqual(p.get("value"), "5e-07")
	
	def testModelName(self):
		p = self.stringAndTree[1].xpath(
			"//PARAM[@utype='spec2:Dataset.DataModel.Name']")[0]
		self.assertEqual(p.get("value"), "Spectrum-2.0")


class _RenderedSDMFITSResponse(testhelpers.TestResource):
	resources = [("ssatable", tresc.ssaTestTable)]

	def make(self, deps):
		sdmData = sdm.makeSDMDataForPUBDID('ivo://test.inv/test1', 
			getRD().getById("hcdtest"),
			getRD().getById("datamaker"))
		fitsBytes = sdm.formatSDMData(sdmData, "application/fits")[-1]
		self.tempFile = tempfile.NamedTemporaryFile()
		self.tempFile.write(fitsBytes)
		self.tempFile.flush()
		return pyfits.open(self.tempFile.name)
	
	def clean(self, res):
		self.tempFile.close()


class SDMFITSTest(testhelpers.VerboseTest):
	resources = [("hdus", _RenderedSDMFITSResponse())]

	def testPrimaryHDU(self):
		self.hdus[0].header.get("EXTEND", True)
		self.hdus[0].header.get("NAXIS", 0)

	def testSimpleUtypeTranslated(self):
		self.assertEqual(self.hdus[1].header.get("OBJECT"), "big fart nebula")
	
	def testParTypesPreserved(self):
		self.assertAlmostEqual(self.hdus[1].header.get("DEC"), 15.2)
	
	def testColumnUtype(self):
		hdr = self.hdus[1].header
		self.assertEqual(hdr["TUTYP1"], 'spec:spectrum.data.spectralaxis.value')
		self.assertEqual(hdr["TUTYP2"], 'spec:spectrum.data.fluxaxis.value')

	def testColumnComment(self):
		hdr = self.hdus[1].header
		self.assertEqual(hdr.ascard["TTYPE1"].comment, "Wavelength")

	def testValues(self):
		wl, flux = self.hdus[1].data[1]
		self.assertAlmostEqual(wl, 1755.)
		self.assertAlmostEqual(flux, 1753.)

	def testLimits(self):
		hdr = self.hdus[1].header
		self.assertEqual(hdr["TDMIN1"], 4e-7)
		self.assertEqual(hdr.cards["TDMIN1"].comment, "[m]")

	def testCalibration(self):
		hdr = self.hdus[1].header
		self.assertEqual(hdr["FLUX_CAL"], "UNCALIBRATED")

	def testBandwidthUnit(self):
		hdr = self.hdus[1].header
		card = hdr.ascard["SPEC_BW"]
		self.assertEqual(card.value, 1e-7)
		self.assertEqual(card.comment, "[m]")


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


class MixcTableTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	def testColumns(self):
		table = getRD().getById("mixctest")
		col = table.getColumnByName("ssa_fluxcalib")
		for attName, expected in [
			("utype", "ssa:Char.FluxAxis.Calibration"),
			("verbLevel", 15)]:
			self.assertEqual(getattr(col, attName), expected)
		col = table.getColumnByName("ssa_spectStatError")
		for attName, expected in [
			("utype", "ssa:Char.SpectralAxis.Accuracy.StatError"),
			("unit", "m"),
			("verbLevel", 15)]:
			self.assertEqual(getattr(col, attName), expected)
		col = table.getColumnByName("ssa_fluxStatError")
		for attName, expected in [
			("utype", "ssa:Char.FluxAxis.Accuracy.StatError"),
			("unit", "Jy"),
			("verbLevel", 15)]:
			self.assertEqual(getattr(col, attName), expected)

	def testUndefinedOnPar(self):
		col = getRD().getById("mixctest").getColumnByName("ssa_reference")
		self.assertEqual(col.unit, None)

	def testSkippedColumnsGone(self):
		td = getRD().getById("mixctest")
		colNames = set(c.name for c in td.columns)
		for name in ["ssa_timeSI", "ssa_spaceCalib"]:
			self.assertRaises(base.NotFoundError, td.getColumnByName, (name))

	def testFilling(self):
		data = rsc.makeData(getRD().getById("test_mixc"), connection=self.conn,
			runCommit=False)
		try:
			rows = list(self.conn.queryToDicts(
				"select ssa_dstitle, ssa_instrument, ssa_pubdid,"
				" ssa_reference, ssa_publisher from test.mixctest"))
			self.assertEqual(len(rows), 3)
			id = rows[0]["ssa_pubdid"].split("/")[-1]
			self.assertEqual(rows[0]["ssa_publisher"], "ivo://x-unregistred")
			self.assertEqual(rows[0]["ssa_instrument"], "Bruce Astrograph")
			self.assertEqual(rows[0]["ssa_reference"], "Paper on "+id)
			self.assertEqual(rows[0]["ssa_dstitle"], "junk from "+id)
		finally:
			self.conn.rollback()

	def testParams(self):
		table = getRD().getById("mixctest")
		param = table.getParamByName("ssa_fluxunit")
		self.assertEqual(param.value, "Jy")


if __name__=="__main__":
	from gavo.formats import texttable
	base.DEBUG = True
	testhelpers.main(SDMDatalinkTest)
