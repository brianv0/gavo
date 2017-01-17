"""
Tests for resource descriptor handling
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cStringIO
import os
import threading
import time
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.base import meta
from gavo.protocols import tap
from gavo.rscdef import regtest
from gavo.rscdef import tabledef

import tresc


class CanonicalizeTest(testhelpers.VerboseTest):
# tests for mapping paths and stuff to canonical ids.
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	inp = base.getConfig("inputsDir").rstrip("/")+"/"

	def _runTest(self, sample):
		src, expected = sample
		self.assertEqual(
			rscdesc.canonicalizeRDId(src),
			expected)
	
	samples = [
		("/somewhere/bad", "/somewhere/bad"),
		("/somewhere/bad.crazy", "/somewhere/bad.crazy"),
		("/somewhere/bad.rd", "/somewhere/bad"),
		("//tap", "__system__/tap"),
		("//tap.rd", "__system__/tap"),
#5
		(inp+"/where", "where"),
		(inp+"/where/q", "where/q"),
		(inp+"/where/q.rd", "where/q"),
		("/resources/inputs/where/q.rd", "where/q"),
		("/resources/inputs/where/q", "where/q"),]
	

class InputStreamTest(testhelpers.VerboseTest):
# test the location of input streams.  This assumes testhelpers has set
# gavo_inputs to <test_dir>/data

	def _assertSourceName(self, rdId, expectedSuffix):
		fName, fobj = rscdesc.getRDInputStream(rscdesc.canonicalizeRDId(rdId))
		self.failUnless(fName.endswith(expectedSuffix), 
			"%r does not end with %r"%(fName, expectedSuffix))
		fobj.close()

	def testInternalResource(self):
		self._assertSourceName("//users", "/resources/inputs/__system__/users.rd")

	def testUserResource(self):
		self._assertSourceName("data/test", "data/test.rd")
	
	def testUserOverriding(self):
		inpDir = base.getConfig("inputsDir")
		dirName = os.path.join(inpDir, "__system__")
		try:
			os.mkdir(dirName)
		except os.error: # don't worry if someone left the dir
			pass
		try:
			testName = os.path.join(dirName, "users")
			open(testName, "w").close()
			try:
				self._assertSourceName("//users", testName)
			finally:
				os.unlink(testName)
		finally:
			os.rmdir(dirName)


class MetaTest(unittest.TestCase):
	"""Test for correct interpretation of meta information.
	"""
	def setUp(self):
		# get a fresh copy of the RD since we're modifying the thing
		self.rd = testhelpers.getTestRD()
		meta.configMeta.addMeta("test.fromConfig", "from Config")
	
	def testMetaAttachment(self):
		"""tests for proper propagation of meta information.
		"""
		recDef = self.rd.getTableDefById("noname")
		self.assert_(str(recDef.getMeta("test.inRec")), "from Rec")
		self.assert_(str(recDef.getMeta("test.inRd")), "from Rd")
		self.assert_(str(recDef.getMeta("test.fromConfig")), "from Config")
		self.assertEqual(recDef.getMeta("test.doesNotExist"), None)

	def testComplexMeta(self):
		"""tests for handling of complex meta items.
		"""
		data = self.rd.getById("metatest")
		data.addMeta("testStatus", base.META_CLASSES_FOR_KEYS["info"](
			"I'm so well I could cry",
			infoValue="OK"))
		self.assert_(isinstance(data.getMeta("testStatus").children[0], 
			meta.InfoItem))
		self.assertEqual(data.getMeta("testStatus").children[0].infoValue, "OK")
		self.assertEqual(str(data.getMeta("testStatus")),
			"I'm so well I could cry")


class ValidationTest(testhelpers.VerboseTest):
	def setUp(self):
		self.rd = testhelpers.getTestRD()

	def testOptional(self):
		"""tests for correct validation of non-optional values.
		"""
		recDef = self.rd.getTableDefById("valSpec")
		rec = {}
		try:
			recDef.validateRow(rec)
		except base.ValidationError, ex:
			self.assertEqual(ex.colName, "numeric")
		rec["enum"] = "abysimal"
		self.assertRaises(base.ValidationError, recDef.validateRow,
			rec)
		rec["numeric"] = 14
		self.assert_(recDef.validateRow(rec)==None)
	
	def testBadSchema(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="a;drop ta...], (1, 37):'
			' DaCHS schema attributes must be valid python identifiers',
			base.parseFromString,
			(rscdesc.RD, '<resource schema="a;drop table foo"/>'))


class MacroTest(unittest.TestCase):
	"""Tests for macro evaluation within RDs.
	"""
	def testDefinedMacrosEasy(self):
		rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="test"><macDef name="foo">abc</macDef></resource>')
		self.assertEqual(rd.expand("foo is \\foo."), "foo is abc.")

	def testDefinedMacrosWhitespace(self):
		rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="test"><macDef name="foo"> a\nbc  </macDef></resource>')
		self.assertEqual(rd.expand("foo is \\foo."), "foo is  a\nbc  .")


class ViewTest(testhelpers.VerboseTest):
	"""tests for interpretation of view elements.
	"""
	def testBadRefRaises(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<simpleView><fieldRef table...], (1, 67):'
			" No field 'noexist' in table test.prodtest", 
			base.parseFromString, (tabledef.SimpleView, '<simpleView>'
			'<fieldRef table="data/test#prodtest" column="noexist"/></simpleView>'))

	def testTableDefCreation(self):
		rd = base.parseFromString(rscdesc.RD,
			'<resource schema="test2">'
			'<simpleView id="vv">'
			'<columnRef table="data/test#prodtest" column="alpha"/>'
			'<columnRef table="data/test#prodtest" column="delta"/>'
			'<columnRef table="data/test#prodtest" column="object"/>'
			'<columnRef table="data/test#adql" column="mag"/>'
			'</simpleView></resource>')
		self.assertEqual(len(rd.tables), 1)
		td = rd.tables[0]
		self.failUnless(isinstance(td, rscdef.TableDef))
		self.assertEqual(td.viewStatement, 'CREATE VIEW test2.vv AS'
			' (SELECT test.prodtest.alpha,test.prodtest.delta,test.prodtest.'
			'object,test.adql.mag FROM test.prodtest NATURAL JOIN test.adql)')
		self.assertEqual(td.onDisk, True)
		self.assertEqual(rd.getById("vv"), td)


class TAP_SchemaTest(testhelpers.VerboseTest):
	"""test for working tap_schema export.

	This is another mega test that runs a bunch of functions in sequence.
	We really should have a place to put those.
	"""
	resources = [("conn", tresc.dbConnection)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.rd = testhelpers.getTestRD()
		self.rd.getById("adqltable").foreignKeys.append(
			base.parseFromString(tabledef.ForeignKey, 
				'<foreignKey inTable="data/test#adql" source="foo" dest="rV"/>'))

	def tearDown(self):
		tap.unpublishFromTAP(self.rd, self.conn)
		self.rd.getById("adqltable").foreignKeys = []
		testhelpers.VerboseTest.tearDown(self)

	def _checkPublished(self):
		q = base.UnmanagedQuerier(connection=self.conn)
		tables = set(r[0] for r in
			(q.query("select table_name from TAP_SCHEMA.tables where sourcerd"
			" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(tables, set([
			'test.adqltable', 'test.adql', 'test.pgs_siaptable']))
		columns = set(r[0] for r in
			(q.query("select column_name from TAP_SCHEMA.columns where sourcerd"
			" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertTrue(
			set([u'alpha', u'rv', u'foo', u'mag', u'delta', u'tinyflag']
				).issubset(columns), "adql columns not in TAP_SCHEMA")
		fkeys = set(q.query("select from_table, target_table"
				" from TAP_SCHEMA.keys where sourcerd"
				" = %(rdid)s", {"rdid": self.rd.sourceId}))
		self.assertEqual(fkeys, 
			set([(u'test.adqltable', u'test.adql')]))
		fkcols = set(r for r in
			(q.query("select from_column, target_column"
				" from TAP_SCHEMA.key_columns where sourcerd"
				" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(fkcols, set([(u'foo', u'rv')]))

	def _checkUnpublished(self):
		q = base.UnmanagedQuerier(connection=self.conn)
		tables = set(r[0] for r in
			(q.query("select table_name from TAP_SCHEMA.tables where sourcerd"
			" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(tables, set())
		columns = set(r[0] for r in
			(q.query("select column_name from TAP_SCHEMA.columns where sourcerd"
			" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(columns, set())
		fkeys = set(q.query("select from_table, target_table"
				" from TAP_SCHEMA.keys where sourcerd"
				" = %(rdid)s", {"rdid": self.rd.sourceId}))
		self.assertEqual(fkeys, set())
		fkcols = set(r for r in
			(q.query("select from_column, target_column"
				" from TAP_SCHEMA.key_columns where sourcerd"
				" = %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(fkcols, set())

	def testMega(self):
		tap.publishToTAP(self.rd, self.conn)
		self._checkPublished()
		tap.unpublishFromTAP(self.rd, self.conn)
		self._checkUnpublished()


class RestrictionTest(testhelpers.VerboseTest):
	"""Tests for rejection of constructs disallowed in restricted RDs.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		context = rscdesc.RDParseContext(restricted=True)
		context.srcPath = os.getcwd()
		self.assertRaises(base.RestrictedElement, base.parseFromString,
			rscdesc.RD, '<resource schema="testing">'
				'<table id="test"><column name="x"/></table>'
				'%s</resource>'%sample,
				context)
		
	samples = [
		'<procDef><code>pass</code></procDef>',
		'<dbCore queriedTable="test"><condDesc><phraseMaker/></condDesc></dbCore>',
		'<nullCore id="null"/><service core="null"><customRF name="foo"/>'
			'</service>',
		'<table id="test2"><column name="x"/><index columns="x">'
			'CREATE</index></table>',
		'<table id="test2"><column name="x" fixup="__+\'x\'"/></table>',
		'<data><embeddedGrammar><iterator/></embeddedGrammar></data>',
		'<data><reGrammar names="a,b" preFilter="rm -rf /"/></data>',
		'<data><directGrammar cBooster="res/kill.c"/></data>',
	]


class _RD1(tresc.FileResource):
	path = "inputs/rd1.rd"
	content = """<resource schema='test'>
			<table id="tmp"><column name="a"/></table>
			<data id="import">
				<dictlistGrammar/>
				<make table="tmp" rowmaker="rd2#rmk"/>
			</data>
		</resource>"""


class _RD2(tresc.FileResource):
	path = "inputs/rd2.rd"
	content = """<resource schema='test'>
			<rowmaker id="rmk" idmaps="*">
				<apply name="foo">
					<code>
						@a = ord(@a)*0.5
					</code>
				</apply>
			</rowmaker>
		</resource>"""


class RestrictionInheritingTest(testhelpers.VerboseTest):
	# tests making sure cross-RD references don't break out of restricted
	# mode
	resources = [("rd1", _RD1()), ("rd2", _RD2())]

	def testRestrictionRequired(self):
		rows = rsc.makeData(base.caches.getRD("rd1"
			).getById("import"),
			forceSource=[{'a': 'x'}]).getPrimaryTable().rows
		self.assertEqual(rows, [{'a': 60.0}])

	def testRestrictionEnforced(self):
		self.assertRaises(base.RestrictedElement,
			base.caches.getRD,
			"rd1", restricted=True)


class _TempRDFile(tresc.FileResource):
	path = "inputs/temp.rd"
	content = "<resource schema='temptemp'/>"


class _UnloadableRDFile(tresc.FileResource):
	# this is handcrafted for specific failure in parallelRDIsInvalidated
	path = "inputs/unloadable.rd"
	content = """<resource schema='temptemp'>
			<LOOP>
				<codeItems>
					from gavo import base
					base.OTHER_IS_WAITING = True
					while True:
						if hasattr(base, "I_AM_HERE"):
							raise base.ReportableError("All is good")
					yield {"foo": "a"}
				</codeItems>
				<events>
					<table id="\\foo"/>
				</events>
			</LOOP>
		</resource>"""


class _TempBadRDFile(tresc.FileResource):
	path = "inputs/tempbad.rd"
	content = "<resource schema='temptemp'>junk</resource>"


class CachesTest(testhelpers.VerboseTest):
	resources = [("tempRDFile", _TempRDFile()),
		("tempBadRDFile", _TempBadRDFile())]

	def testCacheWorks(self):
		rd1 = base.caches.getRD("//users")
		rd2 = base.caches.getRD("//users")
		self.failUnless(rd1 is rd2)

	def testCachesCleared(self):
		rd1 = base.caches.getRD("//users")
		rd1.getById("users").gobble = "funk"
		base.caches.clearForName(rd1.sourceId)
		rd2 = base.caches.getRD("//users")
		self.failIf(rd2 is rd1)
		self.failUnless(hasattr(rd1.getById("users"), "gobble"))
		self.failIf(hasattr(rd2.getById("users"), "gobble"))

	def testAliases(self):
		rd1 = base.caches.getRD("//users")
		rd1.getById("users").gobble = "funk"
		base.caches.clearForName("__system__/users")
		rd2 = base.caches.getRD("//users")
		rd3 = base.caches.getRD("__system__/users.rd")
		self.failIf(rd2 is rd1)
		self.failIf(rd1 is rd3)
		self.failUnless(hasattr(rd1.getById("users"), "gobble"))
		self.failIf(hasattr(rd2.getById("users"), "gobble"))

	def testDirty(self):
		origRD = base.caches.getRD("temp")
		sameRD = base.caches.getRD("temp")
		self.failUnless(origRD is sameRD)
		now = time.time()
		os.utime(self.tempRDFile, (now+1, now+1))
		otherRD = base.caches.getRD("temp")
		self.failIf(origRD is otherRD)

	def testExceptionsAreCached(self):
		try:
			rd = base.caches.getRD("tempbad")
		except base.StructureError, ex:
			ex1 = ex
		try:
			rd2 = base.caches.getRD("tempbad")
		except base.StructureError, ex:
			ex2 = ex
		self.failUnless(ex1 is ex2)

	def testBadRDsAreReloaded(self):
		base.caches.clearForName("tempbad")
		try:
			rd = base.caches.getRD("tempbad")
		except base.StructureError, ex:
			ex1 = ex
		os.utime(os.path.join(base.getConfig("inputsDir"), "tempbad.rd"), 
			(time.time()+1, time.time()+1))
		try:
			rd = base.caches.getRD("tempbad")
		except base.StructureError, ex:
			self.failIf(ex is ex1)
		else:
			self.fail("This should have raised?")

	def testClearOnRm(self):
		with testhelpers.testFile(os.path.join(
				base.getConfig("inputsDir"), "fugit.rd"),
				"<resource schema='look'/>") as rdName:
			rd = base.caches.getRD(rdName)
			self.assertEqual(rd.schema, "look")
		self.assertRaises(base.RDNotFound, base.caches.getRD, rdName)


class DependentsTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	def testRecreateAfter(self):
		q = base.UnmanagedQuerier(connection=self.conn)
		rd = testhelpers.getTestRD()
		t0 = rsc.TableForDef(rd.getById("pythonscript"), connection=self.conn,
			create=False)
		t0.drop()
		self.failIf(q.tableExists("test.pythonscript"))
		data = rsc.makeDependentsFor([rd.getById("recaftertest")],
			rsc.parseNonValidating, connection=self.conn)
		self.failUnless(q.tableExists("test.pythonscript"))
		self.conn.rollback()

	def testFailedDependencyNonFatal(self):
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data recreateAfter="data/test#foobarmatic"/>')

		msgs = []
		handler = lambda msg: msgs.append(msg)
		base.ui.subscribe("Warning", handler)
		try:
			rsc.makeDependentsFor([dd], 
				rsc.parseNonValidating, connection=self.conn)
		finally:
			base.ui.unsubscribe("Warning", handler)
		self.assertEqual(len(msgs), 1)
		self.assertEqual(msgs[0], "Ignoring dependent data/test#foobarmatic"
			" of None (Element with id u'foobarmatic' could not be located"
			" in RD data/test)")

	def testRecursiveDepedency(self):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
			<table id="made"/>
			<rowmaker id="add_fu">
				<apply>
					<code>
						targetTable.tableDef.rd.dataMade.append(vars["dn"])
					</code>
				</apply>
			</rowmaker>
			<data id="stuff0" recreateAfter="stuff1">
				<sources items="1"/>
				<embeddedGrammar id="g">
					<iterator>
						<code>
							yield {"dn": self.grammar.parent.id}
						</code>
					</iterator>
				</embeddedGrammar>
				<make table="made" rowmaker="add_fu"/>
			</data>
			<data original="stuff0" id="stuff1">
				<recreateAfter>stuff2</recreateAfter>
				<recreateAfter>stuff3</recreateAfter>
			</data>
			<data id="stuff2" original="stuff0"/>
			<data id="stuff3" original="stuff0"/>
			</resource>
			""")
		rd.dataMade = []
		data = rsc.makeDependentsFor([rd.getById("stuff0")],
			rsc.parseNonValidating, connection=self.conn)
		self.assertEqual(set(rd.dataMade), set(["stuff1", "stuff2", "stuff3"]))
	
	def testCyclicDependency(self):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
			<table id="made"/>
			<rowmaker id="add_fu">
				<apply>
					<code>
						targetTable.tableDef.rd.dataMade.append(vars["dn"])
					</code>
				</apply>
			</rowmaker>
			<data id="stuff0" recreateAfter="stuff1">
				<sources items="1"/>
				<embeddedGrammar id="g">
					<iterator>
						<code>
							yield {"dn": self.grammar.parent.id}
						</code>
					</iterator>
				</embeddedGrammar>
				<make table="made" rowmaker="add_fu"/>
			</data>
			<data original="stuff0" id="stuff1" dependents="stuff2"/>
			<data original="stuff0" id="stuff2" recreateAfter="stuff1"/>
			</resource>
			""")
		rd.dataMade = []
		self.assertRaisesWithMsg(base.ReportableError,
			"Could not sort dependent DDs topologically (use  --hints to learn more).",
			rsc.makeDependentsFor,
			([rd.getById("stuff0")], rsc.parseNonValidating, self.conn))

	def testSequencing(self):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
				<table id="made" onDisk="True" temporary="True"/>
				<STREAM id="make">
					<make table="made"><script type="preIndex" lang="python">
						table.tableDef.rd.dataMade.append("\\tag")
					</script></make>
				</STREAM>

				<data id="d1" recreateAfter="d3">
					<recreateAfter>d2</recreateAfter><recreateAfter>d4</recreateAfter>
					<FEED source="make" tag="1"/>
				</data>

				<data id="d2">
					<recreateAfter>d4</recreateAfter><recreateAfter>d3</recreateAfter>
					<FEED source="make" tag="2"/>
				</data>

				<data id="d3">
					<recreateAfter>d4</recreateAfter>
					<FEED source="make" tag="3"/>
				</data>

				<data id="d4">
					<recreateAfter>d5</recreateAfter>
					<FEED source="make" tag="4"/>
				</data>

				<data id="d5">
					<FEED source="make" tag="end"/>
				</data>
			</resource>""")

		rd.dataMade = []
		data = rsc.makeDependentsFor([rd.getById("d1")],
			rsc.parseNonValidating, connection=self.conn)
		self.assertEqual(rd.dataMade, ["2", "3", "4", "end"])


class ConcurrentRDTest(testhelpers.VerboseTest):
	resources = [("unloadableRDFile", _UnloadableRDFile())]

	def testInvalidation(self):
		rd = base.parseFromString(rscdesc.RD, '<resource schema="test"/>')
		rd.sourceId = "artificial"
		rd.invalidate()
		try:
			rd.sourceId
		except base.ReportableError, ex:
			self.assertEqual(str(ex), "Loading of artificial"
				" failed in another thread; this RD cannot be used here")
		else:
			self.fail("Invalidation of an RD didn't work")

	def testRacingClear(self):
		# this is a bit non-deterministic...
		base.caches.clearForName("__system__/services")
		def loadFromOne():
			rd = base.caches.getRD("__system__/services")
			self.failUnless(hasattr(rd, "serviceIndex"))

		t1 = threading.Thread(target=loadFromOne)
		t1.daemon = True
		t1.start()
		for retry in range(50):
			if "__system__/services" in rscdesc._currentlyParsing:
				break
			time.sleep(0.05)
		else:
			self.fail("getRD in thread does not load the services RD?")

		base.caches.clearForName("__system__/services")
		newRD = base.caches.getRD("__system__/services")
		self.failUnless(hasattr(newRD, "serviceIndex"))

	def testParallelRDIsInvalidated(self):
		base.caches.clearForName("unloadable")
		fromThreads = []
		def loadFromOne():
			try:
				fromThreads.append(base.caches.getRD("unloadable"))
			except Exception, ex:
				fromThreads.append(ex)
		t1 = threading.Thread(target=loadFromOne)
		t1.start()

		# Check the _UnloadableRDFile above: This will set base.OTHER_IS_WAITING
		# and the wait for base.I_AM_HERE to appear.  This will happen in
		# thread 1.  We here provide the trigger when we've started to
		# in another thread.
		t2 = threading.Thread(target=loadFromOne)
		t2.start()

		while not hasattr(base, "OTHER_IS_WAITING"):
			time.sleep(0.001)
		base.I_AM_HERE = True
		t1.join(0.2)
		t2.join(0.2)

		# now one of the results must be an exception, the other a
		# BrokenClass
		self.assertEqual(set(r.__class__.__name__ for r in fromThreads),
			frozenset(["BrokenClass", "ReportableError"]))
		


_RUNNERS_RESPONSES = {
	"http://localhost:8080/bar": (200, {}, 
		'<VOTABLE version="1.2" xmlns="http://www.ivoa.net/xml/VOTable/v1.2"'
		' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
		' xsi:schemaLocation="http://www.ivoa.net/xml/VOTable/v1.2 '
		'http://vo.ari.uni-heidelberg.de/docs/schemata/VOTable-1.2.xsd">'
		'<DESCRIPTION>The apparent places</DESCRIPTION><RESOURCE type="meta">'
		'<DESCRIPTION>give exact</DESCRIPTION></RESOURCE></VOTABLE>'),
	"ivo://ivoa.net/std/quack": (200, {}, ""),
	"http://localhost:8080/data/regtest/foo?testParam=10%25w%2Fo+tax": 
		(200, {}, "Hume and Kant singing in perfect harmony."),
	"http://localhost:8080/data/regtest/nork?urk=zoo&oo=1&oo=2":
		(200, {}, ""),
}


def _fakeRetrieveResource(self, serverURL, timeout=0, moreHeaders=""):
	"""A stand-in for the test runner's testOpener.
	"""
	self.httpURL = self.getValue(base.getConfig("web", "serverURL"))
	try:
		return _RUNNERS_RESPONSES[self.httpURL]
	except KeyError:
		return 404, {}, "Not found"


class _RunnersSample(testhelpers.TestResource):
	def make(self, dependents):
		self.originalRetrieve = regtest.DataURL.retrieveResource
		regtest.DataURL.retrieveResource = _fakeRetrieveResource
		rd = base.caches.getRD("data/regtest")
		return rd

	def clean(self, rsc):
		regtest.DataURL.retrieveResource = self.originalRetrieve


class _RegtestTest(testhelpers.VerboseTest):
	resources = [("rd", _RunnersSample())]

	def assertContains(self, needle, haystack):
		if needle not in haystack:
			raise AssertionError("%s not in %s"%(needle, haystack))


class MiscRegtestTest(_RegtestTest):
	def testBasic(self):
		runner = regtest.TestRunner([self.rd.tests[0]], verbose=False)
		runner.runTestsInOrder()
		self.assertContains("3 of 4 bad.  avg", runner.stats.getReport())

	def testRelativeSource(self):
		self.assertEqual(self.rd.tests[1].tests[0].url.getValue("http://foo"),
			"http://foo/data/regtest/foo?testParam=10%25w%2Fo+tax")

	def testRelativeSourceWithParam(self):
		self.assertEqual(self.rd.tests[1].tests[3].url.getValue("http://foo"),
			"http://foo/data/regtest/nork?urk=zoo&oo=1&oo=2")

	def testAbsoluteSource(self):
		self.assertEqual(self.rd.tests[1].tests[1].url.getValue("http://foo"),
			"http://foo/bar")

	def testURISource(self):
		self.assertEqual(self.rd.tests[1].tests[2].url.getValue("http://foo"),
			"ivo://ivoa.net/std/quack")
		self.assertEqual(self.rd.tests[1].tests[2].url.getParams(), 
			[("gobba", "&?")])


class RegtestRunTest(_RegtestTest):
	def testRunWholeRD(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-v", "data/regtest"],))
		self.assertContains("**** Test failed: Failing Test -- http://localhost:8",
			stdout)
		self.assertContains("3 of 9 bad.  avg", stdout)
		self.assertEqual(stderr.count("."), 6)
		self.assertEqual(stderr.count("E"), 3)

	def testRunSuite(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["data/regtest#urltests"],))
		self.assertContains("0 of 5 bad.  avg", stdout)
	
	def testRunSingle(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-v", "data/regtest#atest"],))
		self.assertContains("0 of 1 bad.  avg", stdout)

	def testVerboseFailing(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-v", "data/regtest#failtest"],))
		self.assertContains("Test failed: Failing Test -- "
			"http://localhost:8080/data/regtest/foo?testParam=10%25w%2Fo+tax",
			stdout)
		self.assertContains(">>>> 'Wittgenstein' missing", stdout)
		self.assertContains("1 of 1 bad.  avg", stdout)

	def testXSDFailing(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-v", "data/regtest#xsdfail"],))
		self.assertContains(">>>> Response not XSD valid.  Validator output"
			" starts with\n",
			stdout)

	def testXpathFailing(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-v", "data/regtest#xpathfail"],))
		self.assertContains(" not lots -- http://localhost:8080/bar\n\n"
			">>>> Trouble with type: //v2:RESOURCE[1] ('lots', 'meta')\n"
			"1 of 1 bad.",
			stdout)
	
	def testTagSelects(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-t", "elite", "data/regtest#dumbsuite"],))
		self.assertContains("4 of 5 bad.", stdout)

	def testWrongTagSelectsNot(self):
		proc, stdout, stderr = testhelpers.captureOutput(regtest.main,
			args=(["-t", "bigserver", "data/regtest#dumbsuite"],))
		self.assertContains("3 of 4 bad.", stdout)


class _CombinedData(testhelpers.TestResource):
	resources = [("csTable", tresc.csTestTable),
		("randomTable", tresc.randomDataTable)]

	def make(self, dependents):
		return rsc.makeCombinedData(testhelpers.getTestRD().getById("metatest"),
			{"primary": dependents["csTable"], "other": dependents["randomTable"]})


class CombiningDataTest(testhelpers.VerboseTest):
	resources = [("data", _CombinedData())]

	def testTablesIterating(self):
		names = [t.tableDef.id for t in self.data]
		self.assertEqual(names, ['randomDataTable', 'csdata'])
	
	def testMetaFromBasis(self):
		self.assertEqual(base.getMetaText(self.data.dd, "onData"), "present")

	def testPrimaryTable(self):
		res = self.data.getPrimaryTable()
		self.assertEqual(list(res), [
			{'tinyflag': None, 'alpha': 10.0, 'rV': None, 
			'mag': 14.0, 'delta': 12.0}])
	
	def testSecondaryTable(self):
		self.assertEqual(self.data.getTableWithRole("other").rows[0],
			{'n': 23, 'x': 29.25})

if __name__=="__main__":
	testhelpers.main(RegtestRunTest)
