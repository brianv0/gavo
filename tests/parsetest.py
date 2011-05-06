"""
Tests pertaining to the parsing system
"""

import contextlib
import datetime
import itertools
import os
import shutil
import tempfile
import unittest

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.base import sqlsupport
from gavo.helpers import testhelpers
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
				"While building x in bla_foo: invalid literal for int()"
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
				"Column y missing",
				rsc.makeData, (dd, rsc.parseValidating))

	def testNonExistingSource(self):
		dd = self._getDD()
		self.assertRaisesWithMsg(base.SourceParseError, 
			"At start: I/O operation failed ([Errno 2] No such file or directory:"
			" u'/home/msdemlei/gavo/trunk/tests/testInput.txt')",
			rsc.makeData,
			(dd,))


def assertRowset(self, found, expected):
	self.assertEqual(len(found), len(expected), "Rowset length didn't match")
	for f, e in itertools.izip(sorted(found), sorted(expected)):
		self.assertEqual(f, e, "Rows don't match: %s vs. %s"%(f, e))


class TestProductsImport(testhelpers.VerboseTest):
	"""tests for operational import of real data.

	This is more of an integration test, but never mind that.
	"""
	resources = [("conn", tresc.prodtestTable)]

	def testWorkingImport(self):
		assertRowset(self,
			list(sqlsupport.SimpleQuerier(connection=self.conn).query(
				"select object from test.prodtest")),
			[("gabriel",), ("michael",)])
	
	def testInProducts(self):
		assertRowset(self,
			list(sqlsupport.SimpleQuerier(connection=self.conn).query(
				"select * from dc.products where sourceTable='test.prodtest'")),
			[(u'data/a.imp', u'X_test', datetime.date(2030, 12, 31), 
					'text/plain', u'data/a.imp', u'test.prodtest'),
			 (u'data/b.imp', u'X_test', datetime.date(2003, 12, 31), 
					'text/plain', u'data/b.imp', u'test.prodtest'),])

	def testInMetatable(self):
		fields = sorted([(r[7], r[1], r[4]) for r in
			sqlsupport.SimpleQuerier(connection=self.conn).query(
				"select * from dc.columnmeta where tableName='test.prodtest'")])
		assertRowset(self, fields, [
			(0, u'accref', u'Access key for the data'),
			(1, u'owner', u'Owner of the data'),
			(2, u'embargo', u'Date the data will become/became public'),
			(3, u'mime', u'MIME type of the file served'),
			(4, u'accsize', u'Size of the data in bytes'),
			(5, u'object', u''),
			(6, u'alpha', u''),
			(7, u'delta', u'')])

	def testNoMixinInMem(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"Tables mixing in product must be onDisk, but foo is not",
			base.parseFromString, (rscdesc.RD, 
				'<resource schema="test"><table id="foo" mixin="//products#table">'
					'</table></resource>',))


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
		with open(destName, "w") as f:
			fullPath = os.path.abspath(f.name)
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
			os.unlink(fullPath)
	
	samples = [
		("ok_LOT,allowed-this_ought,to10000%do.file", True),
		("Q2232+23.fits", False),
		("A&A23..1.fits", False),
		("name with blank.fits", False),
		("don't want quotes", False),]


class TestCleanedup(testhelpers.VerboseTest):
	"""tests for cleanup after table drop (may fail if other tests failed).
	"""
	resources = [("conn", tresc.dbConnection)]

	def testNotInProducts(self):
		assertRowset(self,
			list(sqlsupport.SimpleQuerier(connection=self.conn
				).query(
				"select * from dc.products where sourceTable='test.prodtest'")),
			[])

	def testNotInMetatable(self):
		assertRowset(self,
			list(sqlsupport.SimpleQuerier(connection=self.conn).query(
			"select * from dc.columnmeta where tableName='test.prodtest'")),
			[])

	def testNotInDc_tables(self):
		assertRowset(self,
			list(sqlsupport.SimpleQuerier(connection=self.conn).query(
				"select * from dc.tablemeta where tableName='test.prodtest'")),
			[])


if __name__=="__main__":
	testhelpers.main(ProductsBadNameTest)
