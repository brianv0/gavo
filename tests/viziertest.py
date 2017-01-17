# -*- coding: iso-8859-1 -*-

"""
Tests for correct interpretation of vizier-type expressions.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import datetime
import sys
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo.protocols import products
from gavo.svcs import vizierexprs
from gavo.svcs import inputdef

import tresc


MS = base.makeStruct


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
			("2003-11-19", "(= 2003-11-19 00:00:00)"),
			("2003-11-19..2003-12-15", 
				"(.. 2003-11-19 00:00:00 2003-12-15 00:00:00)"),
			("2003-11-19 +/- 3", 
				"(.. 2003-11-16 00:00:00 2003-11-22 00:00:00)"),
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


class _SQLGenerTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inValue, expectedSQL, expectedPars = sample
		foundPars = {}
		foundExpr = base.getSQLForField(
			self.protoField, {"foo": inValue}, foundPars)
		self.assertEqual(foundExpr, expectedSQL)
		if expectedPars is not None:
			self.assertEqual(foundPars, expectedPars)


class SimpleNumericSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-float")

	samples = [
		("8", "foo = %(foo0)s", {"foo0": 8.0}),
		("=8", "foo = %(foo0)s", {"foo0": 8.0}),
		("!=8", "NOT (foo = %(foo0)s)", {"foo0": 8.0}),
		("< 8", "foo < %(foo0)s", {"foo0": 8.0}),]


class ComplexNumericSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-float")
	samples =  [
		("< 8 | > 15", "(foo < %(foo0)s) OR (foo > %(foo1)s)",
			{"foo0": 8.0, "foo1": 15}),
		("< 8 & > 15", "(foo < %(foo0)s) AND (foo > %(foo1)s)", None),
		("8, 9, 10", "foo IN (%(foo0)s, %(foo1)s, %(foo2)s)",
			{"foo0": 8.0, "foo1": 9.0, "foo2": 10.0}),
		("8 .. 10", "foo BETWEEN %(foo0)s AND %(foo1)s", None),
		("8 +/- 2", "foo BETWEEN %(foo0)s AND %(foo1)s",
			{"foo0": 6.0, "foo1": 10.0}),]


class DateSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-date")
	samples = [
		("2001-05-12", "foo BETWEEN %(foo0)s AND %(foo1)s", {
				"foo0": datetime.datetime(2001, 5, 12),
				"foo1": datetime.datetime(2001, 5, 12, 23, 59, 59)}),
		("2001-05-12T12:33:14", "foo = %(foo0)s", {
				"foo0": datetime.datetime(2001, 5, 12, 12, 33, 14)}),
		("> 2001-05-12", "foo > %(foo0)s",
			{"foo0": datetime.datetime(2001, 5, 12, 23, 59, 59)}),
		("< 2001-05-12", "foo < %(foo0)s",
			{"foo0": datetime.datetime(2001, 5, 12, 0, 0, 0)}),
		("< 2001-05-12T14:21:12", "foo < %(foo0)s",
			{"foo0": datetime.datetime(2001, 5, 12, 14, 21, 12)}),
		("2001-05-12 +/- 2.5", 'foo BETWEEN %(foo0)s AND %(foo1)s', {
			"foo0": datetime.datetime(2001, 5, 9, 12, 0, 0),
			"foo1": datetime.datetime(2001, 5, 14, 12, 0, 0)}),
		("2001-05-12,2001-05-12T14:21:12", 
			'(foo BETWEEN %(foo0)s AND %(foo1)s) OR (foo = %(foo2)s)', { 
				"foo0": datetime.datetime(2001, 5, 12),
				"foo1": datetime.datetime(2001, 5, 12, 23, 59, 59),
				"foo2": datetime.datetime(2001, 5, 12, 14, 21, 12)}),
		("! 2001-06-07",
			'NOT (foo BETWEEN %(foo0)s AND %(foo1)s)', {
			'foo0': datetime.datetime(2001, 6, 7, 0, 0),
			'foo1': datetime.datetime(2001, 6, 7, 23, 59, 59)}),
		("! 2001-06-07 & >2011-10-20T14:33:10", 
			'(NOT (foo BETWEEN %(foo0)s AND %(foo1)s)) AND (foo > %(foo2)s)', {
				'foo0': datetime.datetime(2001, 6, 7, 0, 0),
				'foo1': datetime.datetime(2001, 6, 7, 23, 59, 59),
				'foo2': datetime.datetime(2011, 10, 20, 14, 33, 10)}),]


class MJDSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-mjd")
	samples = [
		("2001-05-12", "foo BETWEEN %(foo0)s AND %(foo1)s", {
			'foo0': 52041.0, 'foo1': 52041.99998842599}),
		("2001-05-12T12:00:00", "foo = %(foo0)s", {
				"foo0": 52041.5}),
		("> 2001-05-12", "foo > %(foo0)s",
			{"foo0": 52041.99998842599}),
		("< 2001-05-12", "foo < %(foo0)s",
			{"foo0": 52041.0}),
		("< 2001-05-12T18:00:00", "foo < %(foo0)s",
			{"foo0": 52041.75}),
		("2001-05-12 +/- 2.5", 'foo BETWEEN %(foo0)s AND %(foo1)s', {
			'foo0': 52038.5, 'foo1': 52043.5}),
		("2001-05-12,2001-05-12T12:00:00", 
			'(foo BETWEEN %(foo0)s AND %(foo1)s) OR (foo = %(foo2)s)', { 
				'foo0': 52041.0, 
				'foo1': 52041.99998842599, 
				'foo2': 52041.5}),
		("! 2001-06-07",
			'NOT (foo BETWEEN %(foo0)s AND %(foo1)s)', {
			'foo0': 52067.0,
			'foo1': 52067.99998842599}),
		("! 2001-06-07 & >2011-10-20T06:00:00", 
			'(NOT (foo BETWEEN %(foo0)s AND %(foo1)s)) AND (foo > %(foo2)s)', {
				'foo0': 52067.0,
				'foo1': 52067.99998842599,
				'foo2': 55854.25}),]


class NULLSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-float")
	samples = [
		(None, None, {})]


class PatternsSQLGenerTest(_SQLGenerTest):
	protoField = MS(inputdef.InputKey, name="foo", type="vexpr-string")
	samples = [
		("~star", "foo ~* %(foo0)s", {"foo0": "^star$"}),
		("~sta?", "foo ~* %(foo0)s", {"foo0": "^sta.$"}),
		("~s*ta?", "foo ~* %(foo0)s", {"foo0": "^s.*ta.$"}),
		("=s*ta?", "foo ~ %(foo0)s", {"foo0": "^s.*ta.$"}),
		("~a+b*", "foo ~* %(foo0)s", {"foo0": r"^a\+b.*$"}),
		("!a+b\*", "foo !~ %(foo0)s", {"foo0": r"^a\+b\\.*$"}),
		("!~[a-z]", "foo !~* %(foo0)s", {"foo0": r"^[a-z]$"}),
		("!~[a-z]", "foo !~* %(foo0)s", {"foo0": r"^[a-z]$"})]


class _ViztestTable(tresc.RDDataResource):
	dataId = "viziertest"


_viztestTable = _ViztestTable()


class StringQueryTest(testhelpers.VerboseTest):
	"""Tests for string vizier-expressions in a database.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [("testTable", _viztestTable)]
	ik = base.makeStruct(inputdef.InputKey, name="s", type="vexpr-string")

	samples = [
#0
			("a", 1),
			("== a", 1),
			("!= a", 10),
			("== ", 1),
			("<a", 6),
#5
			("<A", 1),
			("<=A", 2),
			("<=b", 10),
			("<b", 10),
			(">b", 1),
#10
			("== \it", 1),
			("== B*", 1),
			("=~ a", 2),
			("=~ x33+4", 1),
			("=, a,b,a|b", 2),
#15
			("=| a,b,a|b", 0),
			("=| a,b|b", 1),
			("= a", 1),
			("~ a", 2),
			("~ a", 2),
#20
			("~ X*", 1),
			("~ a*", 5),
			("=*a*", 6),
			("~*+*", 1),
			("~*|*", 1),
#25
			("~\*", 1),
			("!\*", 10),
			("~B*", 3),
			("= B*", 2),
			("~B?", 1),
#30
			("!B?", 10),
			("! *a*", 5),
			("!~*a*", 4),
		]

	def _runTest(self, sample):
		expr, numberExpected = sample
		pars = {}
		query = "SELECT * FROM %s WHERE %s"%(self.testTable.tableDef.getQName(),
			base.getSQLForField(self.ik, {"s": expr}, pars))
		res = self.testTable.query(query, pars).fetchall()
		self.assertEqual(len(res), numberExpected,
			"Query %s from %r with parameters %s didn't yield exactly"
				" %d result(s).\nResult is %s."%(
				query, expr, pars, numberExpected, res))

# This matrix is used in the docs for vizier expressions (help_vizier.shtml).
# If you amend it, please update it there as well.
# To turn this into an HTML table, use something like this mess:
# sed -e 's/</\&lt;/g;s/>/\&gt;/g;s/(/<tr><td>/;s/),/<\/td><\/tr>/;s/None//;s/"//g;s/ T/ X/g;s/ F/ \&nbsp;/g;s/,  */<\/td><td>/g' 
T, F = True, False
_MATCH_MATRIX = [
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
		(">O",      F,     F,      T,     F,     T,     F,    T,     T,     F),
		(">O5",     F,     F,      T,     F,     F,     F,    T,     T,     F),
		(">=m",     F,     F,      T,     F,     F,     F,    T,     T,     F),
		("<M",      F,     F,      F,     T,     F,     F,    F,     F,     T),
		("=|M4e| O4p| x,a", T, F,  F,     F,     T,     F,    F,     T,     F),
		("=,x,a,=x,m|a", F, F,     F,     F,     F,     F,    T,     F,     T),
	]


class _VizTable(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]

	setUpCost = 4

	def make(self, deps):
		self.conn = deps["conn"]
		dd = testhelpers.getTestRD().getById("viziertest")
		data = rsc.makeData(dd, forceSource="$".join(_MATCH_MATRIX[0][1:]),
			connection=self.conn)
		return data.getPrimaryTable()

	def clean(self, ignored):
		self.conn.rollback()


class MatchMatrixTest(testhelpers.VerboseTest):
	resources = [("testtable", _VizTable())]

	queryKey = MS(inputdef.InputKey, name="s", type="vexpr-string")

	def _computeTest(self, testLine):
		pars = {}
		query = "SELECT s FROM %s WHERE %s"%(self.testtable.tableDef.getQName(),
			base.getSQLForField(self.queryKey, {"s": testLine[0]}, pars))
		expectation = set([item for item, res in 
			zip(_MATCH_MATRIX[0][1:], testLine[1:]) if res])
		return expectation, query, pars

	def runTest(self):
		for test in _MATCH_MATRIX[1:]:
			expectation, query, pars = self._computeTest(test)
			res = set([r[0] for r in self.testtable.query(query, pars).fetchall()])
			self.assertEqual(expectation, res, 
				"Query for %s returned wrong set.\n"
				"Got %s, expected %s."%(
					test[0], res, expectation))


if __name__=="__main__":
	testhelpers.main(StringQueryTest)
