"""
Some tests for the database interface.

This only works with psycopg2.
"""

import datetime
import os
import sys
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import svcs
from gavo import protocols
from gavo.base import coords
from gavo.base import config
from gavo.base import sqlsupport
from gavo.utils import pgsphere

import tresc


class ProfileTest(testhelpers.VerboseTest):
	parser = config.ProfileParser("data")

	def testEmptyProfile(self):
		nullProfile = self.parser.parse("test1", None, "")
		self.assertRaisesWithMsg(base.StructureError,
			"Insufficient information to connect to the database in profile 'test1'.",
			base.getDBConnection,
			(nullProfile,))

	def testInvalidProfile(self):
		self.assertRaisesWithMsg(config.ProfileParseError,
			"\"internal\", line 3: unknown setting 'hsot'",
			self.parser.parse,
			("test2", "internal", "database=gavo\nhsot=bar\n"))


class ConnectionsTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]
	
	def testConnectionConfiguration(self):
		cursor = self.conn.cursor()
		cursor.execute("SELECT current_setting('statement_timeout')")
		prevVal = list(cursor)[0][0]
		with base.connectionConfiguration(self.conn, statement_timeout=34):
			cursor.execute("SELECT current_setting('statement_timeout')")
			self.assertEqual(list(cursor)[0][0], "34ms")
		cursor.execute("SELECT current_setting('statement_timeout')")
		self.assertEqual(list(cursor)[0][0], prevVal)
		cursor.close()

	def testConnectionConfigurationErrorReset(self):
		cursor = self.conn.cursor()
		cursor.execute("SELECT current_setting('statement_timeout')")
		prevVal = list(cursor)[0][0]
		try:
			with base.connectionConfiguration(self.conn, statement_timeout=34):
				raise ValueError("expected")
		except ValueError:
			pass # expected
		cursor.execute("SELECT current_setting('statement_timeout')")
		self.assertEqual(list(cursor)[0][0], prevVal)
		cursor.close()


	def testConnectionConfigurationAutocommitted(self):
		with base.getTableConn() as conn:
			cursor = conn.cursor()
			cursor.execute("SELECT current_setting('statement_timeout')")
			prevVal = list(cursor)[0][0]
			with base.connectionConfiguration(conn, statement_timeout=34,
					isLocal=False):
				cursor.execute("SELECT current_setting('statement_timeout')")
				self.assertEqual(list(cursor)[0][0], "34ms")
			cursor.execute("SELECT current_setting('statement_timeout')")
			self.assertEqual(list(cursor)[0][0], prevVal)
			cursor.close()

	def testConnectionConfigurationDBErrorReset(self):
		with base.getTableConn() as conn:
			cursor = conn.cursor()
			cursor.execute("SELECT current_setting('statement_timeout')")
			prevVal = list(cursor)[0][0]
			try:
				with base.connectionConfiguration(conn, statement_timeout=34,
						isLocal=False):
					cursor.execute("totally whacky ")
			except sqlsupport.DBError:
				pass # expected error
			else:
				self.fail("DB server is whacky")
			cursor.execute("SELECT current_setting('statement_timeout')")
			self.assertEqual(list(cursor)[0][0], prevVal)
			cursor.close()


class TestTypes(testhelpers.VerboseTest):
	"""Tests for some special adapters we provide.
	"""
	resources = [("conn", tresc.dbConnection)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		dd = testhelpers.getTestRD().getById("boxTest")
		self.data = rsc.makeData(dd, forceSource=[{"box": coords.Box(1,2,3,4)}],
			connection=self.conn)
		self.table = self.data.tables["misctypes"]

	def tearDown(self):
		self.data.dropTables(rsc.parseNonValidating)
		testhelpers.VerboseTest.tearDown(self)

	def testBoxUnpack(self):
		rows = [r for r in 
			self.table.iterQuery(
				svcs.OutputTableDef.fromTableDef(self.table.tableDef, None), 
				"box IS NOT NULL")]
		self.assertEqual(rows[0]["box"][0], (2,4))
		self.assertEqual(rows[0]["box"][1], (1,3))


class TestWithTableCreation(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	tableName = None
	rdId = "test.rd"
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
		testhelpers.VerboseTest.setUp(self)
		if self.tableName is None:
			return
		self.querier = base.SimpleQuerier(connection=self.conn)
		self.tableDef = testhelpers.getTestTable(self.tableName, self.rdId)
		self.table = rsc.TableForDef(self.tableDef, rows=self.rows,
			connection=self.conn, create=True)
		self.conn.commit()

	def tearDown(self):
		if self.tableName is None:
			return
		self.table.drop().commit()


class TestPrivs(TestWithTableCreation):
	"""Tests for privilege management.
	"""
	tableName = "valSpec"

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
	rdId = "privtest.rd"

	def setUp(self):
		# We need a private querier here since we must squeeze those
		# users in before TestPriv's setup
		try:
			with base.AdhocQuerier(base.getAdminConn) as querier:
				querier.query("create user privtestuser")
				querier.query("create user testadmin")
		except base.DBError: # probably left over from a previous crash
			sys.stderr.write("Test roles already present?  Rats.\n")
		
		self.profDir = base.getConfig("configDir") 
		with open(os.path.join(self.profDir, "privtest"), "w") as f:
			f.write("include dsn\nuser=privtestuser\n")
		with open(os.path.join(self.profDir, "testadmin"), "w") as f:
			f.write("include dsn\nuser=testadmin\n")
		base.setConfig("profiles", "privtest", "privtest")
		base.setConfig("profiles", "testadmin", "testadmin")
	
		TestPrivs.setUp(self)
	
	def tearDown(self):
		TestPrivs.tearDown(self)
		self.querier.query("drop schema test cascade")
		self.querier.query("drop user privtestuser")
		self.querier.query("drop user testadmin")
		self.querier.commit()
		os.unlink(os.path.join(self.profDir, "privtest"))
		os.unlink(os.path.join(self.profDir, "testadmin"))


class SimpleQuerierTest(TestWithTableCreation):
	tableName = "typesTable"
	rows = [{"anint": 3, "afloat": 3.25, "adouble": 7.5,
			"atext": "foo", "adate": datetime.date(2003, 11, 13)}]
	
	def testPlainQuery(self):
		q = base.SimpleQuerier(connection=self.conn)
		self.assertEqual(q.runIsolatedQuery(
				"select * from %s"%self.tableDef.getQName()),
			[(3, 3.25, 7.5, u'foo', datetime.date(2003, 11, 13))])

	def testDictQuery(self):
		q = base.SimpleQuerier(connection=self.conn)
		self.assertEqual(q.runIsolatedQuery(
				"select * from %s"%self.tableDef.getQName(), asDict=True),
			[{'anint': 3, 'afloat': 3.25, 'adouble': 7.5, 'atext': u'foo', 
				'adate': datetime.date(2003, 11, 13)}])


class AdhocQuerierTest(testhelpers.VerboseTest):
	resources = [("table", tresc.csTestTable)]

	def testBasic(self):
		with base.AdhocQuerier() as q:
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName()))))

	def testAdminQuerier(self):
		with base.AdhocQuerier(base.getAdminConn) as q:
			self.assertRuns(q.query,
				("create role dont",))
			self.assertRuns(q.query,
				("drop role dont",))
	
	def testNoAdminQuerier(self):
		with base.AdhocQuerier() as q:
			self.assertRaises(sqlsupport.ProgrammingError, q.query,
				"create role dont")

	def testReopen(self):
		q = base.AdhocQuerier()
		with q:
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName()))))
		self.assertRaises(base.ReportableError, 
			q.query, "select * from dc.tables")
		with q:
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName()))))

	def testGetSetTimeout(self):
		with base.AdhocQuerier() as q:
			q.setTimeout(3)
			self.assertAlmostEqual(q.getTimeout(), 3.)

	def testTimeoutReset(self):
		with base.AdhocQuerier() as q:
			q.setTimeout(0)
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName(), timeout=2))))
			self.assertEqual(q.getTimeout(), 0)


class TestMetaTable(TestWithTableCreation):
	tableName = "typesTable"

	def testDcTablesEntry(self):
		with  base.AdhocQuerier() as q:
			res = q.query("select * from dc.tablemeta where tableName=%(n)s",
				{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, td, rd, adql = res[0]
		self.assertEqual(qName, 'test.typesTable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, False)

	def testColInfo(self):
		mh = rsc.MetaTableHandler()
		res = mh.getColumnsForTable(self.tableDef.getQName())
		self.assertEqual([(f.name, f.type, f.getLabel())
				for f in res], [
			(u'anint', 'integer', u'An Integer'), 
			(u'afloat', 'real', u'Some Real'), 
			(u'adouble', 'double precision', u'And a Double'), 
			(u'atext', 'text', u'A string must be in here as well'), 
			(u'adate', 'date', u'When')])


class TestMetaTableADQL(TestWithTableCreation):
	tableName = "adqltable"

	def testDcTablesEntry(self):
		q = base.SimpleQuerier(connection=self.conn)
		res = q.query("select * from dc.tablemeta where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, td, rd, adql = res[0]
		self.assertEqual(qName, 'test.adqltable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, True)

	def testColInfo(self):
		mh = rsc.MetaTableHandler()
		res = mh.getColumnsForTable(self.tableDef.getQName())
		self.assertEqual([(f.name, f.type, f.getLabel()) 
				for f in res], [
			(u'foo', 'double precision', 'Foo'), ])
		mh.close()


class TestPgSphere(testhelpers.VerboseTest):
	"""tests for the python interface to pgsphere.
	"""
	resources = [("conn", tresc.dbConnection)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		pgsphere.preparePgSphere(self.conn)

	def assertTripsRound(self, testedType, testValue):
		cursor = self.conn.cursor()
		cursor.execute("CREATE TABLE pgstest (col %s)"%testedType)
		cursor.execute("INSERT INTO pgstest (col) VALUES (%(val)s)",
			{"val": testValue})
		cursor.execute("SELECT * from pgstest")
		self.assertEqual(list(cursor)[0][0], testValue)
		cursor.execute("DROP TABLE pgstest")

	def testSPoints(self):
		self.assertTripsRound("spoint", pgsphere.SPoint(2,0.5))

	def testSCircle(self):
		self.assertTripsRound("scircle",
			pgsphere.SCircle(pgsphere.SPoint(2,0.5), 0.25))

	def testSPoly(self):
		self.assertTripsRound("spoly",
			pgsphere.SPoly([pgsphere.SPoint(2,0.5),
				pgsphere.SPoint(2.5,-0.5),
				pgsphere.SPoint(1.5,0),]))

	def testSBox(self):
		self.assertTripsRound("sbox",
			pgsphere.SBox(pgsphere.SPoint(2.5,-0.5),
				pgsphere.SPoint(2.0,0.5)))


class TestWithDataImport(testhelpers.VerboseTest):
	"""base class for tests importing data up front.

	You need to set the ddId, which must point into test.rd
	"""
	resources = [("connection", tresc.dbConnection)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		dd = testhelpers.getTestRD().getById(self.ddId)
		self.data = rsc.makeData(dd, connection=self.connection)
	

class TestPreIndexSQLRunning(TestWithDataImport):
	"""tests for dbtables running preIndexSQL scripts.
	"""
	ddId = "import_sqlscript"

	def testScriptRan(self):
		q = base.SimpleQuerier(connection=self.connection)
		ct = list(q.query("select count(*) from test.sqlscript"))[0][0]
		self.assertEqual(ct, 3)


class TestPreIndexPythonRunning(TestWithDataImport):
	"""tests for dbtables running preIndexSQL scripts.
	"""
	ddId = "import_pythonscript"

	def testScriptRan(self):
		q = base.SimpleQuerier(connection=self.connection)
		ct = list(q.query("select * from test.pythonscript"))[0][0]
		self.assertEqual(ct, 123)


class TestQueryExpands(TestWithTableCreation):
	"""tests for expansion of macros in dbtable's query.
	"""
	tableName = "adqltable"

	def testExpandedQuery(self):
		self.table.query("insert into \qName (\colNames) values (-133.0)")
		self.assertEqual(
			len(list(self.table.iterQuery([self.tableDef.getColumnByName("foo")],
				"foo=-133.0"))),
			1)

	def testBadMacroRaises(self):
		self.assertRaises(base.MacroError, self.table.query, "\monkmacrobad")


if __name__=="__main__":
	testhelpers.main(AdhocQuerierTest)
