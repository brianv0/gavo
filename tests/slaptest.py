"""
Tests for slap tables and services
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import api
from gavo import svcs
from gavo.helpers import testtricks
from gavo.web import vodal

import tresc

class _SLAPTable(tresc.RDDataResource):
	rdName = "data/slaptest"
	dataId = "import"

slapTestTable = _SLAPTable()


class TestWithSLAPTable(testhelpers.VerboseTest):
	resources = [("table", slapTestTable)]

	def runService(self, params):
		res = api.resolveCrossId("data/slaptest#s").run("slap.xml", params)
		return res.original


class ImportingTest(TestWithSLAPTable):
	def testValues(self):
		line = list(self.table.connection.queryToDicts(
			"select * from test.slaptest where chemical_element='Mo'"))[0]
		self.assertAlmostEqual(line.pop("initial_level_energy"), 
			1.65537152014313e-26)
		self.assertAlmostEqual(line.pop("final_level_energy"),  
			4.96611457698311e-18)
		self.assertEqual(line, {
			'id_status': u'identified', 
			'initial_name': u'Upper Level', 
			'linename': u'Mo 400 A', 
			'final_name': u'Lower Level', 'pub': u'2003junk.yard.0123X', 
			'chemical_element': u'Mo', 'wavelength': 4e-08})
		
	def testSimpleMeta(self):
		self.assertEqual(
			self.table.tableDef.getColumnByName("wavelength").utype,
			"ssldm:Line.wavelength.value")


class _SLAPMetadata(testhelpers.TestResource):
	resources = [("slapTable", slapTestTable)]

	def make(self, dependents):
		ctx = testhelpers.FakeContext(FORMAT="Metadata")
		res = vodal.SLAPRenderer(ctx,
			api.resolveCrossId("data/slaptest#s")).renderHTTP(ctx)
		tree = testhelpers.getXMLTree(res, debug=False)
		return tree


class ServiceMetadataTest(testhelpers.VerboseTest):
	resources = [("tree", _SLAPMetadata())]

	def testWavelength(self):
		params = self.tree.xpath("//PARAM[@name='INPUT:wavelength']")
		self.assertEqual(len(params), 1)
		param = params[0]
		self.assertEqual(param.get("utype"), "ssldm:Line.wavelength.value")
		self.assertEqual(param.get("unit"), "m")

	def testServiceKey(self):
		param = self.tree.xpath("//PARAM[@name='INPUT:VERB']")[0]
		self.assertEqual(len(param.xpath("VALUES/OPTION")), 3)
	
	def testFieldsDeclared(self):
		param = self.tree.xpath("//FIELD[@ID='wavelength']")[0]
		self.assertEqual(param.get("utype"), "ssldm:Line.wavelength.value")

	def testQueryStatus(self):
		self.assertEqual(
			self.tree.xpath("RESOURCE/INFO[@name='QUERY_STATUS']")[0
				].get("value"), "OK")


class ServiceConstraintsTest(TestWithSLAPTable):
	def testChemicalElement(self):
		res = self.runService({"CHEMICAL_ELEMENT": ["Mo"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0]["chemical_element"], "Mo")

	def testChemicalElements(self):
		res = self.runService({"CHEMICAL_ELEMENT": ["Mo,Bi"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 2)
		self.assertEqual(set(r["chemical_element"] for r in res), 
			set(["Mo", "Bi"]))

	def testWavelength(self):
		res = self.runService({"WAVELENGTH": ["4e-8/1e-7"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0]["chemical_element"], "Mo")

	def testInitialEnergy(self):
		res = self.runService({"INITIAL_LEVEL_ENERGY": ["1.1e-29/"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 2)
		self.assertEqual(set(r["chemical_element"] for r in res), 
			set(["Mo", "Bi"]))

	def testInitialEnergy(self):
		res = self.runService({"FINAL_LEVEL_ENERGY": ["/5e-18"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 2)
		self.assertEqual(set(r["chemical_element"] for r in res), 
			set(["Mo", "H"]))

	def testMAXREC(self):
		res = self.runService({"MAXREC": ["1"]}
			).getPrimaryTable().rows
		self.assertEqual(len(res), 1)


class _SLAPRegistryRecord(testhelpers.TestResource):
	def make(self, dependents):
		from gavo.registry import capabilities
		from gavo.web import vosi
		publication = api.resolveCrossId("data/slaptest#s").publications[0]
		res = vosi.CAP.capabilities[
			capabilities.getCapabilityElement(publication)].render()
		return testhelpers.getXMLTree(res, debug=False), res


class CapabilityTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("cap", _SLAPRegistryRecord())]

	def testValid(self):
		self.assertValidates(self.cap[1])

	def testType(self):
		self.assertEqual(self.cap[0][0].get(
			"{http://www.w3.org/2001/XMLSchema-instance}type"),
			"slap:SimpleLineAccess")

	def testStandardId(self):
		self.assertEqual(self.cap[0][0].get("standardID"),
			"ivo://ivoa.net/std/SLAP")

	def testComplianceLevel(self):
		self.assertEqual(self.cap[0][0].xpath("complianceLevel")[0].text,
			"full")

	def testDataSource(self):
		self.assertEqual(self.cap[0][0].xpath("dataSource")[0].text,
			"theoretical")

	def testTestQuery(self):
		self.assertEqual(self.cap[0][0].xpath("testQuery/queryDataCmd")[0].text,
			"MAXREC=1")


if __name__=="__main__":
	testhelpers.main(ImportingTest)
