"""
Tests for services and cores.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import re
import os

from nevow import context
from nevow import inevow
from nevow import flat

from gavo.helpers import testhelpers

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import protocols
from gavo import svcs
from gavo import utils
from gavo.imp import formal
from gavo.imp.formal import iformal
from gavo.protocols import scs
from gavo.svcs import renderers
from gavo.web import formrender
from gavo.web import vodal

import tresc
import trialhelpers


MS = base.makeStruct


class ErrorMsgTest(testhelpers.VerboseTest):
	def testMissingQueriedTable(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="test">\\n\\...],'
			' (2, 22): You must set queriedTable on dbCore elements',
			base.parseFromString,
			(rscdesc.RD,
			"""<resource schema="test">
				<dbCore id="foo"/>
			</resource>"""))


class GetURLTest(testhelpers.VerboseTest):
	def testAbsolute(self):
		self.assertEqual(
			testhelpers.getTestRD("cores").getById("cstest"
				).getURL("form"),
			"http://localhost:8080/data/cores/cstest/form")

	def testRelative(self):
		self.assertEqual(
			testhelpers.getTestRD("cores").getById("cstest"
				).getURL("form", absolute=False),
			"/data/cores/cstest/form")

	def testWithParam(self):
		self.assertEqual(
			testhelpers.getTestRD("cores").getById("cstest"
				).getURL("form", arg1="10%", arg2="/&!;="),
			'http://localhost:8080/data/cores/cstest/form?arg1=10%25&'
			'arg2=%2F%26%21%3B%3D')


class InputDDTest(testhelpers.VerboseTest):
	def _assertPartialDict(self, partialExpectation, result):
		"""checks that all key/value pairs in partialExpectation are present in
		result.
		"""
		for key, value in partialExpectation.iteritems():
			self.assertEqual(value, result[key])

	def _getDDForInputKey(self, **keyPars):
		return MS(svcs.InputDescriptor, 
			grammar=MS(svcs.ContextGrammar, inputKeys=[
				MS(svcs.InputKey, name="x", **keyPars)]))
				
	def _getTableForInputKey(self, source, **keyPars):
		return rsc.makeData(
			self._getDDForInputKey(**keyPars),
			forceSource=source).getPrimaryTable()

	def testTypedIntSet(self):
		t = self._getTableForInputKey({"x": ["22", "24"]},
			type="integer")
		self._assertPartialDict({"x": 22}, t.getParamDict())
		self.assertEqual(len(t.rows), 0)

	def testTypedIntVal(self):
		t = self._getTableForInputKey({"x": "22"},
			type="integer")
		self._assertPartialDict({"x": 22}, t.getParamDict())

	def testTypedSingle(self):
		t = self._getTableForInputKey({"x": ["-22"]},
				type="real", multiplicity="single")
		self._assertPartialDict({"x": -22}, t.getParamDict())

	def testBadLiteralRejected(self):
		self.assertRaises(base.ValidationError,
			self._getTableForInputKey,
			{"x": "gogger"}, type="integer")
	
	def testMultipleRejected(self):
		self.assertRaises(base.ValidationError,
			self._getTableForInputKey,
			{"x": ["-22", "30"]},
			type="real", multiplicity="forced-single")

	def testRows(self):
		dd = MS(svcs.InputDescriptor, 
			grammar=MS(svcs.ContextGrammar, rowKey="x",
				inputKeys=[
					MS(svcs.InputKey, name="x", type="integer", multiplicity="multiple"),
					MS(svcs.InputKey, name="y", type="text", content_="uhu"),
					MS(svcs.InputKey, name="z", type="integer")]))
		res = rsc.makeData(dd, 
			forceSource={"x": range(4), "y": None, "z": range(2)})
		self.assertEqual(res.getPrimaryTable().rows, [
			{'x': 0, 'y': u'uhu', 'z': 0},
			{'x': 1, 'y': u'uhu', 'z': 1},
			{'x': 2, 'y': u'uhu', 'z': 0},
			{'x': 3, 'y': u'uhu', 'z': 1}])

	def testMissingRequired(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field x: Value is required but was not provided",
			self._getTableForInputKey,
			({},),
			type="real", required="True")

	def testMissingStringRequired(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field x: Value is required but was not provided",
			self._getTableForInputKey,
			({"x": ""},),
			type="text", required="True")


# XXX TODO test some other funky properties of rows generating ContextGrammars.
# XXX TODO test singleton inputs into ContextGrammar

class _AutoBuiltParameters(testhelpers.TestResource):
# XXX TODO: more types: unicode, spoint...
	def make(self, ignored):
		core = testhelpers.getTestRD("cores").getById("typescore")
		inputDD = svcs.makeAutoInputDD(core)
		return rsc.makeData(inputDD, forceSource={
				"anint": ["22"],
				"afloat": ["-2e-7"],
				"adouble": ["-2"],
				"atext": ["foo", "bar"],
				"adate": ["2013-05-04", "2005-02-02"]
			}).getPrimaryTable().getParamDict()


class AutoInputDDTest(testhelpers.VerboseTest):
	resources = [("resPars", _AutoBuiltParameters())]

	def testInteger(self):
		self.assertEqual(self.resPars["anint"], 22)

	def testFloat(self):
		self.assertEqual(self.resPars["afloat"], -2e-7)

	def testDouble(self):
		self.assertEqual(self.resPars["adouble"], -2)

	def testText(self):
		self.assertEqual(self.resPars["atext"], "foo")

	def testDate(self):
		self.assertEqual(self.resPars["adate"], datetime.date(2013, 5, 4))


class InputTableGenTest(testhelpers.VerboseTest):
	def testDefaulting(self):
		service = testhelpers.getTestRD("cores").getById("cstest")
		it = service._makeInputTableFor(renderers.getRenderer("form"), 
			svcs.PreparsedInput({
				"hscs_pos": "Aldebaran", "hscs_SR": "0.25"}))
		self.assertEqual(it.getParamDict(), {
			'rV': '-100 .. 100', 'hscs_sr': 0.25, 'mag': None, 
			'hscs_pos': 'Aldebaran'})

	def testInvalidLiteral(self):
		service = testhelpers.getTestRD("cores").getById("cstest")
		try:
			it = service._makeInputTableFor(renderers.getRenderer("form"), {
				"hscs_pos": "Aldebaran", "hscs_sr": "a23"})
		except base.ValidationError, ex:
			self.assertEqual(ex.colName, "hscs_sr")
			return
		raise AssertionError("ValidationError not raised")

	def testEnumeratedNoDefault(self):
		service = testhelpers.getTestRD("cores").getById("enums")
		it = service._makeInputTableFor(renderers.getRenderer("form"), {})
		self.assertEqual(it.getParamDict(), {'a': None, 'b': None,
			'c':[1]})

	def testCaseFolding(self):
		service = testhelpers.getTestRD("cores").getById("enums")
		it = service._makeInputTableFor(renderers.getRenderer("form"), {"B": 2})
		self.assertEqual(it.getParamDict(), {'a': None, 'b': [2],
			'c':[1]})

	def testEnumeratedBadValues(self):
		service = testhelpers.getTestRD("cores").getById("enums")
		self.assertRaisesWithMsg(base.ValidationError,
			"Field b: '3' is not a valid value for b",
			service._makeInputTableFor,
			(renderers.getRenderer("form"), {'b':"3"}))


class PlainDBServiceTest(testhelpers.VerboseTest):
	"""tests for working db-based services, having defaults for everything.
	"""
	resources = [("prodtbl", tresc.prodtestTable)]
	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.rd = testhelpers.getTestRD()

	def testEmptyQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.run("get", {})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_(set(["gabriel", "michael"])<=namesFound)

	def testOneParameterQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.run("form", {"accref": ["~ *a.imp"]})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" in namesFound)
		self.assert_("michael" not in namesFound)

	def testTwoParametersQuery(self):
		svc = self.rd.getById("basicprod")
		res = svc.run("form", {"accref": "~ *a.imp", "embargo": "< 2000-03-03"})
		namesFound = set(r["object"] for r in res.original.getPrimaryTable().rows)
		self.assert_("gabriel" not in namesFound)
		self.assert_("michael" not in namesFound)


class _DatafieldsTestMixin(object):
	def assertDatafields(self, columns, names):
		self.assertEqual(len(columns), len(names), "Wrong number of columns"
			" returned, expected %d, got %s"%(len(names), len(columns)))
		for c, n in zip(columns, names):
			self.assertEqual(c.name, n, "Got column %s instead of %s"%(c.name, n))


class VerblevelBasicTest(testhelpers.VerboseTest, _DatafieldsTestMixin):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inData, expected = sample
		svc = testhelpers.getTestRD("cores.rd").getById("basiccat")
		resTable = svc.run("form", inData).original.getPrimaryTable()
		self.assertDatafields(resTable.tableDef.columns, expected)

	samples = [
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "verbosity": "2", "_FORMAT": "VOTable"},
			["a"]),
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "VERB": "1", "_FORMAT": "VOTable"},
			["a", "b"]),
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "2", "_FORMAT": "VOTable"},
			["a", "b", "c", "d"]),
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "3", "_FORMAT": "VOTable"},
				["a", "b", "c", "d", "e"]),
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_VERB": "HTML", "_FORMAT": "VOTable"},
			["a"]),
		({"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_FORMAT": "VOTable"},
			["a", "b", "c", "d"])]


class ComputedServiceTest(testhelpers.VerboseTest, _DatafieldsTestMixin):
	"""tests a simple service with a computed core.
	"""
	def setUp(self):
		self.rd = testhelpers.getTestRD("cores.rd")

	def testStraightthrough(self):
		svc = self.rd.getById("basiccat")
		res = svc.run("form", {"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01"})
		self.assertEqual(res.original.getPrimaryTable().rows, [
			{'a': u'xy', 'c': 4, 'b': 3, 
				'e': datetime.datetime(2005, 10, 12, 12, 23, 1), 'd': 5}])

	def testMappedOutput(self):
		svc = self.rd.getById("convcat")
		res = svc.run("form", {"a": "xy", "b": "3", "c": "4", "d": "5",
			"e": ["2005-10-12T12:23:01"]})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "d"])
		self.assertEqual(res.original.getPrimaryTable().
			tableDef.columns[0].verbLevel, 15)
		self.assertEqual(res.original.getPrimaryTable().rows[0]['d'], 5000.)

	def testAdditionalFields(self):
		svc = self.rd.getById("convcat")
		res = svc.run("form", {"a": ["xy"], "b": "3", "c": "4", "d": "5",
			"e": "2005-10-12T12:23:01", "_ADDITEM":["c", "e"]})
		self.assertDatafields(res.original.getPrimaryTable().tableDef.columns, 
			["a", "b", "d", "c", "e"])

	def testTableSet(self):
		svc = self.rd.getById("basiccat")
		res = svc.getTableSet()
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0].columns[0].name, "a")


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
	# tests for type/widget inference with input keys.
	def _getKeyProps(self, src):
		cd = base.parseFromString(svcs.CondDesc, src
			).adaptForRenderer(svcs.getRenderer("form"))
		ik = cd.inputKeys[0]
		ftype = formrender._getFormalType(ik)
		fwid = formrender._getWidgetFactory(ik)
		ctx = context.WovenContext()
		rendered = fwid(ftype).render(ctx, "foo", {}, None)
		return ftype, fwid, rendered

	def _runWithData(self, fwid, ftype, data):
		ctx = trialhelpers.getRequestContext("/")
		ctx.remember({}, iformal.IFormData)
		widget = fwid(ftype)
		return widget.processInput(ctx, "x", {}, widget.default)

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

	def testUnicodeCondDesc(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="foo" type="unicode"/></condDesc>')
		self.assertEqual(ftype.__class__.__name__, "String")

	def testNotRequiredCondDesc(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="foo" type="text" required="True"/></condDesc>')
		self.assertEqual(ftype.required, False)

	def testBuildFrom(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc buildFrom="data/testdata#data.afloat"/>')
		self.failUnless(isinstance(ftype, formal.types.String))
		self.assertEqual(rendered.children[2].children[0].children[0],
			"[?num. expr.]")

	def testBuildFromEnumerated(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc buildFrom="data/testdata#data.atext"/>')
		self.assertEqual(rendered.data[0].content_, "bla")

	def testWithOriginalAndFT(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey original="data/testdata#data.afloat"'
				' type="integer"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.Integer))

	def testWithEnumeratedOriginal(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey original="data/testdata#nork.cho"/></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.String))
		opts = list(rendered.children[0](None, rendered.data))
		self.assertEqual(opts[0][0].attributes["type"], "checkbox")

	def testWithEnumeratedDefaultedRequired(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey name="m" type="text" required="True"'
			' multiplicity="forced-single"><values default="i">'
			' <option>i</option><option>u</option></values></inputKey></condDesc>')
		self.failUnless(isinstance(ftype, formal.types.String))
		opts = [c.children[0].attributes["value"]
			for c in rendered.children[0](None, rendered.data)]
		self.assertEqual(opts, ['i', 'u'])
	
	def testManualWF(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc><inputKey type="text" name="x" widgetFactory="'
				'widgetFactory(ScalingTextArea, rows=15)"/></condDesc>')
		self.assertEqual(rendered.attributes["rows"], 15)

	def testSpointWidget(self):
		cd = base.parseFromString(svcs.CondDesc, '<condDesc buildFrom='
			'"data/ssatest#hcdtest.ssa_location"/>'
			).adaptForRenderer(svcs.getRenderer("form"))
		outPars = {}
		self.assertEqual(
			cd.asSQL({"pos_ssa_location": "23,-43", "sr_ssa_location": "3"},
				outPars, svcs.emptyQueryMeta),
			"ssa_location <-> %(pos0)s < %(sr0)s")
		self.assertAlmostEqual(outPars["sr0"], 3/60.*utils.DEG)
		self.assertEqual(outPars["pos0"].asSTCS("Junk"),
			'Position Junk 23. -43.')

	def testPlaceholder(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc buildFrom="data/test#valSpec.numeric"/>')
		self.assertEqual(rendered.children[0].attributes["placeholder"],
			"10.0 .. 15.0")
	
	def testPlaceholderUnitconv(self):
		ftype, fwid, rendered = self._getKeyProps(
			'<condDesc buildFrom="data/test#adql.rV"/>')
		self.assertEqual(rendered.children[0].attributes["placeholder"],
			"-20.0 .. 200.0")


class InputFieldSelectionTest(testhelpers.VerboseTest):
	# Tests for renderer-dependent selection and adaptation of db core 
	# input fields.
	def testForm(self):
		service = testhelpers.getTestRD("cores").getById("cstest")
		self.assertEqual(
			[(k.name, k.type) for k in service.getInputKeysFor("form")],
			[("hscs_pos", "text"), ("hscs_sr", "real"), ("mag", "vexpr-float"),
				('rV', 'vexpr-float')])

	def testSCS(self):
		service = testhelpers.getTestRD("cores").getById("cstest")
		self.assertEqual(
			[(k.name, k.type) for k in service.getInputKeysFor("scs.xml")],
			 [(u'RA', u'double precision'), (u'DEC', u'double precision'), 
			 	(u'SR', 'real'), (u'RESPONSEFORMAT', u'text'), 
			 	(u'MAXREC', u'integer'), (u'VERB', u'integer'), 
			 	(u'mag', 'pql-float'), (u'rV', u'vexpr-float')])

	def testSSAPPrune(self):
		svc = base.caches.getRD("data/ssatest").getById("d")
		self.failIf("FORMAT" in
			[k.name for k in svc.getInputKeysFor("ssap.xml")])

	def testAPIKeysVanish(self):
		svc = base.parseFromString(svcs.Service, """<service id="x"><nullCore/>
			<FEED source="//pql#DALIPars"/></service>""")
		self.assertEqual([],
			[k.name for k in svc.getInputKeysFor("form")])
		self.assertEqual(["RESPONSEFORMAT", "MAXREC", "VERB"],
			[k.name for k in svc.getInputKeysFor("api")])


class _DALIParameters(testhelpers.TestResource):
	def make(self, deps):
		svc = base.parseFromString(svcs.Service, """<service id="x">
			<dbCore queriedTable="data/test#typesTable">
				<condDesc buildFrom="anint"/>
				<condDesc buildFrom="afloat"/>
				<condDesc buildFrom="adouble"/>
				<condDesc buildFrom="atext"/>
				<condDesc>
					<inputKey name="enum" type="smallint" multiplicity="single">
						<values>
							<option>1</option>
							<option>2</option>
						</values>
					</inputKey>
				</condDesc>
				<condDesc>
					<inputKey name="single"/>
				</condDesc>
				<condDesc buildFrom="data/test#abcd.e"/>
				<condDesc>
					<inputKey name="arr">
						<property key="adaptToRenderer">True</property>
					</inputKey>
				</condDesc>
			</dbCore>
			<FEED source="//pql#DALIPars"/></service>""")
		keys = dict((k.name, k) for k in svc.getInputKeysFor("api"))
		return keys


class DALIAdaptationTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [('pars', _DALIParameters())]

	def _runTest(self, sample):
		parName, attrName, expectedValue = sample
		self.assertEqual(getattr(self.pars[parName], attrName), expectedValue)
	
	samples = [
		('enum', 'xtype', None),
		('enum', 'type', 'smallint'),
		('enum', 'multiplicity', 'single'),
		('MAXREC', 'type', 'integer'),
		('MAXREC', 'xtype', None),
# 5
		('anint', 'xtype', 'interval'),
		('anint', 'type', 'integer[2]'),
		('afloat', 'xtype', 'interval'),
		('afloat', 'type', 'real[2]'),
		('single', 'type', 'real'),
# 10
		('arr', 'type', 'real[2]'),
		('arr', 'xtype', 'interval'),
		('e', 'type', 'double precision[2]'),
		('e', 'unit', 'd'),
		('e', 'xtype', 'interval'),
# 15
		('atext', 'type', 'unicode'),
	]


class GroupingTest(testhelpers.VerboseTest):
	def _renderForm(self, svc):
		from gavo.imp.formal.form import FormRenderer
		ctx = trialhelpers.getRequestContext("/")
		ctx.remember({}, iformal.IFormData)
		ctx.remember({}, inevow.IData)

		rend = formrender.Form(ctx, svc)
		form = rend.form_genForm(ctx)
		ctx.remember(form, iformal.IForm)
		ctx.remember(rend, inevow.IRendererFactory)
		form.name = "foo"
		return flat.flatten(FormRenderer(form), ctx)

	def testExplicitGroup(self):
		rendered = self._renderForm(
			testhelpers.getTestRD("cores").getById("grouptest"))
		#testhelpers.printFormattedXML(rendered)
		self.failUnless('<fieldset class="group localstuff"' in rendered)
		self.failUnless('<legend>Magic</legend>' in rendered)
		self.failUnless('<div class="description">Some magic parameters we took'
			in rendered)

	def testImplicitGroup(self):
		# automatic grouping of condDescs with group
		rendered = self._renderForm(
			testhelpers.getTestRD("cores").getById("impgrouptest"))
		#testhelpers.printFormattedXML(rendered)
		self.failUnless('<div class="multiinputs" id="multigroup-phys">' 
			in rendered)
		self.failUnless('<label for="multigroup-phys">Wonz' in rendered)
		renderedInput = re.search('<input[^>]*name="rV"[^>]*>', rendered).group(0)
		self.failUnless('class="inmulti"' in renderedInput)


class OutputTableTest(testhelpers.VerboseTest):
	resources = [("adqltable", tresc.csTestTable)]

	def testResolution(self):
		base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">
			<column name="bar"/></table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable autoCols="bar"/>
			</service></resource>""")

	def testNamePath(self):
		base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo"><column name="bar"/></table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable><outputField original="bar"/></outputTable>
			</service></resource>""")

	def testVerbLevel(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">
			<column name="bar" verbLevel="7"/>
			<column name="baz" verbLevel="8"/></table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable verbLevel="7"/>
			</service></resource>""")
		cols = rd.services[0].outputTable.columns
		self.assertEqual(len(cols), 1)
		self.assertEqual(cols[0].name, "bar")

	def testParams(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">
			<param name="bar" verbLevel="7"/>
			<param name="baz" verbLevel="8"/>
			<param name="quux" verbLevel="9"/>
			</table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable verbLevel="7" autoCols="quux"/>
			</service></resource>""")
		pars = rd.services[0].outputTable.params
		self.assertEqual(len(pars), 2)
		self.assertEqual(pars[0].name, "quux")
		self.assertEqual(pars[1].name, "bar")

	def testSTCPreserved(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">
			<stc>Position ECLIPTIC Epoch J2200.0 "bar" "bar"</stc>
			<column name="bar"/></table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable autoCols="bar"/>
			</service></resource>""")
		self.assertEqual("ECLIPTIC",
			rd.services[0].outputTable.columns[0].stc.place.frame.refFrame)

	def testSTCPreservedOriginal(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">
			<stc>Position ECLIPTIC Epoch J2200.0 "bar" "bar"</stc>
			<column name="bar"/></table>
			<service id="quux"><dbCore queriedTable="foo"/>
			<outputTable><outputField original="bar"/></outputTable>
			</service></resource>""")
		self.assertEqual("ECLIPTIC",
			rd.services[0].outputTable.columns[0].stc.place.frame.refFrame)

	def testAutoColsSingleWildcard(self):
		svc = base.parseFromString(svcs.Service,
			"""<service id="quux" core="data/cores#cscore">
				<outputTable autoCols="*"/>
			</service>""")
		cols = svc.getCurOutputFields()
		self.assertEqual([c.name for c in cols],
			["alpha", "delta", "mag", "rV", "tinyflag"])

	def testAutoColsMultiWildcard(self):
		svc = base.parseFromString(svcs.Service,
			"""<service id="quux" core="data/cores#cscore">
				<outputTable autoCols="*a,*g"/>
			</service>""")
		cols = svc.getCurOutputFields()
		self.assertEqual([c.name for c in cols],
			["alpha", "delta", "mag", "tinyflag"])

	def testCustomTableSelection(self):
		svc = base.parseFromString(svcs.Service,
			"""<service id="quux" core="data/cores#cscore">
				<outputTable verbLevel="15">
					<outputField original="mag" unit="mmag" select="mag*1000"/>
				</outputTable>
			</service>""")
		res = svc.run("form", {"verbosity": "25", "_FORMAT": "VOTable"}
			).original.getPrimaryTable().tableDef
		self.assertEqual(res.getColumnByName("mag").unit, "mmag")
		self.assertEqual(res.getColumnByName("rV").unit, "km/s")
		self.assertEqual(len(res.columns), 4)


class TableSetTest(testhelpers.VerboseTest):
	def testFromCore(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo"><column name="bar"/>
			</table>
			<service id="quux"><dbCore queriedTable="foo"/></service></resource>""")
		cols = rd.getById("quux").getTableSet()[0].columns
		self.assertEqual(len(cols), 1)
		self.assertEqual(cols[0].name, "bar")

	def testOutputTable(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test">
			<service id="quux"><nullCore/><outputTable><outputField
			name="knotz"/></outputTable></service></resource>""")
		cols = rd.getById("quux").getTableSet()[0].columns
		self.assertEqual(len(cols), 1)
		self.assertEqual(cols[0].name, "knotz")

	def testTAPTableset(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test">
			<service id="quux" allowed="tap"><nullCore/></service></resource>""")
		ts = rd.getById("quux").getTableSet()
		self.failUnless("tap_schema.tables" in [t.getQName() for t in ts])


class _ConecatTable(tresc.RDDataResource):
	rdName = "data/cores"
	dataId = "import_conecat"


class ConeSearchTest(testhelpers.VerboseTest):
	resources = [("cstable", _ConecatTable()),
		("fs", tresc.fakedSimbad)]

	def testRadiusAddedSCS(self):
		svc = base.resolveCrossId("data/cores#scs")
		res = svc.run("scs.xml", {"RA": 1, "DEC": "2", "SR": 3}
			).original.getPrimaryTable()
		self.assertAlmostEqual(res.rows[0]["_r"], 0.5589304685425)
		col = res.tableDef.getColumnByName("_r")
		self.assertEqual(col.unit, "deg")

	def testRadiusAddedForm(self):
		svc = base.resolveCrossId("data/cores#scs")
		res = svc.run("form", {"hscs_pos": "1, 2", "hscs_sr": 3*60}
			).original.getPrimaryTable()
		self.assertAlmostEqual(res.rows[0]["_r"], 0.5589304685425)

	def testRadiusAddedFormObjectres(self):
		svc = base.resolveCrossId("data/cores#scs")
		res = svc.run("form", {"hscs_pos": "Aldebaran", "hscs_sr": 180*60}
			).original.getPrimaryTable()
		self.assertAlmostEqual(res.rows[0]["_r"], 67.9075866114036)

	def testNoRadiusWithoutPos(self):
		svc = base.resolveCrossId("data/cores#scs")
		res = svc.run("form", {"id": "0"}).original.getPrimaryTable()
		self.assertTrue(res.rows[0]["_r"] is None)


class PythonCoreTest(testhelpers.VerboseTest):
	def testBasic(self):
		svc = base.resolveCrossId("data/cores#pc")
		res = svc.run("form", {"opre": "1", "opim": 1, "powers": [2,3,4]}
			).original.getPrimaryTable()
		self.assertEqual(res.rows[0]["re"], 0)
		self.assertEqual(res.rows[1]["im"], 2.0)
		self.assertAlmostEqual(res.rows[2]["log"], 1.3862943611198906)
		self.assertEqual(len(res.rows), 3)

	def testDefaulting(self):
		svc = base.resolveCrossId("data/cores#pc")
		res = svc.run("form", {"opre": "1", "opim": 1}
			).original.getPrimaryTable()
		self.assertEqual(len(res), 3)

	def testMissing(self):
		svc = base.resolveCrossId("data/cores#pc")
		self.assertRaisesWithMsg(base.ValidationError,
			"Field opre: Value is required but was not provided",
			svc.run,
			("form", {"opim": 1, "powers": [2,3,4]}))


class HumanCoordParseTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [("fs", tresc.fakedSimbad)]

	def _runTest(self, sample):
		literal, parsed = sample
		self.assertEqual(scs.parseHumanSpoint(literal), parsed)
	
	samples = [
		("23.5, -21.75", (23.5, -21.75)),
		("23.5 -21.75", (23.5, -21.75)),
		("23 30, 11 15 30.6", (352.5, 11.2585)),
		("23:30:45, 11:15:30.6", (352.6875, 11.2585)),
		("Aldebaran",  (68.9375, 16.46875)),]

	def testException(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Unidentified Field: $&& zefixx is neither a RA,DEC pair nor"
			" a simbad resolvable object.",
			scs.parseHumanSpoint,
			("$&& zefixx",))




if __name__=="__main__":
	testhelpers.main(ComputedServiceTest)
