"""
Tests pertaining to the parsing system
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import contextlib
import datetime
import itertools
import os
import shutil
import tempfile
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.base import sqlsupport
from gavo.web import formrender

import tresc


@contextlib.contextmanager
def _inputFile(fName, content):
	with open(fName, "w") as f:
		f.write(content)
	try:
		yield
	finally:
		os.unlink(fName)


class SimpleParseTest(testhelpers.VerboseTest):
	"""tests for some simple parses.
	"""
	def _getDD(self):
		return base.parseFromString(rscdef.DataDescriptor, '<data>'
			'<sources>testInput.txt</sources>'
			'<columnGrammar><col key="val1">3</col>'
			'<col key="val2">6-10</col></columnGrammar>'
			'<table id="foo"><column name="x" type="integer"/>'
			'<column name="y" type="text"/>'
			'</table><rowmaker id="bla_foo">'
			'<map dest="y" src="val2"/>'
			'<map dest="x" src="val1"/>'
			'</rowmaker><make table="foo" rowmaker="bla_foo"/></data>')

	def testBasic(self):
		with _inputFile("testInput.txt", "xx1xxabc, xxxx\n"):
			dd = self._getDD()
			data = rsc.makeData(dd)
			self.assertEqual(data.getPrimaryTable().rows, [{'y': u'abc,', 'x': 1}])
	
	def testRaising(self):
		with _inputFile("testInput.txt", "xxxxxabc, xxxx\n"):
			dd = self._getDD()
			self.assertRaisesWithMsg(base.ValidationError,
				"Field x: While building x in bla_foo: invalid literal for int()"
					" with base 10: 'x'",
				rsc.makeData, (dd,))
	
	def testValidation(self):
		with _inputFile("testInput.txt", "xx1xxabc, xxxx\n"):
			dd = base.parseFromString(rscdef.DataDescriptor, '<data>'
				'<sources pattern="testInput.txt"/>'
				'<columnGrammar><col key="val1">3</col></columnGrammar>'
				'<table id="foo"><column name="x" type="integer"/>'
				'<column name="y" type="text"/></table><rowmaker id="bla_foo">'
				'<map dest="x" src="val1"/></rowmaker>'
				'<make table="foo" rowmaker="bla_foo"/></data>')
			rsc.makeData(dd, rsc.parseNonValidating)
			self.assertRaisesWithMsg(base.ValidationError,
				"Field y: Column y missing",
				rsc.makeData, (dd, rsc.parseValidating))

	def testNonExistingSource(self):
		dd = self._getDD()
		try:
			rsc.makeData(dd)
		except base.SourceParseError, ex:
			msg = str(ex)
			self.assertTrue(msg.startswith(
				"At start: I/O operation failed ([Errno 2] No such file or directory:"))
			self.assertTrue(msg.endswith("tests/testInput.txt')"))


class RowsetTest(testhelpers.VerboseTest):
	def assertQueryReturns(self, query, expected):
		cursor = self.conn.cursor()
		cursor.execute(query)
		found = list(cursor)
		self.assertEqual(len(found), len(expected), 
			"Rowset length didn't match: %s"%str(found))
		for f, e in itertools.izip(sorted(found), sorted(expected)):
			self.assertEqual(f, e, "Rows don't match: %s vs. %s"%(f, e))


class TestProductsImport(RowsetTest):
	"""tests for operational import of real data.

	This is more of an integration test, but never mind that.
	"""
	resources = [("conn", tresc.prodtestTable)]

	def testWorkingImport(self):
		self.assertQueryReturns("select object from test.prodtest",
			[("gabriel",), ("michael",)])
	
	def testInProducts(self):
		self.assertQueryReturns(
				"select * from dc.products where sourceTable='test.prodtest'",
			[(u'data/a.imp', u'X_test', datetime.date(2030, 12, 31), 
					'text/plain', u'data/a.imp', u'test.prodtest', 
					'data/broken.imp', None, 'text/plain'),
			 (u'data/b.imp', u'X_test', datetime.date(2003, 12, 31), 
					'text/plain', u'data/b.imp', u'test.prodtest', 
					'http://example.com/borken.jpg', None, 'image/jpeg'),])

	def testNoMixinInMem(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"Tables mixing in product must be onDisk, but foo is not",
			base.parseFromString, (rscdesc.RD, 
				'<resource schema="test"><table id="foo" mixin="//products#table">'
					'</table></resource>',))
	
	def testImportWithBadFails(self):
		dd = testhelpers.getTestRD().getById("productimport")
		self.assertRaisesWithMsg(base.SourceParseError,
			"At unspecified location: Not a key value pair: 'kaputt.'",
			rsc.makeData,
			(dd,),
			parseOptions=rsc.parseValidating, connection=self.conn)


class ProductsSkippingTest(RowsetTest):
	resources = [("conn", tresc.dbConnection)]

	def _testImportWithSkipBehavesConsistently(self, parseOptions):
# This is of course crappy behaviour we don't want, but it's hard
# to fix this, and actually sometimes this "skip just one table"
# might be what people want.  Anyway, we need to be consistent.
		dd = testhelpers.getTestRD().getById("productimport-skip")
		data = rsc.makeData(dd, 
			parseOptions=parseOptions, connection=self.conn)
		try:
			self.assertQueryReturns("select object from test.prodskip",
				[(u'gabriel',)])
			self.assertQueryReturns("select accref from dc.products where"
				" sourceTable='test.prodskip'",
				[(u'data/a.imp',), (u'data/b.imp',)])
		finally:
			data.dropTables(parseOptions)
			self.conn.commit()

	def testImportWithSkipBehavesKeepGoing(self):
		self._testImportWithSkipBehavesConsistently(rsc.parseValidating.change(
			keepGoing=True))

	def testImportWithSkipBehavesNormal(self):
		self._testImportWithSkipBehavesConsistently(rsc.parseValidating.change(
			keepGoing=False))


class _WildResource(testhelpers.TestResource):
	def make(self, ignored):
		tempPath = tempfile.mkdtemp(suffix="parsetest", 
			dir=str(base.getConfig("inputsdir")))
		rdSrc = """<resource schema="%s">
			<table onDisk="true" id="deleteme" mixin="//products#table"/>
			<data id="import">
				<sources pattern="*"/>
				<keyValueGrammar>
					<rowfilter procDef="//products#define">
						<bind key="table">"deleteme"</bind>
					</rowfilter>
				</keyValueGrammar>
				<make table="deleteme"/>
			</data>
		</resource>"""%os.path.basename(tempPath)
		rd = base.parseFromString(rscdesc.RD, rdSrc)
		return rd
	
	def clean(self, rd):
		shutil.rmtree(rd.resdir)


class ProductsBadNameTest(testhelpers.VerboseTest):
# Products are supposed to have well-behaved file names.
# This is a test making sure bad file names are rejected.

	resources = [("rd", _WildResource())]

	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		destName, shouldBeOk = sample
		fullPath = os.path.join(base.getConfig("inputsDir"), destName)
		f = open(fullPath, "w")
		try:
			ex = None
			try:
				list(self.rd.dds[0].grammar.parse(fullPath, None))
			except ValueError, ex:
				pass
			if shouldBeOk and ex:
				raise AssertionError("Filename %s should be legal but is not"%destName)
			elif not shouldBeOk and ex is None:
				raise AssertionError("Filename %s should be illegal"
					" but is not"%destName)
		finally:
			f.close()
			os.unlink(fullPath)
	
	samples = [
		("ok_LOT,allowed-this_ought,to10000do.file", True),
		("Q2232+23.fits", False),
		("A&A23..1.fits", False),
		("name with blank.fits", False),
		("name%with%blank.fits", False),
		("don't want quotes", False),]


class CleanedupTest(RowsetTest):
	"""tests for cleanup after table drop (may fail if other tests failed).
	"""
	resources = [("conn", tresc.dbConnection), ("table", tresc.prodtestTable)]

	def tearDown(self):
		self.conn.rollback()

	def testNotInProducts(self):
		rsc.Data.drop(testhelpers.getTestRD().getById("productimport"), 
			connection=self.conn)
		self.assertQueryReturns(
			"select * from dc.products where sourceTable='test.prodtest'",
			[])
		self.assertQueryReturns(
			"select * from dc.tablemeta where tableName='test.prodtest'",
			[])


class DispatchedGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		rd = base.parseFromString(rscdesc.RD,
			"""
			<resource schema="test">
				<table id="t1"><column name="x" type="text"/></table>
				<table id="t2"><column name="y" type="text"/></table>
				<data id="import">
					<sources items="foo"/>
					<embeddedGrammar isDispatching="True"><iterator><code>
						yield "one", {"x": "x1", "y": "FAIL"}
						yield "two", {"x": "FAIL", "y": "y1"}
						yield "one", {"x": "x2", "y": "FAIL"}
					</code></iterator></embeddedGrammar>
					<make role="one" table="t1"/>
					<make role="two" table="t2"/>
				</data>
			</resource>
			""")
		data = rsc.makeData(rd.getById("import"))
		self.assertEqual([r["x"] for r in data.getTableWithRole("one").rows],
			["x1", "x2"])
		self.assertEqual([r["y"] for r in data.getTableWithRole("two").rows],
			["y1"])

	def testNoRole(self):
		dd = base.parseFromString(rscdef.DataDescriptor, """<data id="import">
					<sources items="foo"/>
					<embeddedGrammar isDispatching="True"><iterator><code>
						yield "one", {"x": "x1", "y": "FAIL"}
					</code></iterator></embeddedGrammar>
				</data>
			""")
		self.assertRaisesWithMsg(base.ReportableError,
			"Grammar tries to feed to role 'one', but there is no corresponding make",
			rsc.makeData, (dd,))


class CrossResolutionTest(testhelpers.VerboseTest):
# NOTE: DaCHS-internal code should use base.resolveCrossId instead of
# of the getReferencedElement exercised here.
	def testItemAbsolute(self):
		res = rscdef.getReferencedElement("data/test#ADQLTest")
		self.assertEqual(res.id, "ADQLTest")
	
	def testRDAbsolute(self):
		res = rscdef.getReferencedElement("data/test")
		self.assertEqual(res.sourceId, "data/test")

	def testRDTypecheck(self):
		self.assertRaisesWithMsg(base.StructureError,
			"Reference to 'data/test' yielded object of type RD, expected TableDef",
			rscdef.getReferencedElement,
			("data/test", rscdef.TableDef))

	def testItemError(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"Element with id 'nonexisting' could not be located in RD data/test",
			rscdef.getReferencedElement,
			("data/test#nonexisting",))

	def testRDError(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"Resource descriptor 'nonexisting' could not be located in file system",
			rscdef.getReferencedElement,
			("nonexisting",))

	def testItemRelative(self):
		wd = os.path.join(base.getConfig("inputsDir"), "test")
		with testhelpers.testFile(os.path.join(wd, "rel.rd"), 
				"""<resource schema="foo"><table id="bar"/></resource>"""):
			with utils.in_dir(wd):
				res = rscdef.getReferencedElement("rel#bar", rscdef.TableDef)
				self.assertEqual(res.id, "bar")

	def testRelativeMessage(self):
		wd = os.path.join(base.getConfig("inputsDir"), "test")
		with utils.in_dir(wd):
			self.assertRaisesWithMsg(base.NotFoundError,
				"Resource descriptor 'test/foo' could not be located in file system",
				rscdef.getReferencedElement,
				("foo#bar", rscdef.TableDef))

	def testRDRelative(self):
		wd = os.path.join(base.getConfig("inputsDir"), "test")
		with testhelpers.testFile(os.path.join(wd, "rel.rd"), 
				"""<resource schema="foo"><table id="bar"/></resource>"""):
			with utils.in_dir(wd):
				res = rscdef.getReferencedElement("rel")
				self.assertEqual(res.sourceId, "test/rel")


if __name__=="__main__":
	testhelpers.main(DispatchedGrammarTest)
