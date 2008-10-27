# -*- coding: iso-8859-1 -*-

"""
Tests for correct interpretation of vizier-type expressions.
"""

import sys
import unittest

import testhelpers

from gavo import config
from gavo import datadef
from gavo import nullui
from gavo import sqlsupport
from gavo.parsing import typeconversion
from gavo.web import gwidgets
from gavo.web import vizierexprs

import testhelpers


class GrammarTest(testhelpers.VerboseTest):
	def _assertResults(self, *examples):
		for expr, res in examples:
			try:
				found = str(self.parse(expr))
				self.assertEqual(found, res, "%r != expectation %r on example %r"%(
					found, res, expr))
			except vizierexprs.ParseException:
				raise AssertionError("%s doesn't parse"%expr)
			except:
				sys.stderr.write("\nFailed example is %s\n"%expr)
				raise

	def _assertFailures(self, *examples):
		for expr in examples:
			self.assertRaisesVerbose(vizierexprs.ParseException,
				self.parse, (expr,), "%s is bad but was accepted"%expr)


class SimpleFloatParsesTest(GrammarTest):
	def parse(self, val):
		return vizierexprs.parseNumericExpr(val)

	def testSimpleExprs(self):
		"""tests for correct parsing of simple expressions
		"""
		self._assertResults(
				("1", "(= 1)"),
				("> 1.5", "(> 1.5)"),
				(">-1", "(> -1)"),
				(">=-4.5", "(>= -4.5)"),
				("!=1", "(NOT (= 1))"),  # This one's complex in our implementation
				("<1", "(< 1)"),
				("<=1", "(<= 1)"),
			)

	def testMalformedSimpleExprs(self):
		"""tests for rejection of malformed simple expressions
		"""
		self._assertFailures("a1", "< x", "12ea")
	
	def testRanges(self):
		"""tests for correct parsing of ranges
		"""
		self._assertResults(
				("1 .. 2", "(.. 1 2)"),
				("1. .. 2", "(.. 1.0 2)"),
			)

	def testMalformedRanges(self):
		"""tests for rejection of malformed range expressions.
		"""
		self._assertFailures(".. 1", "1 ..", "1 .. x", "y .. 1", ".. ..",
			"1 .. 2 ..", "1 .. 2 ..")

	def testPM(self):
		"""tests for correct parsing of values with "errors"
		"""
		self._assertResults(
				("1 +/- 2", "(.. -1 3)"),
				("1. +/-2", "(.. -1.0 3.0)"),
				("1. ±  2".decode("iso-8859-1"), "(.. -1.0 3.0)"),
			)

	def testMalformedRanges(self):
		"""tests for rejection of malformed range expressions.
		"""
		self._assertFailures("+/- 1", "1 +/-", "1 +/- x", "y +/- 1")

	def testValList(self):
		"""tests for correct parsing of value lists.
		"""
		self._assertResults(
			("1,2", "(, 1 2)"),
			("1,2,3", "(, 1 2 3)"),
			)
	
	def _testMalformedValLists(self):
		"""tests for rejection of malformed value lists.
		"""
		self._assertFailures(",", "1,", "1,2,", ",1")


class ComplexFloatExpressionTest(GrammarTest):
	"""Tests for complex vizier-like expressions involving floats.
	"""
	def parse(self, val):
		return vizierexprs.parseNumericExpr(val)

	def testSimpleNot(self):
		"""tests for parses simple expressions with the not operator
		"""
		self._assertResults(
			("! 1", "(NOT (= 1))"),
			("! = 1", "(NOT (= 1))"),
			("! 1 .. 2", "(NOT (.. 1 2))"),
			("! < 1", "(NOT (< 1))"),
			("!>=1", "(NOT (>= 1))"),
		)
	
	def testSimpleNotFailures(self):
		"""tests for rejection of malformed simple not expressions.
		"""
		self._assertFailures("!", "!!", "!a")

	def testSimpleAnds(self):
		"""tests for simple and expressions.
		"""
		self._assertResults(
			(">1 & <3", "(AND (> 1) (< 3))"),
			("1 .. 2 & 1.5 +/- 0.5", "(AND (.. 1 2) (.. 1.0 2.0))"),
		)

	def testSimpleAndFailures(self):
		"""tests for rejection of malformed and expressions.
		"""
		self._assertFailures("&", "1 &", "& 1", "2 .. & 3")
	
	def testSimpeOrs(self):
		"""tests for simple or expressions.
		"""
		self._assertResults(
			(">1 | <3", "(OR (> 1) (< 3))"),
			("1 .. 2 | 1.5 +/- 0.5", "(OR (.. 1 2) (.. 1.0 2.0))"),
		)

	def testSimpleOrFailures(self):
		"""tests for rejection of malformed or expressions.
		"""
		self._assertFailures("|", "1 |", "| 1", "2 .. | 3")
	
	def testComplexLogic(self):
		"""tests for (unspecified by vizier) nested logic.
		"""
		self._assertResults(
			("! 1 & 2", "(AND (NOT (= 1)) (= 2))"),
			("! 1 & 2 | < 0", "(OR (AND (NOT (= 1)) (= 2)) (< 0))"),
		)


class ComplexDateExpresionTest(GrammarTest):
	"""Tests for complex vizier-like expressions involving dates.

	We just do a couple of them, dates share their grammar with floats.
	"""
	def parse(self, val):
		return vizierexprs.parseDateExpr(val)

	def testSome(self):
		"""tests for some expressions based on dates.
		"""
		self._assertResults(
			("2003-11-19", "(= 2003-11-19 00:00:00.00)"),
			("2003-11-19..2003-12-15", 
				"(.. 2003-11-19 00:00:00.00 2003-12-15 00:00:00.00)"),
			("2003-11-19 +/- 3", 
				"(.. 2003-11-16 00:00:00.00 2003-11-22 00:00:00.00)"),
		)


class StringParseTest(GrammarTest):
	def parse(self, val):
		return vizierexprs.parseStringExpr(val)
	
	def testSimpleExprs(self):
		"""tests for correct parsing of non-pattern string expressions.
		"""
		self._assertResults(
			("NGC", "(== NGC)"),
			("==NGC", "(== NGC)"),
			("~NGC", "(~ NGC)"),
			("!=     NGC", "(!= NGC)"),
			(">= M 51", "(>= M 51)"),
			("<= B*", "(<= B*)"),
			("< B*", "(< B*)"),
			("> Q3489+2901", "(> Q3489+2901)"),
			("> >foo<", "(> >foo<)"),
		)

	def testEnumerations(self):
		"""tests for correct parsing of enumerated string expressions.
		"""
		self._assertResults(
			("=,A,B,C", "(=, A B C)"),
			("!=,A,B,C", "(!=, A B C)"),
			("=|A|B|C", "(=| A B C)"),
			("=|1,2,3|B|C", "(=| 1,2,3 B C)"),
			("=|1, 2, 3|B|C", "(=| 1, 2, 3 B C)"),
			("=,1, 2, 3|B|C", "(=, 1 2 3|B|C)"),
		)
	
	def testEnumerationFailures(self):
		self._assertFailures("=,a,b,")

	def testPatternExprs(self):
		"""tests for correct parsing of pattern expresssions.
		"""
		self._assertResults(
			("NGC*", "(== NGC*)"),
			("~NGC*", "(~ NGC (* ))"),
			("~ NGC*", "(~ NGC (* ))"),
			("~NG?*", "(~ NG (? ) (* ))"),
			("~NG[A-Z]*", "(~ NG ([ A-Z) (* ))"),
			("~NG[^A-Za-z]*", "(~ NG ([ ^A-Za-z) (* ))"),
			("~NG[^ -A]*", "(~ NG ([ ^ -A) (* ))"),
		)
	
	def testPatternFailures(self):
		"""tests for rejection of malformed pattern expressions.
		"""
		self._assertFailures("~ [a")
			

class SQLGenerTest(unittest.TestCase):
	"""Tests for SQL fragments making out of simple vizier-like expressions.
	"""
	def testSQLGenerationSimple(self):
		field = gwidgets.InputKey(dest="foo", source="bar", 
			dbtype="vexpr-float")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "8"}, sqlPars),
			"foo = %(foo0)s")
		self.assertEqual(sqlPars["foo0"], 8.0)
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "=8"}, sqlPars),
			"foo = %(foo0)s")
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "!=8"}, sqlPars),
			"NOT (foo = %(foo0)s)")
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "< 8"}, sqlPars),
			"foo < %(foo0)s")

	def testSQLGenerationComplex(self):
		"""Tests for SQL fragments making out of complex vizier-like expressions.
		"""
		field = gwidgets.InputKey(dest="foo", source="bar", 
			dbtype="vexpr-float")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "< 8 | > 15"}, sqlPars),
			"(foo < %(foo0)s) OR (foo > %(foo1)s)")
		self.assertEqual(len(sqlPars), 2)
		self.assertEqual(sqlPars["foo1"], 15)

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "< 8 & > 15"}, sqlPars),
			"(foo < %(foo0)s) AND (foo > %(foo1)s)")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "8, 9, 10"}, sqlPars),
			"foo IN (%(foo0)s, %(foo1)s, %(foo2)s)")
		self.assertEqual(len(sqlPars), 3)

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "8 .. 10"}, sqlPars),
			"foo BETWEEN %(foo0)s AND %(foo1)s")
		self.assertEqual(len(sqlPars), 2)

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "8 +/- 2"}, sqlPars),
			"foo BETWEEN %(foo0)s AND %(foo1)s")
		self.assertEqual(sqlPars["foo1"], 10)

	def testDateSQLGeneration(self):
		"""tests for SQL fragments making for date expressions.
		"""
		field = gwidgets.InputKey(dest="foo", source="bar", 
			dbtype="vexpr-date")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "2001-05-12"}, 
			sqlPars), "foo = %(foo0)s")
		self.assertEqual(sqlPars["foo0"], typeconversion.make_dateTimeFromString(
			"2001-05-12"))

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "< 2001-05-12"}, 
			sqlPars), "foo < %(foo0)s")
		self.assertEqual(sqlPars["foo0"], typeconversion.make_dateTimeFromString(
			"2001-05-12"))

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field, {"bar": "2001-05-12 +/- 2.5"}, 
			sqlPars), 'foo BETWEEN %(foo0)s AND %(foo1)s')
		self.assertEqual(str(sqlPars["foo0"]), "2001-05-09 12:00:00.00")

	def testWithNones(self):
		"""tests for SQL fragments generation with NULL items.
		"""
		field1 = gwidgets.InputKey(dest="foo", source="foo", 
			dbtype="vexpr-float")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": None}, sqlPars),
			None)

	def testPatterns(self):
		"""tests for SQL generation with string patterns.
		"""
		field1 = gwidgets.InputKey(dest="foo", source="foo", dbtype="vexpr-string")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "~star"}, sqlPars),
			"foo ~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], "^star$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "~sta?"}, sqlPars),
			"foo ~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], "^sta.$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "~s*ta?"}, sqlPars),
			"foo ~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], "^s.*ta.$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "=s*ta?"}, sqlPars),
			"foo ~ %(foo0)s")
		self.assertEqual(sqlPars["foo0"], "^s.*ta.$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "~a+b*"}, sqlPars),
			"foo ~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], r"^a\+b.*$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "!a+b\*"}, sqlPars),
			"foo !~ %(foo0)s")
		self.assertEqual(sqlPars["foo0"], r"^a\+b\\.*$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "!~[a-z]"}, sqlPars),
			"foo !~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], r"^[a-z]$")

		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": "!~[a-z]"}, sqlPars),
			"foo !~* %(foo0)s")
		self.assertEqual(sqlPars["foo0"], r"^[a-z]$")


class StringQueryTest(unittest.TestCase):
	"""Tests for string vizier-expressions in a database.
	"""
	def setUp(self):
		config.setDbProfile("test")
		tableDef = testhelpers.getTestTable("vizierstrings")
		tw = sqlsupport.TableWriter(tableDef)
		tw.createTable()
		feed = tw.getFeeder()
		feed({"s": ""})
		feed({"s": "a"})
		feed({"s": "A"})
		feed({"s": "aaab"})
		feed({"s": "baaab"})
		feed({"s": "BAaab"})
		feed({"s": "B*"})
		feed({"s": "X33+4"})
		feed({"s": "a,b"})
		feed({"s": "a|b"})
		feed({"s": r"\it"})
		feed.close()
		tw.finish()
		self.tableName = tableDef.getQName()

	def _runCountTests(self, tests):
		querier = sqlsupport.SimpleQuerier()
		ik = gwidgets.InputKey(source="s", dest="s", dbtype="vexpr-string")
		try:
			for vExpr, numberExpected in tests:
				pars = {}
				query = "SELECT * FROM %s WHERE %s"%(self.tableName,
					vizierexprs.getSQL(ik, {"s": vExpr}, pars))
				res = querier.query(query, pars).fetchall()
				self.assertEqual(len(res), numberExpected,
					"Query %s with parameters %s didn't yield exactly %d result(s).\n"
					"Result is %s."%(
						query, pars, numberExpected, res))
		finally:
			querier.close()

	def testExactMatches(self):
		self._runCountTests([
			("a", 1),
			("== a", 1),
			("!= a", 10),
			("== ", 1),
			("<a", 1),
			("<A", 2),
			("<=A", 3),
			("<=b", 6),
			("<b", 6),
			(">b", 5),
			("== \it", 1),
			("== B*", 1),
			("=~ a", 2),
			("=~ x33+4", 1),
			("=, a,b,a|b", 2),
			("=| a,b,a|b", 0),
			("=| a,b|b", 1),
		])
	
	def testPatternMatches(self):
		self._runCountTests([
			("= a", 1),
			("~ a", 2),
			("~ a", 2),
			("~ X*", 1),
			("~ a*", 5),
			("=*a*", 6),
			("~*+*", 1),
			("~*|*", 1),
			("~\*", 1),
			("!\*", 10),
			("~B*", 3),
			("= B*", 2),
			("~B?", 1),
			("!B?", 10),
			("! *a*", 5),
			("!~*a*", 4),
		])

	def tearDown(self):
		querier = sqlsupport.SimpleQuerier()
		querier.query("DROP TABLE %s CASCADE"%self.tableName)
		querier.commit()


class MatchMatrixTest(unittest.TestCase):

# This matrix is used in the docs for vizier expressions (help_vizier.shtml).
# If you amend it, please update it there as well.
# To turn this into an HTML table, use something like this mess:
# sed -e 's/</\&lt;/g;s/>/\&gt;/g;s/(/<tr><td>/;s/),/<\/td><\/tr>/;s/None//;s/"//g;s/ T/ X/g;s/ F/ \&nbsp;/g;s/,  */<\/td><td>/g' 
	T, F = True, False
	matchMatrix = [
		(None,      "M4e", "M4ep", "m4e", "A4p", "O4p", "M*", "m|a", "x,a", "=x"),
		("M4e",     T,     F,      F,     F,     F,     F,    F,     F,     F),
		("=x",      F,     F,      F,     F,     F,     F,    F,     F,     F),
		("== =x",   F,     F,      F,     F,     F,     F,    F,     F,     T),
		("!= =x",   T,     T,      T,     T,     T,     T,    T,     T,     F),
		("==M4e",   T,     F,      F,     F,     F,     F,    F,     F,     F),
		("=~m4e",   T,     F,      T,     F,     F,     F,    F,     F,     F),
		("=~m4",    F,     F,      F,     F,     F,     F,    F,     F,     F),
		("~*",      T,     T,      T,     T,     T,     T,    T,     T,     T),
		("~m*",     T,     T,      T,     F,     F,     T,    T,     F,     F),
		("M*",      F,     F,      F,     F,     F,     T,    F,     F,     F),
		("!~m*",    F,     F,      F,     T,     T,     F,    F,     T,     T),
		("~*p",     F,     T,      F,     T,     T,     F,    F,     F,     F),
		("!~*p",    T,     F,      T,     F,     F,     T,    T,     T,     T),
		("~?4p",    F,     F,      F,     T,     T,     F,    F,     F,     F),
		("~[MO]4[pe]", T,  F,      T,     F,     T,     F,    F,     F,     F),
		("=[MO]4[pe]", T,  F,      F,     F,     T,     F,    F,     F,     F),
		(">O",      F,     F,      F,     F,     T,     F,    F,     T,     T),
		(">O5",     F,     F,      F,     F,     F,     F,    F,     T,     T),
		(">=m",     T,     T,      T,     F,     T,     T,    T,     T,     T),
		("<m",      F,     F,      F,     T,     F,     F,    F,     F,     F),
		("=|M4e| O4p| x,a", T, F,  F,     F,     T,     F,    F,     T,     F),
		("=,x,a,=x,m|a", F, F,     F,     F,     F,     F,    T,     F,     T),
	]

	def setUp(self):
		config.setDbProfile("test")
		self.tableDef = testhelpers.getTestTable("vizierstrings")
		tw = sqlsupport.TableWriter(self.tableDef)
		tw.createTable()
		feed = tw.getFeeder()
		self.itemsInDb = self.matchMatrix[0][1:]
		for item in self.itemsInDb:
			feed({"s": item})
		feed.close()
		tw.finish()
		self.queryKey = gwidgets.InputKey(source="s", dest="s", dbtype="vexpr-string")

	def _computeTest(self, testLine):
		pars = {}
		query = "SELECT s FROM %s WHERE %s"%(self.tableDef.getQName(),
			vizierexprs.getSQL(self.queryKey, {"s": testLine[0]}, pars))
		expectation = set([item for item, res in 
			zip(self.itemsInDb, testLine[1:]) if res])
		return expectation, query, pars

	def runTest(self):
		querier = sqlsupport.SimpleQuerier()
		try:
			for test in self.matchMatrix[1:]:
				expectation, query, pars = self._computeTest(test)
				res = set([r[0] for r in querier.query(query, pars).fetchall()])
				self.assertEqual(expectation, res, 
					"Query for %s returned wrong set.\n"
					"Got %s, expected %s."%(
						test[0], res, expectation))
		finally:
			querier.close()

	def tearDown(self):
		tw = sqlsupport.TableWriter(self.tableDef)
		tw.dropTable()
		tw.finish()
if __name__=="__main__":
	testhelpers.main(MatchMatrixTest)
