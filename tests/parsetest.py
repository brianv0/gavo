"""
Tests pertaining to the parsing system
"""

import itertools
import os
import unittest

from mx import DateTime

from gavo import config
from gavo import nullui
from gavo import sqlsupport
from gavo.parsing import importparser
from gavo.parsing import macros
from gavo.parsing import processors
from gavo.parsing import resource

import testhelpers

class MacroErrorTest(unittest.TestCase):
	"""Tests for error reporting of macros and processors.
	"""
	def testDateRangeFieldReporting(self):
		p = processors.DateExpander([("start", "startDate", ""),
			("end", "endDate", ""), ("hrInterval", "intv", "")])
		try:
			l = p(None, {"startDate": "2000-01-01", "endDate": "2000-13-31",
				"intv": "300"})
		except Exception, msg:
			self.assertEqual(msg.fieldName, "endDate")
		else:
			self.fail("2000-13-31 is regarded as a valid date...")
		try:
			l = p(None, {"startDate": "2000-01-01", "endDate": "2000-12-31",
				"intv": "a00"})
		except Exception, msg:
			self.assertEqual(msg.fieldName, "intv")
		else:
			self.fail("a00 is regarded as a valid integer...")


class ProcessorsTest(unittest.TestCase):
	"""Tests for some row processors.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
	
	def testExpandComma(self):
		"""test for correct operation of the expandComma row processor.
		"""
		dd = self.rd.getDataById("processortest")
		data = resource.InternalDataSet(dd, dataSource=[
			(12.5, "one, two, three"),
			(1.2, ""),
			(2.2, "four,"),
			(0, "five")])
		rows = data.getPrimaryTable().rows
		self.assertEqual(len(rows), 5)
		self.assertAlmostEqual(rows[0]["c"], 12.5)
		self.assertEqual(rows[0]["tf"], "one")
		self.assertEqual(rows[4]["tf"], "five")


def assertRowset(self, found, expected):
	self.assertEqual(len(found), len(expected), "Rowset length didn't match")
	for f, e in itertools.izip(sorted(found), sorted(expected)):
		self.assertEqual(f, e, "Rows don't match: %s vs. %s"%(f, e))


class TestProductsImport(unittest.TestCase):
	"""tests for operational import of real data.

	This is more of an integration test, but never mind that.
	"""
	def setUp(self):
		config.setDbProfile("test")
		self.oldInputs = config.get("inputsDir")
		config.set("inputsDir", os.getcwd())
		rd = importparser.getRd("test")
		self.tableDef = rd.getTableDefByName("prodtest")
		res = resource.Resource(rd)
		res.importData(None, ["productimport"])
		res.export("sql", ["productimport"])
	
	def testWorkingImport(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select object from"
				" test.prodtest"),
			[("gabriel",)])
	
	def testInProducts(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" products where sourceTable='test.prodtest'"),
			[(u'data/a.imp', u'test', DateTime.DateTime(2030, 12, 31), 
				u'data/a.imp', u'test.prodtest')])

	def testInMetatable(self):
		fields = sorted([(r[9], r[1], r[4]) for r in
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" fielddescriptions where tableName='test.prodtest'")])
		assertRowset(self, fields, [
			(0, u'object', None), 
			(1, u'alpha', None), 
			(2, u'accref', None), 
			(3, u'owner', None), 
			(4, u'embargo', None), 
			(5, u'accsize', u'Size of the image in bytes')])

	def tearDown(self):
		tw = sqlsupport.TableWriter(self.tableDef)
		tw.dropTable()
		tw.finish()
		config.set("inputsDir", self.oldInputs)


class TestCleanedup(unittest.TestCase):
	"""tests for cleanup after table drop (may fail if other tests failed).
	"""
	def setUp(self):
		config.setDbProfile("admin")

	def testNotInProducts(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" products where sourceTable='test.prodtest'"),
			[])

	def testNotInMetatable(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" fielddescriptions where tableName='test.prodtest'"),
			[])

	def testNotInDc_tables(self):
		assertRowset(self,
			sqlsupport.SimpleQuerier().runIsolatedQuery("select * from"
				" dc_tables where tableName='test.prodtest'"),
			[])


if __name__=="__main__":
	testhelpers.main(TestProductsImport)
#	testhelpers.main(TestCleanedup)
