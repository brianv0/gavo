"""
Some tests for the database interface.

This only works with psycopg2.
"""

import sys
import unittest

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import nullui
from gavo import sqlsupport

import testhelpers


class TestTypes(unittest.TestCase):
	"""Tests for some special adapters we provide.
	"""
	def setUp(self):
		config.setDbProfile("test")
		tableDef = testhelpers.getTestTable("misctypes")
		tw = sqlsupport.TableWriter(tableDef)
		tw.createTable()
		feed = tw.getFeeder()
		feed({"box": coords.Box(1,2,3,4)})
		tw.finish()
		self.tableName = tableDef.getQName()

	def testBoxUnpack(self):
		querier = sqlsupport.SimpleQuerier()
		try:
			r = querier.query(
				"SELECT * FROM %s WHERE box IS NOT NULL"%self.tableName).fetchall()
			self.assertEqual(r[0][0][0], (2,4))
			self.assertEqual(r[0][0][1], (1,3))
		finally:
			querier.close()

	def tearDown(self):
		sqlsupport.SimpleQuerier().runIsolatedQuery(
			"DROP TABLE %s CASCADE"%self.tableName)


class TestWithTableCreation(unittest.TestCase):
	tableName = None

	def _assertPrivileges(self, foundPrivs, expPrivs):
		# profile user might not be mentioned in table acl, so retrofit it
		profileUser = config.getDbProfile().get_user() 
		expPrivs[profileUser] = foundPrivs[profileUser]
		self.assertEqual(set(foundPrivs), set(expPrivs))
		for role in foundPrivs:
			self.assertEqual(foundPrivs[role], expPrivs[role],
				"Privileges for %s don't match: found %s, expected %s"%(role, 
					foundPrivs[role], expPrivs[role]))

	def setUp(self):
		if self.tableName is None:
			return
		config.setDbProfile("test")
		self.querier = sqlsupport.SimpleQuerier(useProfile="test")
		self.tableDef = testhelpers.getTestTable(self.tableName)
		tw = sqlsupport.TableWriter(self.tableDef)
		tw.createTable()
		tw.finish()

	def tearDown(self):
		if self.tableName is None:
			return
		sqlsupport.SimpleQuerier().runIsolatedQuery("DROP TABLE %s CASCADE"%
			self.tableDef.getQName())


class TestPrivs(TestWithTableCreation):
	"""Tests for privilege management.
	"""
	tableName = "valspec"

	def testDefaultPrivileges(self):
		self._assertPrivileges(sqlsupport.getTablePrivileges(
			self.tableDef.rd.get_schema(), self.tableDef.get_table(), self.querier),
			sqlsupport.getACLFromRes(self.tableDef))


class TestADQLPrivs(TestPrivs):
	"""Tests for privilege management for ADQL-enabled tables.
	"""
	tableName = "adqltable"


class TestRoleSetting(TestPrivs):
	tableName = "privtable"

	def setUp(self):
		config.setDbProfile("test")
		q = sqlsupport.SimpleQuerier()
		try:
			q.query("create user privtestuser")
			q.query("create user testadmin")
		except sqlsupport.DbError: # probably left over from a previous crash
			sys.stderr.write("Test roles already present?  Rats.\n")
		q.finish()
		TestPrivs.setUp(self)
	
	def tearDown(self):
		TestPrivs.tearDown(self)
		q = sqlsupport.SimpleQuerier()
		q.query("drop schema test cascade")
		q.query("drop user privtestuser")
		q.query("drop user testadmin")
		q.finish()


class TestMetaTable(TestWithTableCreation):
	tableName = "typestable"

	def testDcTablesEntry(self):
		q = sqlsupport.SimpleQuerier()
		res = q.query("select * from dc_tables where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, adql = res[0]
		self.assertEqual(qName, 'test.typestable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, False)

	def testColInfo(self):
		mh = sqlsupport.MetaTableHandler()
		res = mh.getFieldInfos(self.tableDef.getQName())
		self.assertEqual([(f.get_dest(), f.get_dbtype(), f.get_tablehead()) 
				for f in res], [
			(u'anint', 'int', u'An Integer'), 
			(u'afloat', 'real', u'Some Real'), 
			(u'adouble', 'double precision', u'And a Double'), 
			(u'atext', 'text', u'A string must be in here as well'), 
			(u'adate', 'date', u'When')])


class TestMetaTableADQL(TestWithTableCreation):
	tableName = "adqltable"

	def testDcTablesEntry(self):
		q = sqlsupport.SimpleQuerier()
		res = q.query("select * from dc_tables where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, adql = res[0]
		self.assertEqual(qName, 'test.adqltable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, True)

	def testColInfo(self):
		mh = sqlsupport.MetaTableHandler()
		res = mh.getFieldInfos(self.tableDef.getQName())
		self.assertEqual([(f.get_dest(), f.get_dbtype(), f.get_tablehead()) 
				for f in res], [
			(u'foo', 'double precision', None), ])


if __name__=="__main__":
	testhelpers.main(TestPrivs, "test")
