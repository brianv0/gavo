"""
Tests for services and cores.
"""

import datetime
import os

from nevow import context

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo import protocols
from gavo import svcs
from gavo.imp import formal
from gavo.helpers import testhelpers
from gavo.web import resourcebased

import tresc


class PlainDBServiceTest(testhelpers.VerboseTest):
	"""tests for working db-based services, having defaults for everything.
	"""
	resources = [("prodtbl", tresc.prodtestTable)]
	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.rd = testhelpers.getTestRD()

	def testEmptyQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runFromDict({})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_(set(["gabriel", "michael"])<=namesFound)

	def testOneParameterQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runFromDict({"accref": "~ *a.imp"})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" in namesFound)
		self.assert_("michael" not in namesFound)

	def testTwoParametersQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.runFromDict({"accref": "~ *a.imp", "embargo": "< 2000-03-03"})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" not in namesFound)
		self.assert_("michael" not in namesFound)


class ComputedServiceTest(testhelpers.VerboseTest):
	"""tests a simple service with a computed core.
	"""
	def setUp(self):
		self.rd = testhelpers.getTestRD("cores.rd")

	def assertDatafields(self, columns, names):
		self.assertEqual(len(columns), len(names), "Wrong number of columns"
			" returned, expected %d, got %s"%(len(names), len(columns)))
		for c, n in zip(columns, names):
			self.assertEqual(c.name, n, "Got column %s instead of %s"%(c.name, n))

	def testStraightthrough(self):
		svc = self.rd.getById("basiccat")
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01"})
		self.assertEqual(res.original.getPrimaryTable().rows, [{'a': u'xy', 'c': 4, 'b': 3, 
			'e': datetime.datetime(2005, 10, 12, 12, 23, 1), 'd': 5}])

	def testVerblevelBasic(self):
		svc = self.rd.getById("basiccat")
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "verbosity": "2", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a"])
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "VERB": "1", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b"])
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "2", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "c", "d"])
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "3", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "c", "d", "e"])
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "HTML", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "c", "d", "e"])
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_FORMAT": "VOTable"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "c", "d"])

	def testMappedOutput(self):
		svc = self.rd.getById("convcat")
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01"})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, ["a", "b", "d"])
		self.assertEqual(res.original.getPrimaryTable().tableDef.columns[0].verbLevel, 15)
		self.assertEqual(res.original.getPrimaryTable().rows[0]['d'], 5000.)

	def testAdditionalFields(self):
		svc = self.rd.getById("convcat")
		res = svc.runFromDict({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_ADDITEM":["c", "e"]})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "d", "c", "e"])


class BrowsableTest(testhelpers.VerboseTest):
	"""tests for selection of URLs for browser users.
	"""
	def testBrowseableMethod(self):
		service = testhelpers.getTestRD("pubtest.rd").getById("moribund")
		self.failUnless(service.isBrowseableWith("form"))
		self.failUnless(service.isBrowseableWith("external"))
		self.failIf(service.isBrowseableWith("static"))
		self.failIf(service.isBrowseableWith("scs.xml"))
		self.failIf(service.isBrowseableWith("pubreg.xml"))
		self.failIf(service.isBrowseableWith("bizarro"))
	
	def testStaticWithIndex(self):
		service = testhelpers.getTestRD().getById("basicprod")
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
	

class InputKeyTest(testhelpers.VerboseTest):
	"""tests for type/widget inference with input keys.
	"""
	def _getKeyProps(self, src):
		cd = base.parseFromString(svcs.CondDesc, src)
		ftype = cd.inputKeys[0].getCurrentFormalType()
		fwid = cd.inputKeys[0].getCurrentWidgetFactory()
		ctx = context.WovenContext()
		rendered = fwid(ftype).render(ctx, "foo", {}, None)
		return ftype, fwid, rendered

	def testAllAuto(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="foo" type="text"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.String))
		self.assertEqual(ftype.required, False)
		self.assertEqual(rendered.attributes["type"], "text")

	def testRequiredCondDesc(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc required="True"><inputKey name="foo" type="text"/></condDesc>')
		self.assertEqual(ftype.required, True)

	def testNotRequiredCondDesc(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="foo" type="text" required="True"/></condDesc>')
		self.assertEqual(ftype.required, False)

	def testWithFormalType(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="foo" type="text" formalType="int"/>'
			'</condDesc>')
		self.failUnless(isinstance(ftype, formal.types.Integer))

	def testWithOriginal(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey original="data/testdata#data.afloat"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.String))
		self.assertEqual(rendered.children[3].children[0].children[0],
			"[?num. expr.]")

	def testWithOriginalAndFT(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey original="data/testdata#data.afloat"'
				' formalType="int"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.Integer))

	def testWithEnumeratedOriginal(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey original="data/testdata#nork.cho"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.String))
		opts = list(rendered.children[0](None, None))
		self.assertEqual(opts[0].children[0].attributes["type"], "radio")

	def testManualWF(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey type="text" name="x" widgetFactory="'
				'widgetFactory(ScalingTextArea, rows=15)"/></condDesc>')
		self.assertEqual(rendered.attributes["rows"], 15)


class InputFieldSelectionTest(testhelpers.VerboseTest):
	# Tests for renderer-dependent selection and adaptation of db core 
	# input fields.
	
	resources = [("table", tresc.csTestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.service = testhelpers.getTestRD("cores").getById("cstest")

	def testForm(self):
		self.assertEqual(
			[(k.name, k.type) for k in self.service.getInputKeysFor("form")],
			[("hscs_pos", "text"), ("hscs_sr", "real"), ("mag", "vexpr-float")])

	def testSCS(self):
		self.assertEqual(
			[(k.name, k.type) for k in self.service.getInputKeysFor("scs.xml")],
			[('RA', 'double precision'), ('DEC', 'double precision'), 
				('SR', 'real'), ("mag", "vexpr-float")])


if __name__=="__main__":
	testhelpers.main(InputFieldSelectionTest)
