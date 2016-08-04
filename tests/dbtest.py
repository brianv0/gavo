"""
Some tests for the database interface and the surrounding helper code.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import contextlib
import datetime
import os
import sys
import unittest

import numpy

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
from gavo.utils import pyfits

import tresc


class GetSQLTest(testhelpers.VerboseTest):
# this is for "dumb" fields.  See also viziertest and pqltest for advanced
# SQL generation from stuff coming in from the web.
	def _assertSQLGenerated(self, ikArgs, inputPars, fragment, sqlPars):
		foundPars = {}
		inputKey = base.makeStruct(svcs.InputKey, **ikArgs)
		foundFragment = base.getSQLForField(inputKey, inputPars, foundPars)
		self.assertEqual(fragment, foundFragment)
		self.assertEqual(sqlPars, foundPars)

	def testSimpleString(self):
		self._assertSQLGenerated(
			{"name": "foo", "type": "text"}, 
			{"foo": ["';"]}, 
			'foo=%(foo0)s',	{'foo0': u"';"})
	
	def testEmptyString(self):
		self._assertSQLGenerated(
			{"name": "foo", "type": "text"}, 
			{"foo": [""]},
			'foo=%(foo0)s', {'foo0': u""})

	def testMissingString(self):
		self._assertSQLGenerated(
			{"name": "foo", "type": "text"},
			{},
			None, {})

	def testIntSeq(self):
		self._assertSQLGenerated(
			{"name": "foo", "type": "integer"}, 
			{"foo": map(int, "1 2 3 4".split())},
			'foo IN %(foo0)s', {'foo0': set([1,2,3,4])})


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

	def testWhitespace(self):
		profile = self.parser.parse("foo", None, stream="""
			user = honk

			password="secre t  "  
			
			""")
		self.assertEqual(profile.user, "honk")
		self.assertEqual(profile.password, "secre t  ")


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


@contextlib.contextmanager
def digestedTable(connection, name, columns, values):
	"""a context manager to have a temporary table with ddl and values,
	also providing the whole table after digestion by the database.

	Values is a list of dicts sutable for for INSERT statements.

	ddl is a string that is pasted behind create temp table.

	None of the inputs is validated in any way, so this function must
	never receive untrusted input.
	"""
	connection.execute("CREATE TEMP TABLE %s %s"%(name, columns))
	for row in values:
		connection.execute("INSERT INTO %s (%s) VALUES (%s)"%(
			name, ", ".join(row), ", ".join("%%(%s)s"%s for s in row)),
			row)
	yield list(connection.queryToDicts("SELECT * FROM %s"%name))
	connection.rollback()


class TestTypes(testhelpers.VerboseTest):
	"""Tests for some special adapters we provide.
	"""
	resources = [("conn", tresc.dbConnection)]

	def testNumpyFloat(self):
		with digestedTable(self.conn, "n_a_t", "(b REAL)",
				[{"b": numpy.float(0.25)}]) as rows:
			self.assertEqual(rows[0]["b"], 0.25)

	def testNumpyFloat32(self):
		with digestedTable(self.conn, "n_a_t", "(b REAL)",
				[{"b": numpy.float32(0.25)}]) as rows:
			self.assertEqual(rows[0]["b"], 0.25)

	def testNumpyFloat64(self):
		with digestedTable(self.conn, "n_a_t", "(b REAL)",
				[{"b": numpy.float64(0.25)}]) as rows:
			self.assertEqual(rows[0]["b"], 0.25)

	def testNumpyInt8(self):
		with digestedTable(self.conn, "n_a_t", "(b BIGINT)",
				[{"b": numpy.int8(10)}]) as rows:
			self.assertEqual(rows[0]["b"], 10)

	def testNumpyInt64(self):
		with digestedTable(self.conn, "n_a_t", "(b BIGINT)",
				[{"b": numpy.int64(388290102316)}]) as rows:
			self.assertEqual(rows[0]["b"], 388290102316)

	def testNumpyInteger(self):
		with digestedTable(self.conn, "n_a_t", "(b BIGINT)",
				[{"b": numpy.int(302316)}]) as rows:
			self.assertEqual(rows[0]["b"], 302316)

	def testNumpyArray(self):
		with digestedTable(self.conn, "n_a_t", "(b double precision[])",
				[{"b": numpy.array([1.0, 1.5, 2])}]) as rows:
			self.assertEqual(rows[0]["b"], [1.0, 1.5, 2.0])

	def testPyfitsUndefined(self):
		with digestedTable(self.conn, "n_a_t", "(a float, b text)",
				[{"a": pyfits.Undefined(), "b": pyfits.Undefined()}]) as rows:
			self.assertEqual(rows[0]["a"], None)
			self.assertEqual(rows[0]["b"], None)


class TestWithTableCreation(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection)]

	tableName = None
	rdId = "test.rd"
	rows = []

	def _assertPrivileges(self, foundPrivs, expPrivs):
		# profile user might not be mentioned in table acl, so retrofit it
		profileUser = base.getDBProfile("admin").user
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
		self.querier = base.UnmanagedQuerier(connection=self.conn)
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
			with base.AdhocQuerier(base.getWritableAdminConn) as querier:
				querier.query("create user privtestuser")
				querier.query("create user testadmin")
		except base.DBError: # probably left over from a previous crash
			sys.stderr.write("Test roles already present."
				" Hope we'll clear them later.\n")
		
		self.profDir = base.getConfig("configDir") 
		with open(os.path.join(self.profDir, "privtest"), "w") as f:
			f.write("include dsn\nuser=privtestuser\n")
		with open(os.path.join(self.profDir, "testadmin"), "w") as f:
			f.write("include dsn\nuser=testadmin\n")
	
		TestPrivs.setUp(self)
	
	def tearDown(self):
		TestPrivs.tearDown(self)
		self.querier.query("drop schema test cascade")
		self.querier.query("drop user privtestuser")
		self.querier.query("drop user testadmin")
		self.querier.connection.commit()
		os.unlink(os.path.join(self.profDir, "privtest"))
		os.unlink(os.path.join(self.profDir, "testadmin"))


class AdhocQuerierTest(testhelpers.VerboseTest):
	resources = [("table", tresc.csTestTable), ("conn", tresc.dbConnection)]

	def testBasic(self):
		with base.AdhocQuerier() as q:
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName()))))

	def testAdminQuerier(self):
		with base.AdhocQuerier(base.getWritableAdminConn) as q:
			self.assertRuns(q.query,
				("create role dont",))
			self.assertRuns(q.query,
				("drop role dont",))
	
	def testNoAdminQuerier(self):
		with base.AdhocQuerier() as q:
			self.assertRaises(
				(sqlsupport.ProgrammingError, sqlsupport.InternalError),
				q.query,
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
			q.setTimeout(-12)
			self.assertEqual(1, len(list(q.query(
				"select * from %s limit 1"%self.table.tableDef.getQName(), timeout=2))))
			self.assertEqual(q.getTimeout(), 0)

	def testNoInjectionOnGetColumns(self):
		q = base.UnmanagedQuerier(self.conn)
		self.assertRaisesWithMsg(ValueError,
			"'foo; drop tables' is not a SQL regular identifier",
			q.getColumnsFromDB,
			("foo; drop tables",))

	def testGetColumns(self):
		with digestedTable(self.conn, "odd_table", 
				"(t text, s smallint, i integer, b bigint,"
				" r real, d double precision, ar real[], c char,"
				" ad double precision[], odd char(20), frotsch bytea[30],"
				" fro bytea, ts timestamp, dt date, ti time,"
				" boo boolean)", []):
			q = base.UnmanagedQuerier(self.conn)
			self.assertEqual(q.getColumnsFromDB("odd_table"), [
				('t', u'text'), ('s', u'int2'), ('i', u'int4'),
				('b', u'int8'), ('r', u'float4'), ('d', u'float8'),
				('ar', u'_float4'), ('c', u'bpchar'), ('ad', u'_float8'),
				('odd', u'bpchar'), ('frotsch', u'_bytea'), ('fro', u'bytea'),
				('ts', u'timestamp'), ('dt', u'date'), ('ti', u'time'),
				('boo', u'bool')])


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


class TestMetaTableADQL(TestWithTableCreation):
	tableName = "adqltable"

	def testDcTablesEntry(self):
		q = base.UnmanagedQuerier(connection=self.conn)
		res = q.query("select * from dc.tablemeta where tableName=%(n)s",
			{"n": self.tableDef.getQName()}).fetchall()
		qName, srcRd, td, rd, adql = res[0]
		self.assertEqual(qName, 'test.adqltable')
		self.assertEqual(srcRd.split("/")[-1], 'test')
		self.assertEqual(adql, True)


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
		q = base.UnmanagedQuerier(connection=self.connection)
		ct = list(q.query("select count(*) from test.sqlscript"))[0][0]
		self.assertEqual(ct, 3)


class TestPreIndexPythonRunning(TestWithDataImport):
	"""tests for dbtables running preIndexSQL scripts.
	"""
	ddId = "import_pythonscript"

	def testScriptRan(self):
		q = base.UnmanagedQuerier(connection=self.connection)
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


class TestIgnoreFrom(testhelpers.VerboseTest):
	resources = [("connection", tresc.dbConnection)]

	def testWorksWithoutTable(self):
		rsc.TableForDef(testhelpers.getTestRD().getById("prodtest"),
			connection=self.connection, create=False).drop()
		self.data = rsc.makeData(
			testhelpers.getTestRD().getById("productimport"),
			rsc.getParseOptions(keepGoing=True),
			connection=self.connection)
		self.assertEqual(
			set(self.connection.query("select object from test.prodtest")),
			set([('gabriel',), ('michael',)]))

	def testWorksWithTable(self):
		data1 = rsc.makeData(
			testhelpers.getTestRD().getById("productimport"),
			rsc.getParseOptions(keepGoing=True),
			connection=self.connection)
		self.assertEqual(data1.nAffected, 2)
		data2 = rsc.makeData(
			testhelpers.getTestRD().getById("productimport"),
			rsc.getParseOptions(updateMode=True, keepGoing=True),
			connection=self.connection)
		self.assertEqual(data2.nAffected, 0)


if __name__=="__main__":
	testhelpers.main(AdhocQuerierTest)
