"""
Tests pertaining to the parsing system
"""

import datetime
import itertools
import os
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


def _prepareData(fName, content):
	f = open(fName, "w")
	f.write(content)
	f.close()


class SimpleParseTest(testhelpers.VerboseTest):
	"""tests for some simple parses.
	"""
	def _getDD(self):
		return base.parseFromString(rscdef.DataDescriptor, '<data>'
			'<sources pattern="testInput.txt"/>'
			'<columnGrammar><col key="val1">3</col>'
			'<col key="val2">6-10</col></columnGrammar>'
			'<table id="foo"><column name="x" type="integer"/>'
			'<column name="y" type="text"/>'
			'</table><rowmaker id="bla_foo">'
			'<map dest="y" src="val2"/>'
			'<map dest="x" src="val1"/>'
			'</rowmaker><make table="foo" rowmaker="bla_foo"/></data>')

	def testBasic(self):
		_prepareData("testInput.txt", "xx1xxabc, xxxx\n")
		try:
			dd = self._getDD()
			data = rsc.makeData(dd)
			self.assertEqual(data.getPrimaryTable().rows, [{'y': u'abc,', 'x': 1}])
		finally:
			os.unlink("testInput.txt")
			data.closeAll()
	
	def testRaising(self):
		_prepareData("testInput.txt", "xxxxxabc, xxxx\n")
		try:
			dd = self._getDD()
			self.assertRaisesWithMsg(base.ValidationError,
				"While building x in bla_foo: invalid literal for int()"
					" with base 10: 'x'",
				rsc.makeData, (dd,))
		finally:
			os.unlink("testInput.txt")
	
	def testValidation(self):
		_prepareData("testInput.txt", "xx1xxabc, xxxx\n")
		try:
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
		finally:
			os.unlink("testInput.txt")


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


class TestCleanedup(unittest.TestCase):
	"""tests for cleanup after table drop (may fail if other tests failed).
	"""
	def testNotInProducts(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier(useProfile="admin"
				).runIsolatedQuery(
				"select * from dc.products where sourceTable='test.prodtest'"),
			[])

	def testNotInMetatable(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" dc.columnmeta where tableName='test.prodtest'"),
			[])

	def testNotInDc_tables(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" dc.tablemeta where tableName='test.prodtest'"),
			[])


if __name__=="__main__":
	testhelpers.main(TestCleanedup)
