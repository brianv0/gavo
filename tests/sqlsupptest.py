"""
Tests for the simple SQL support infrastucture.

Needs connectivity to the db defined in the test profile.
"""

import re
import os
import unittest

import gavo
from gavo import config
from gavo import datadef
from gavo import nullui
from gavo import sqlsupport
from gavo import table
from gavo.parsing import importparser
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import scripting

import testhelpers

_predefinedFields = {
	"klein": datadef.DataField(dest="klein", dbtype="smallint", source="klein"),
	"prim": datadef.DataField(dest="prim", dbtype="integer", source="prim",
		primary="True", description="Some random primary key"),
	"nopt": datadef.DataField(dest="nopt", dbtype="real", optional="False",
		source="nopt"),
	"echter": datadef.DataField(dest="echter", dbtype="double precision",
		source="echter"),
	"datum": datadef.DataField(dest="datum", dbtype="date", source="datum"),
	"indf": datadef.DataField(dest="indf", dbtype="text", index="find",
		source="indf"),}

def _getFields(*args):
	return [_predefinedFields[a].copy() for a in args]


class TestSimpleQueries(unittest.TestCase):
	def setUp(self):
		config.setDbProfile("test")
		sq = sqlsupport.SimpleQuerier()
		sq.runIsolatedQuery("CREATE TABLE sqtest (c1 text, c2 integer, "
			"fix boolean)", raiseExc=False)
		sq.runIsolatedQuery("INSERT INTO sqtest (c1, c2, fix) VALUES "
			"('eins', 3, true)", raiseExc=False)
		sq.finish()

	def testSimpleQueries(self):
		"""tests for working query method.
		"""
		sq = sqlsupport.SimpleQuerier()
		try:
			c = sq.query("SELECT c1 FROM sqtest WHERE fix=%(fix)s", {"fix": True})
			res = c.fetchall()
			self.assertEqual(len(res), 1, "Basic query didn't return exactly one"
				" row")
			self.assertEqual(res[0][0], "eins", "Basic query returned wrong row")
		finally:
			sq.close()
	
	def testExceptionPropagation(self):
		"""tests for query raising proper exceptions.
		"""
		sq = sqlsupport.SimpleQuerier()
		sq2 = sqlsupport.SimpleQuerier()
		try:
			self.assertRaises(sqlsupport.DbError, sq.query, "SELECT nonexistent"
				" FROM sqtest")
			# everything will raise an error until the transaction has ended
			self.assertRaises(sqlsupport.DbError, sq.query, 
				"SELECT c1 FROM sqtest WHERE fix=%(fix)s", {"fix": True})
			sq.close()
			c = sq2.query("SELECT c1 FROM sqtest WHERE fix=True").fetchall()
			self.assertEqual(len(c), 1, "Querier doesn't seem to recover from error")
		finally:
			sq.close()
			sq2.close()

	def testRollback(self):
		"""tests for query recovering on a rollback
		"""
		sq = sqlsupport.SimpleQuerier()
		try:
			self.assertRaises(sqlsupport.DbError, sq.query, "SELECT nonexistent"
				" FROM sqtest")
			sq.rollback()
			c = sq.query("SELECT c1 FROM sqtest WHERE fix=True").fetchall()
			self.assertEqual(len(c), 1, "Rollback doesn't heal a transaction")
		finally:
			sq.close()

	def testIsolation(self):
		"""tests for transaction isolation.
		"""
		sq = sqlsupport.SimpleQuerier()
		sq2 = sqlsupport.SimpleQuerier()  # A second connection
		try:
			sq.runIsolatedQuery("SLECT junk FORM misguided", raiseExc=False,
				silent=True)
			# The following queries must still run due to isolation of the error above
			c = sq.query("INSERT INTO sqtest (c1, c2, fix) VALUES ('zwei', 7, false)")
			c = sq.query("INSERT INTO sqtest (c1, c2, fix) VALUES ('dri', 19, false)")
			self.assertEqual(c.rowcount, 1)
			sq.commit()
			c = sq2.query("DELETE FROM sqtest WHERE c2=7")
			self.assertEqual(c.rowcount, 1, "Delete failed")
			self.assertEqual(len(sq.query("SELECT c1 FROM sqtest").fetchall()), 3,
				"Transactions aren't properly isolated from one another")
			self.assertEqual(len(sq2.query("SELECT c1 FROM sqtest").fetchall()), 2,
				"Weird delete")
			sq2.finish()
			self.assertEqual(len(sq.query("SELECT c1 FROM sqtest").fetchall()), 2,
				"Transactions don't commit properly")
			sq2 = sqlsupport.SimpleQuerier()  # A third connection
			sq.query("DELETE FROM sqtest WHERE fix=false")
			self.assertEqual(len(sq2.query("SELECT c1 FROM sqtest").fetchall()), 2,
				"Hu?  Database doesn't really implement transactions?")
			sq.finish()
			self.assertEqual(len(sq2.query("SELECT c1 FROM sqtest").fetchall()), 1,
				"Hu?  Database doesn't really implement transactions?")
		finally:
			sq.close()
			sq2.close()

	def tearDown(self):
		sq = sqlsupport.SimpleQuerier()
		sq.query("DROP TABLE sqtest CASCADE")
		sq.finish()


class TestTableWriter(unittest.TestCase):
	"""tests for various aspects of the table writer.
	"""
	def setUp(self):
		config.setDbProfile("test")
		self.tableName = "twtest"

	def testSimpleCreationAndIsolation(self):
		"""tests for creation of a simple table and isolation during feeding.
		"""
		def countTb():
			return len(sq.runIsolatedQuery("SELECT * FROM %s"%self.tableName))

		fields = _getFields("klein", "echter")
		tw = sqlsupport.TableWriter(self.tableName, fields)
		try:
			tw.createTable()
			feed = tw.getFeeder()
			feed({"klein": 1, "echter": 2.1})
			self.assertEqual(feed.close(), 1, "Problem with feeder affected count.")
		finally:
			tw.finish()
		sq = sqlsupport.SimpleQuerier()
		self.assertEqual(1, countTb(), "Data didn't make it to db?")
		tw = sqlsupport.TableWriter(self.tableName, fields)
		try:
			tw.createTable()
			feed = tw.getFeeder()
			feed({"klein": 4, "echter": 1.1})
			feed.close()
		finally:
			tw.abort()
		self.assertEqual(1, countTb(), "Bad mess on aborted table import")
		self.assertEqual(1,
			sq.runIsolatedQuery("SELECT klein FROM %s"%self.tableName)[0][0],
			"Aborted table write left weird traces.")
		sq.finish()

	def testCreationWithIndices(self):
		"""tests for table creation and modification using indices.
		"""
		fields = _getFields("klein", "prim", "indf")
		tw = sqlsupport.TableWriter(self.tableName, fields)
		try:
			tw.createTable()
			feed = tw.getFeeder()
			feed({"klein": 1, "prim": 4, "indf": 12.2})
			feed({"klein": 2, "prim": 5, "indf": 17.2})
			feed.close()
		finally:
			tw.finish()
		sq = sqlsupport.SimpleQuerier()
		self.failUnless(len(tw.getIndices())>0, "TableWriter didn't find any"
			" indices")
		for indexName in tw.getIndices():
			self.failUnless(sq.hasIndex(self.tableName, indexName), "Index %s"
				" was not generated"%indexName)
		self.failUnless(sq.hasIndex(self.tableName, self.tableName+"_pkey"), 
			"Primary key was not recognized") 
		tw = sqlsupport.TableWriter(self.tableName, fields)
		try:
			feed = tw.getFeeder(dropIndices=False)
			self.failUnless(tw.hasIndex(self.tableName, self.tableName+"_pkey"), 
				"Primary key was dropped on update despite dropIndices=False") 
			self.assertRaises(sqlsupport.DbError, feed,
				{"klein": 2, "prim": 5, "indf": 17.2})
			self.assertRaises(sqlsupport.DbError, feed,
				{"klein": 2, "prim": 9, "indf": 17.2})
		finally:
			tw.finish()
		sq.close()

	def testUpdater(self):
		"""tests for the table updater.
		"""
		fields = _getFields("klein", "prim", "indf")
		tw = sqlsupport.TableWriter(self.tableName, fields)
		sq = sqlsupport.SimpleQuerier()
		tw.createTable()
		feed = tw.getFeeder()
		feed({"klein": 1, "prim": 4, "indf": 12.2})
		feed({"klein": 2, "prim": 5, "indf": 17.2})
		feed.close()
		tw.finish()

		tu = sqlsupport.TableUpdater(self.tableName, fields)
		feed = tu.getFeeder()
		self.failIf(tu.hasIndex(self.tableName, self.tableName+"_pkey"), 
			"Primary key was not dropped on update") 
		feed({"klein": 8, "prim": 5, "indf": 12.2})
		feed.close()
		tu.finish()

		self.failUnless(sq.hasIndex(self.tableName, self.tableName+"_pkey"), 
			"Primary key was not restored after update")
		self.assertEqual(sq.runIsolatedQuery("SELECT klein FROM %s"
			" WHERE prim=5"%
			self.tableName)[0][0], 8, "Table update didn't update table")
		sq.close()


	def tearDown(self):
		sq = sqlsupport.SimpleQuerier()
		sq.runIsolatedQuery("DROP table %s"%self.tableName, silent=True,
			raiseExc=False)
		sq.close()


class TestImport(unittest.TestCase):
	"""is not a unit test at all -- it's a macro test for the functionality
	of the SQL import infrastructure.  Thus, it's a bit dangerous running
	this when your test db is your production db.  But you shouldn't do that
	anyway.

	This test should probably go to a test suite of its own, together with
	a few more "big picture" tests.
	"""
	def setUp(self):
		self.tableName = "imptest"
		config.setDbProfile("test")

	def _makeRd(self, fields):
		rd = resource.ResourceDescriptor()
		rd.set_resdir(os.path.abspath("."))
		rd.set_schema("test")
		grammar = rowsetgrammar.RowsetGrammar(initvals={"dbFields": fields})
		dataDesc = resource.DataDescriptor(rd, 
			id="randomTest",
			Grammar=grammar,
			Semantics=resource.Semantics(
				initvals={
					"recordDefs": [
						resource.RecordDef(initvals={
							"table": self.tableName,
							"items": fields,
							"create": True,
						})]}))
		rd.addto_dataSrcs(dataDesc)
		return rd

	def testNormalTable(self):
		"""tests for correct creation of "normal" tables.
		"""
		rd = self._makeRd(_getFields("prim", "nopt", "echter"))
		ds = resource.InternalDataSet(rd.get_dataSrcs()[0], table.Table, 
			dataSource=[
				(1, 2.5, 4),
				(2, 7.5, 9),])
		ds.exportToSql(rd.get_schema())
		sq = sqlsupport.SimpleQuerier()
		noRows = sq.runIsolatedQuery("SELECT count(*) FROM test.imptest")[0][0]
		self.assertEqual(2, noRows, "Import didn't leave exactly two rows")
		ds = resource.InternalDataSet(rd.get_dataSrcs()[0], table.Table, 
			dataSource=[
				(2, 9.3, 14),
				(2, 9.8, 19)])
		self.assertRaises(gavo.Error, ds.exportToSql, rd.get_schema())
		res = sq.runIsolatedQuery("SELECT nopt FROM test.imptest WHERE prim=1")
		self.assertEqual(len(res), 1, "Failed import damages table")
		self.assertEqual(res[0][0], 2.5, "Failed import damages table content")
		sq.close()

	def testSharedTable(self):
		"""tests for correct handling of shared tables.
		"""
		rd = self._makeRd(_getFields("prim", "indf"))
		rd.set_schema("public")
		ds = resource.InternalDataSet(rd.get_dataSrcs()[0], table.Table, 
			dataSource=[
				(1, "honk"), (2, "honk"), (3, "flob"), (4, "flob"), (5, "nox")])
		ds.exportToSql(rd.get_schema())
		td = rd.getTableDefByName(self.tableName)
		td.set_shared(True)
		td.set_owningCondition(("indf", "flob"))
		ds = resource.InternalDataSet(rd.get_dataSrcs()[0], table.Table, 
			dataSource=[(7, "flob"), (8, "flob"), (9, "flob")])
		ds.exportToSql(rd.get_schema())
		sq = sqlsupport.SimpleQuerier()
		res = sq.runIsolatedQuery("SELECT prim FROM imptest WHERE indf='flob'")
		self.assertEqual(len(res), 3, "Weird goings-on with sharedTables")
		self.assertEqual(set([r[0] for r in res]), set([7,8,9]),
			"Replacing stuff in shared tables doesn't work as advertised")
		sq.runIsolatedQuery("DROP TABLE imptest")
		sq.commit()
	
	def testDirectTable(self):
		"""tests for correct handling of tables directly written.
		"""
		rd = self._makeRd(_getFields("prim", "indf"))
		td = rd.getTableDefByName(self.tableName)
		td.set_onDisk(True)
		ds = resource.InternalDataSet(rd.get_dataSrcs()[0], 
			table.DirectWritingTable, dataSource=[
			(1, "honk"), (2, "honk"), (3, "flob"), (4, "flob"), (5, "nox")])
		sq = sqlsupport.SimpleQuerier()
		res = sq.runIsolatedQuery("SELECT prim FROM test.imptest WHERE indf='flob'")
		self.assertEqual(len(res), 2, "Directly writing tables aren't written")
		self.assertEqual(set([r[0] for r in res]), set([3,4]),
			"Directly writing tables write junk")

	def tearDown(self):
		sq = sqlsupport.SimpleQuerier()
		sq.runIsolatedQuery("DROP SCHEMA test CASCADE", silent=True, 
			raiseExc=False)
		sq.commit()


class TestMisc(unittest.TestCase):
	"""tests for various small utility classes.
	"""
	def setUp(self):
		config.setDbProfile("test")

	def testNames(self):
		"""tests for _parseTableName.
		"""
		sq = sqlsupport.SimpleQuerier()
		schema, tn = sq._parseTableName("foo")
		self.assertEqual(schema, "public")
		self.assertEqual(tn, "foo")
		schema, tn = sq._parseTableName("foo", schema="bombast")
		self.assertEqual(schema, "bombast", "Schema argument is ignored")
		self.assertEqual(tn, "foo")
		schema, tn = sq._parseTableName("bar.foo", schema="bombast")
		self.assertEqual(schema, "bar", "Qname doesn't override schema")
		self.assertEqual(tn, "foo")
		sq.close()


class TestScriptRunner(unittest.TestCase):
	"""tests for SQLScriptRunner.
	"""
	def setUp(self):
		config.setDbProfile("test")
		sq = sqlsupport.SimpleQuerier()
		sq.runIsolatedQuery("DROP TABLE scripttest", silent=True, raiseExc=False)
		sq.close()
	
	def testWorkingScript(self):
		"""tests for behaviour of scripts running without errors.
		"""
		sr = scripting.SQLScriptRunner()
		sr.run(r"""CREATE TABLE scripttest (a text, b int)
			INSERT INTO scripttest (a, b) VALUES ('foo in'
				' two lines', 20)
		""")
		sq = sqlsupport.SimpleQuerier()
		self.assertEqual("foo in two lines",
			sq.runIsolatedQuery("SELECT a FROM scripttest")[0][0])
		sq.runIsolatedQuery("DROP TABLE scripttest")
		sq.close()

	def testScriptRaises(self):
		"""tests for an exception being thrown by bad scripts
		"""
		sr = scripting.SQLScriptRunner()
		self.assertRaises(sqlsupport.DbError, sr.run, "DROP TABLE scripttest")
		self.assertRaises(sqlsupport.DbError, sr.run, "wroppa is blup---")

	def testScriptWithIgnoredErrors(self):
		"""tests for bad instructions being isolated and eliminated.
		"""
		sr = scripting.SQLScriptRunner()
		sr.run("-DROP TABLE scripttest\n"
			"CREATE TABLE scripttest (a text primary key, b int)\n"
			"-wroppa is blup---\n"
			"INSERT INTO scripttest (a, b) VALUES ('foo', 3)\n"
			"-INSERT INTO scripttest (a, b) VALUES ('foo', 4)\n"
			"INSERT INTO scripttest (a, b) VALUES ('bar', 4)\n")
		sq = sqlsupport.SimpleQuerier()
		res = sq.runIsolatedQuery("SELECT b FROM scripttest WHERE a='foo'")
		self.assertEqual(1, len(res))
		self.assertEqual(3, res[0][0])
		res = sq.runIsolatedQuery("SELECT b FROM scripttest WHERE a='bar'")
		self.assertEqual(1, len(res))
		self.assertEqual(4, res[0][0])
		sq.runIsolatedQuery("DROP TABLE scripttest")
		sq.close()


class ScriptSplitterTest(testhelpers.VerboseTest):
	"""tests for splitting SQL scripts into individual commands.
	"""
	def _getSample(self):
		sample = []
		splitRE = re.compile(r"----+ (\d+) ----+\n$")
		curExpected, curCode = None, None
		for ln in open("scriptsplitter.sample"):
			mat = splitRE.match(ln)
			if mat:
				if curCode:
					sample.append((curExpected, "".join(curCode)))
				curExpected, curCode = int(mat.group(1)), []
			else:
				if curCode!=None:
					curCode.append(ln)
		if curExpected!=None:
			sample.append((curExpected, "".join(curCode)))
		return sample

	def testGrammarIsValid(self):
		"""tests that the SQL grammar doesn't do infinite recursion.
		"""
		grammar = scripting.getSQLScriptGrammar()
		grammar.validate()

	def testCorrectSplits(self):
		grammar = scripting.getSQLScriptGrammar()
		for expected, code in self._getSample():
			parts = grammar.parseString(code)
			found = len(parts)
			self.assertEqual(expected, found,
				"%d instead of %d parts found in split %s"%(found, expected, parts))

	def testBadSource(self):
		grammar = scripting.getSQLScriptGrammar()
		for bad in [
			"select (foo (bar)",
			"ab )",
			"ab 'x",
			"ab 'x', y'",
			"ab 'x', y$$",
		]:
			self.assertRaisesVerbose(scripting.ParseException,
				grammar.parseString, (bad,), "%s was accepted"%bad)


def singleTest():
	suite = unittest.makeSuite(ScriptSplitterTest, "testB")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	unittest.main()
#	singleTest()
