"""
Some tests for the database interface.

This only works with psycopg2.
"""

import datetime
import sys
import unittest

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo import svcs
from gavo import protocols
from gavo.base import coords
from gavo.base import sqlsupport

import testhelpers


class TestTypes(unittest.TestCase):
	"""Tests for some special adapters we provide.
	"""
	def setUp(self):
		base.setDBProfile("test")
		dd = testhelpers.getTestRD().getById("boxTest")
		self.data = rsc.makeData(dd, forceSource=[{"box": coords.Box(1,2,3,4)}])
		self.table = self.data.tables["misctypes"]

	def tearDown(self):
		self.data.dropTables()

	def testBoxUnpack(self):
		rows = [r for r in 
			self.table.iterQuery(
				svcs.OutputTableDef.fromTableDef(self.table.tableDef), 
				"box IS NOT NULL")]
		self.assertEqual(rows[0]["box"][0], (2,4))
		self.assertEqual(rows[0]["box"][1], (1,3))



class TestWithTableCreation(unittest.TestCase):
	tableName = None
	rows = []

	def _assertPrivileges(self, foundPrivs, expPrivs):
		# profile user might not be mentioned in table acl, so retrofit it
		profileUser = base.getDBProfile().user
		expPrivs[profileUser] = foundPrivs[profileUser]
		self.assertEqual(set(foundPrivs), set(expPrivs))
		for role in foundPrivs:
			self.assertEqual(foundPrivs[role], expPrivs[role],
				"Privileges for %s don't match: found %s, expected %s"%(role, 
					foundPrivs[role], expPrivs[role]))

	def setUp(self):
		if self.tableName is None:
			return
		base.setDBProfile("test")
		self.querier = base.SimpleQuerier(useProfile="test")
		self.tableDef = testhelpers.getTestTable(self.tableName)
		self.table = rsc.TableForDef(self.tableDef, rows=self.rows).commit()

	def tearDown(self):
		if self.tableName is None:
			return
		self.table.drop().commit()


class TestPrivs(TestWithTableCreation):
	"""Tests for privilege management.
	"""
	tableName = "valspec"

	def testDefaultPrivileges(self):
		self._assertPrivileges(self.querier.getTablePrivileges(
				self.tableDef.rd.schema, self.tableDef.id),
			self.querier.getACLFromRes(self.tableDef))


class TestADQLPrivs(TestPrivs):
	"""Tests for privilege management for ADQL-enabled tables.
	"""
	tableName = "adqltable"


class TestRoleSetting(TestPrivs):
	tableName = "privtable"

	def setUp(self):
		base.setDBProfile("test")
		q = base.SimpleQuerier()
		try:
			q.query("create user privtestuser")
			q.query("create user testadmin")
		except base.DBError: # probably left over from a previous crash
			sys.stderr.write("Test roles already present?  Rats.\n")
		q.finish()
		TestPrivs.setUp(self)
	
	def tearDown(self):
		TestPrivs.tearDown(self)
		q = base.SimpleQuerier()
		q.query("drop schema test cascade")
		q.query("drop user privtestuser")
		q.query("drop user testadmin")
		q.finish()


class SimpleQuerierTest(TestWithTableCreation):
	tableName = "typestable"
	rows = [{"anint": 3, "afloat": 3.25, "adouble": 7.5,
			"atext": "foo", "adate": datetime.date(2003, 11, 13)}]
	
	def testPlainQuery(self):
		q = base.SimpleQuerier()
		self.assertEqual(q.runIsolatedQuery(
				"select * from %s"%self.tableDef.getQName()),
			[(3, 3.25, 7.5, u'foo', datetime.date(2003, 11, 13))])

	def testDictQuery(self):
		q = base.SimpleQuerier()
		self.assertEqual(q.runIsolatedQuery(
				"select * from %s"%self.tableDef.getQName(), asDict=True),
			[{'anint': 3, 'afloat': 3.25, 'adouble': 7.5, 'atext': u'foo', 
				'adate': datetime.date(2003, 11, 13)}])


class TestMetaTable(TestWithTableCreation):
	tableName = "typestable"

	def testDcTablesEntry(self):
		q = base.SimpleQuerier()
		res = q.query("select * from dc.tablemeta where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, td, rd, adql = res[0]
		self.assertEqual(qName, 'test.typestable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, False)

	def testColInfo(self):
		mh = rsc.MetaTableHandler('test')
		res = mh.getColumnsForTable(self.tableDef.getQName())
		self.assertEqual([(f.name, f.type, f.tablehead)
				for f in res], [
			(u'anint', 'integer', u'An Integer'), 
			(u'afloat', 'real', u'Some Real'), 
			(u'adouble', 'double precision', u'And a Double'), 
			(u'atext', 'text', u'A string must be in here as well'), 
			(u'adate', 'date', u'When')])


class TestMetaTableADQL(TestWithTableCreation):
	tableName = "adqltable"

	def testDcTablesEntry(self):
		q = base.SimpleQuerier()
		res = q.query("select * from dc.tablemeta where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, td, rd, adql = res[0]
		self.assertEqual(qName, 'test.adqltable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, True)

	def testColInfo(self):
		mh = rsc.MetaTableHandler('test')
		res = mh.getColumnsForTable(self.tableDef.getQName())
		self.assertEqual([(f.name, f.type, f.tablehead) 
				for f in res], [
			(u'foo', 'double precision', 'foo'), ])


if __name__=="__main__":
	testhelpers.main(TestMetaTable, "test")
