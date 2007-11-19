# -*- coding: iso-8859-1 -*-

"""
Tests for correct interpretation of vizier-type expressions.
"""

import unittest
import testhelpers

from gavo import datadef
from gavo.parsing import typeconversion
from gavo.web import vizierexprs


class GrammarTest(testhelpers.VerboseTest):
	def _assertResults(self, *examples):
		for expr, res in examples:
			try:
				self.assertEqual(str(self.parse(expr)), res)
			except vizierexprs.ParseException:
				raise AssertionError("%s doesn't parse"%expr)

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
				("1", "(= 1.0)"),
				("> 1", "(> 1.0)"),
				(">1", "(> 1.0)"),
				(">=1", "(>= 1.0)"),
				("!=1", "(NOT (= 1.0))"),  # This one's complex in our implementation
				("<1", "(< 1.0)"),
				("<=1", "(<= 1.0)"),
			)

	def testMalformedSimpleExprs(self):
		"""tests for rejection of malformed simple expressions
		"""
		self._assertFailures("a1", "< x", "12ea")
	
	def testRanges(self):
		"""tests for correct parsing of ranges
		"""
		self._assertResults(
				("1 .. 2", "(.. 1.0 2.0)"),
				("1. .. 2", "(.. 1.0 2.0)"),
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
				("1 +/- 2", "(.. -1.0 3.0)"),
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
			("1,2", "(, 1.0 2.0)"),
			("1,2,3", "(, 1.0 2.0 3.0)"),
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
			("! 1", "(NOT (= 1.0))"),
			("! = 1", "(NOT (= 1.0))"),
			("! 1 .. 2", "(NOT (.. 1.0 2.0))"),
			("! < 1", "(NOT (< 1.0))"),
			("!>=1", "(NOT (>= 1.0))"),
		)
	
	def testSimpleNotFailures(self):
		"""tests for rejection of malformed simple not expressions.
		"""
		self._assertFailures("!", "!!", "!a")

	def testSimpleAnds(self):
		"""tests for simple and expressions.
		"""
		self._assertResults(
			(">1 & <3", "(AND (> 1.0) (< 3.0))"),
			("1 .. 2 & 1.5 +/- 0.5", "(AND (.. 1.0 2.0) (.. 1.0 2.0))"),
		)

	def testSimpleAndFailures(self):
		"""tests for rejection of malformed and expressions.
		"""
		self._assertFailures("&", "1 &", "& 1", "2 .. & 3")
	
	def testSimpeOrs(self):
		"""tests for simple or expressions.
		"""
		self._assertResults(
			(">1 | <3", "(OR (> 1.0) (< 3.0))"),
			("1 .. 2 | 1.5 +/- 0.5", "(OR (.. 1.0 2.0) (.. 1.0 2.0))"),
		)

	def testSimpleOrFailures(self):
		"""tests for rejection of malformed or expressions.
		"""
		self._assertFailures("|", "1 |", "| 1", "2 .. | 3")
	
	def testComplexLogic(self):
		"""tests for (unspecified by vizier) nested logic.
		"""
		self._assertResults(
			("! 1 & 2", "(AND (NOT (= 1.0)) (= 2.0))"),
			("! 1 & 2 | < 0", "(OR (AND (NOT (= 1.0)) (= 2.0)) (< 0.0))"),
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


class SQLGenerTest(unittest.TestCase):
	"""Tests for SQL fragments making out of simple vizier-like expressions.
	"""
	def testSQLGenerationSimple(self):
		field = datadef.DataField(dest="foo", source="bar")
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
		field = datadef.DataField(dest="foo", source="bar")
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
		field = datadef.DataField(dest="foo", source="bar", dbtype="date")
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

	def testWithNones(self):
		"""tests for SQL fragments generation with NULL items.
		"""
		field1 = datadef.DataField(dest="foo", source="foo")
		sqlPars = {}
		self.assertEqual(vizierexprs.getSQL(field1, {"foo": None}, sqlPars),
			None)


if __name__=="__main__":
	unittest.main()

