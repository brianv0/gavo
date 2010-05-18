"""
Tests for services and cores.
"""

import datetime
import os

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo import protocols
from gavo.web import resourcebased

import testhelpers
import tresc


class PlainDBServiceTest(testhelpers.VerboseTest):
	"""tests for working db-based services, having defaults for everything.
	"""
	resources = [('conn', tresc.prodtestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.rd = testhelpers.getTestRD()

	def testEmptyQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runAsForm({})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_(set(["gabriel", "michael"])<=namesFound)

	def testOneParameterQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runAsForm({"accref": "~ *a.imp"})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" in namesFound)
		self.assert_("michael" not in namesFound)

	def testTwoParametersQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runAsForm({"accref": "~ *a.imp", "embargo": "< 2000-03-03"})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" not in namesFound)
		self.assert_("michael" not in namesFound)


class ComputedServiceTest(testhelpers.VerboseTest):
	"""tests a simple service with a computed core.
	"""
	def setUp(self):
		self.rd = testhelpers.getTestRD()

	def assertDatafields(self, columns, names):
		self.assertEqual(len(columns), len(names), "Wrong number of columns"
			" returned, expected %d, got %s"%(len(names), len(columns)))
		for c, n in zip(columns, names):
			self.assertEqual(c.name, n, "Got column %s instead of %s"%(c.name, n))

	def testStraightthrough(self):
		svc = self.rd.getById("basiccat")
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01"})
		self.assertEqual(res.original.getPrimaryTable().rows, [{'a': u'xy', 'c': 4, 'b': 3, 
			'e': datetime.datetime(2005, 10, 12, 12, 23, 1), 'd': 5}])

	def testVerblevelBasic(self):
		svc = self.rd.getById("basiccat")
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "verbosity": "2", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a"])
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "VERB": "1", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b"])
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "2", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "c", "d"])
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "3", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "c", "d", "e"])
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "HTML", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "c", "d", "e"])
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "c", "d"])

	def testMappedOutput(self):
		svc = self.rd.getById("convcat")
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "d"])
		self.assertEqual(res.original.getPrimaryTable().tableDef.columns[0].verbLevel, 15)
		self.assertEqual(res.original.getPrimaryTable().rows[0]['d'], 5000.)

	def testAdditionalFields(self):
		svc = self.rd.getById("convcat")
		res = svc.runAsForm({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_ADDITEM":["c", "e"]})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "d", "c", "e"])


class BrowsableTest(testhelpers.VerboseTest):
	"""tests for selection of URLs for browser users.
	"""
	def setUp(self):
		self.oldInputs = base.getConfig("inputsDir")
		base.setConfig("inputsDir", os.getcwd())

	def tearDown(self):
		base.setConfig("inputsDir", self.oldInputs)

	def testBrowseableMethod(self):
		service = testhelpers.getTestRD("pubtest.rd").getById("moribund")
		self.failUnless(service.isBrowseableWith("form"))
		self.failUnless(service.isBrowseableWith("external"))
		self.failIf(service.isBrowseableWith("static"))
		self.failIf(service.isBrowseableWith("scs.xml"))
		self.failIf(service.isBrowseableWith("oai.xml"))
	
	def testStaticWithIndex(self):
		service = testhelpers.getTestRD().getById("convcat")
		# service has an indexFile property
		self.failUnless(service.isBrowseableWith("static"))

	def testURLSelection(self):
		service = testhelpers.getTestRD("pubtest.rd").getById("moribund")
		self.assertEqual(service.getBrowserURL(), 
			"http://localhost:8080/data/pubtest/moribund/form")

	def testRelativeURLSelection(self):
		service = testhelpers.getTestRD("pubtest.rd").getById("moribund")
		self.assertEqual(service.getBrowserURL(fq=False), 
			"/data/pubtest/moribund/form")
	



if __name__=="__main__":
	testhelpers.main(ComputedServiceTest)
