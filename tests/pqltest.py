"""
Tests for "PQL" expressions.
"""

import datetime

from gavo.helpers import testhelpers

from gavo import api
from gavo.base import literals
from gavo.svcs import pql
from gavo.utils import pgsphere, DEG



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
		self.assertRaisesWithMsg(api.ValidationError,
			"Ranges not allowed as cone centers",
			pql.PQLPositionPar.fromLiteral("12,12/14", "POS").getConeSQL,
			("POS", {}, 0.1))

	def testRequiresTwo(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"PQL position values must be lists of length divisible by 2.",
			pql.PQLPositionPar.fromLiteral("12", "POS").getConeSQL,
			("POS", {}, 0.1))
	
	def testWhackoFrameRejected(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Cannot match against coordinates given in WHACKO frame",
			pql.PQLPositionPar.fromLiteral("12,13;WHACKO", "POS").getConeSQL,
			("POS", {}, 0.1))
	
	def testSingleCone(self):
		cs = pql.PQLPositionPar.fromLiteral("8,12", "POS")
		pars = {}
		expr = cs.getConeSQL("loc", pars, 0.5)
		self.assertEqual(expr, "(loc <-> %(pos0)s < %(size0)s)")
		self.assertEqual(pars, {'size0': 0.5*DEG, 
			'pos0': pgsphere.SPoint.fromDegrees(8.0, 12.0)})
		
	def testMultiCone(self):
		cs = pql.PQLPositionPar.fromLiteral("10,12,-10,13", "POS")
		pars = {}
		expr = cs.getConeSQL("loc", pars, 0.5)
		self.assertEqual(expr, "(loc <-> %(pos0)s < %(size0)s"
			" OR loc <-> %(pos1)s < %(size0)s)")
		self.assertEqual(pars, {'size0': 0.5*DEG, 
			'pos0': pgsphere.SPoint.fromDegrees(10.0, 12.0),
			'pos1': pgsphere.SPoint.fromDegrees(-10.0, 13.0)})


class PQLFloatTest(testhelpers.VerboseTest):
	def testNoStep(self):
		self.assertRaisesWithMsg(api.LiteralParseError,
			"'1/5/0.5' is not a valid value for range within VAL",
			pql.PQLFloatPar.fromLiteral,
			("1/5/0.5", "VAL"))
	
	def testSimple(self):
		cs = pql.PQLFloatPar.fromLiteral("0.5,4/6", "quack")
		pars = {}
		expr = cs.getSQL("val", pars)
		self.assertEqual(expr, 
			"(val = %(val0)s OR val BETWEEN %(val1)s AND %(val2)s )")
		self.assertEqual(pars, {'val2': 6.0, 'val1': 4.0, 'val0': 0.5})
	
	def testIntervalSQL(self):
		cs = pql.PQLFloatPar.fromLiteral("/-0.5,0,2/4,7/", "quack")
		pars = {}
		expr = cs.getSQLForInterval("lower", "upper", pars)
		self.assertEqual(expr, '((%(val0)s>lower)' 
			' OR %(val1)s BETWEEN lower AND upper'
			' OR (%(val2)s>lower AND %(val3)s<upper)'
			' OR (%(val4)s<upper))')
		self.assertEqual(pars, {"val0": -0.5,
			"val1": 0.,
			"val2": 4.0,
			"val3": 2.0,
			"val4": 7.})


class PQLIRTest(testhelpers.VerboseTest):
	def testBasic(self):
		cs = pql.PQLTextParIR.fromLiteral("abc ef", "foo")
		sqlPars = {}
		sql = cs.getSQL("foo", sqlPars)
		self.assertEqual(sql, "(to_tsvector(foo) @@ plainto_tsquery(%(foo0)s))")
		self.assertEqual(sqlPars, {'foo0': 'abc ef'})
	
	def testEnumeration(self):
		cs = pql.PQLTextParIR.fromLiteral("abc ef, urgl", "foo")
		sqlPars = {}
		sql = cs.getSQL("foo", sqlPars)
		self.assertEqual(sql, "(to_tsvector(foo) @@ plainto_tsquery(%(foo0)s)"
			" OR to_tsvector(foo) @@ plainto_tsquery(%(foo1)s))")
		self.assertEqual(sqlPars, {"foo0": " urgl", 'foo1': 'abc ef'})
	
	def testNoRange(self):
		cs = pql.PQLTextParIR.fromLiteral("abc ef/urgl", "foo")
		self.assertRaisesWithMsg(api.LiteralParseError,
			"'abc%20ef/urgl/' is not a valid value for foo",
			cs.getSQL,
			("foo", {}))


if __name__=="__main__":
	testhelpers.main(PQLIRTest)

