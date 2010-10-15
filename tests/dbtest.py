"""
Some tests for the database interface.

This only works with psycopg2.
"""

import datetime
import sys
import unittest

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
from gavo.helpers import testhelpers

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
		self.data.dropTables()
		testhelpers.VerboseTest.tearDown(self)

	def testBoxUnpack(self):
		rows = [r for r in 
			self.table.iterQuery(
				svcs.OutputTableDef.fromTableDef(self.table.tableDef), 
				"box IS NOT NULL")]
		self.assertEqual(rows[0]["box"][0], (2,4))
		self.assertEqual(rows[0]["box"][1], (1,3))


class TestWithTableCreation(unittest.TestCase):
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
		if self.tableName is None:
			return
		self.querier = base.SimpleQuerier(useProfile="test")
		self.tableDef = testhelpers.getTestTable(self.tableName, self.rdId)
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
	rdId = "privtest.rd"

	def setUp(self):
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
	testhelpers.main(TestPgSphere)
