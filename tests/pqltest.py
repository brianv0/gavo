"""
Tests for "PQL" expressions.
"""

import datetime

from gavo import api
from gavo.base import literals
from gavo.helpers import testhelpers
from gavo.protocols import pql
from gavo.utils import pgsphere



P = pql.PQLPar
PR = pql.PQLRange


class PQLParsesTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, expected = sample
		self.assertEqual(pql.PQLPar.fromLiteral(literal, "pqlExpr"), expected)
	
	samples = [
		("foo;something", P([PR("foo")], "something")),
		("foo;something%3bother", P([PR("foo")], "something;other")),
		("foo/bar", P([PR(start="foo", stop="bar")])),
		("", P([PR(value="")])),
		(",a", P([PR(value=""), PR(value="a")])),
		("a,", P([PR(value="a"), PR(value="")])),
		("foo/", P([PR(start="foo")])),
		("/foo", P([PR(stop="foo")])),
		("bar/,/foo", P([PR(start="bar"), PR(stop="foo")])),
		("u,bar/,/foo", P([PR(value="u"), PR(start="bar"), PR(stop="foo")])),
		("a,b,c", P([PR(value="a"), PR(value="b"), PR(value="c")])),
		("%2f,%2c,%3b", P([PR(value="/"), PR(value=","), PR(value=";")])),
	]


class PQLLiteralParseErrorsTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, msg = sample
		self.assertRaisesWithMsg(api.LiteralParseError,
			msg,
			pql.PQLPar.fromLiteral,
			(literal, "pqlExpr"))

	samples = [
		("foo;something;bother",
			"'foo;something;bother' is not a valid value for pqlExpr"),
		("/bar/quux", "'/bar/quux' is not a valid value for range within pqlExpr"),
		("foo/bar/quux", 
			"'foo/bar/quux' is not a valid value for range within pqlExpr"),
		("foo//quux", "'foo//quux' is not a valid value for range within pqlExpr"),
		("//quux", "'//quux' is not a valid value for range within pqlExpr"),
		("//quux/", "'//quux/' is not a valid value for pqlExpr"),
		("/", "'/' is not a valid value for range within pqlExpr"),
	]


class PQLParsedLiteralTest(testhelpers.VerboseTest):
	def testWithIntRanges(self):
		res = pql.PQLIntPar.fromLiteral("10,11/12,50/100/5;schnarch", "pqlExpr")
		self.assertEqual(res, P([PR(value=10), PR(start=11, stop=12),
			PR(None, 50, 100, 5)], "schnarch"))

	def testBadInt(self):
		self.assertRaisesWithMsg(
			api.LiteralParseError,
			"At 3: '11/1u' is not a valid value for range within pqlExpr",
			pql.PQLIntPar.fromLiteral,
			("10,11/1u,50/100/5;schnarch", "pqlExpr"))

	def testDateRange(self):
		res = pql.PQLDatePar.fromLiteral(
			"2010-11-01T10:00:00/2010-11-24T15:00:00/0.5", 
			"pqlExpr")
		self.assertEqual(res, P([PR(
			start=datetime.datetime(2010, 11, 01, 10, 00, 00),
			stop=datetime.datetime(2010, 11, 24, 15, 00, 00),
			step=datetime.timedelta(days=0.5))]))


class PQLSetValuedTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, expected = sample
		res = pql.PQLIntPar.fromLiteral(literal, "pqlExpr")
		if expected is None:
			self.assertRaises(ValueError, res.getValuesAsSet)
		else:
			self.assertEqual(res.getValuesAsSet(), expected)
	
	samples = [
		("1", set([1])),
		("1/3", None),
		("/4", None),
		("3/", None),
		("1/2/1", set([1,2])),
		("1/2/1;norks", set([1,2])),
		("1/2;norks", None),]


class PQLClausesTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, expected, expectedPars = sample
		res = pql.PQLIntPar.fromLiteral(literal, "pqlExpr")
		pars = {}
		expr = res.getSQL("foo", pars)
		self.assertEqual(expr, expected)
		self.assertEqual(pars, expectedPars)

	samples = [
		("1", "foo = %(foo0)s", {"foo0": 1}),
		("1/3/1", "foo IN %(foo0)s", {"foo0": set([1,2,3])}),
		("1/9/3", "foo IN %(foo0)s", {"foo0": set([1,4,7])}),
		("0,1/9/3,1/3/1", "foo IN %(foo0)s", {"foo0": set([0,1,2,3,4,7])}),
		("/0,1/9/3,1/3/1", 
			"(foo <= %(foo0)s OR foo IN %(foo1)s OR foo IN %(foo2)s)", 
			{"foo0": 0, "foo1": set([1,4,7]), "foo2": set([1,2,3])}),
		("1/", "foo >= %(foo0)s", {"foo0": 1}),
		("/1", "foo <= %(foo0)s", {"foo0": 1}),
	]


class PQLPositionsTest(testhelpers.VerboseTest):
	def testNoStep(self):
		self.assertRaisesWithMsg(api.LiteralParseError,
			"'12%2c12/14%2c13/1' is not a valid value for range within POS",
			pql.PQLPositionPar.fromLiteral,
			("12%2c12/14%2c13/1", "POS"))
	
	def testSingleCone(self):
		cs = pql.PQLPositionPar.fromLiteral("10%2c12", "POS")
		pars = {}
		expr = cs.getConeSQL("loc", pars, 0.5)
		self.assertEqual(expr, "loc <-> %(pos0)s < %(size0)s")
		self.assertEqual(pars, {'size0': 0.5, 
			'pos0': pgsphere.SPoint(10.0, 12.0)})
		
	def testMultiCone(self):
		cs = pql.PQLPositionPar.fromLiteral("10%2c12,-10%2c13", "POS")
		pars = {}
		expr = cs.getConeSQL("loc", pars, 0.5)
		self.assertEqual(expr, "(loc <-> %(pos0)s < %(size0)s"
			" OR loc <-> %(pos1)s < %(size0)s)")
		self.assertEqual(pars, {'size0': 0.5, 
			'pos0': pgsphere.SPoint(10.0, 12.0),
			'pos1': pgsphere.SPoint(-10.0, 13.0)})


if __name__=="__main__":
	testhelpers.main(PQLParsesTest)

