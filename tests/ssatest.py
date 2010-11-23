"""
Some tests around the SSAP infrastructure.
"""

import datetime

from gavo import api
from gavo.base import literals
from gavo.protocols import pql
from gavo.helpers import testhelpers


def getRD():
	return testhelpers.getTestRD("ssatest.rd")


################### PQL tests (put into a test module of their own?


P = pql.PQLRes
PR = pql.PQLRange


class PQLParsesTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, expected = sample
		self.assertEqual(pql.parsePQL(literal, "pqlExpr"), expected)
	
	samples = [
		("foo;something", P([PR("foo")], "something")),
		("foo;something%3bother", P([PR("foo")], "something;other")),
		("foo/bar", P([PR(start="foo", stop="bar")])),
		("foo/bar/quux", P([PR(start="foo", stop="bar", step="quux")])),
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
			pql.parsePQL,
			(literal, "pqlExpr"))

	samples = [
		("foo;something;bother",
			"'foo;something;bother' is not a valid value for pqlExpr"),
		("/bar/quux", "'/bar/quux' is not a valid value for range within pqlExpr"),
		("foo//quux", "'foo//quux' is not a valid value for range within pqlExpr"),
		("//quux", "'//quux' is not a valid value for range within pqlExpr"),
		("//quux/", "'//quux/' is not a valid value for pqlExpr"),
		("/", "'/' is not a valid value for range within pqlExpr"),
	]


class PQLParsedLiteralTest(testhelpers.VerboseTest):
	def testWithIntRanges(self):
		res = pql.parsePQL("10,11/12,50/100/5;schnarch", "pqlExpr",  int)
		self.assertEqual(res, P([PR(value=10), PR(start=11, stop=12),
			PR(None, 50, 100, 5)], "schnarch"))

	def testBadInt(self):
		self.assertRaisesWithMsg(
			api.LiteralParseError,
			"At 3: '11/1u' is not a valid value for range within pqlExpr",
			pql.parsePQL,
			("10,11/1u,50/100/5;schnarch", "pqlExpr",  int))

	def testDateRange(self):
		res = pql.parsePQL("2010-11-01T10:00:00/2010-11-24T15:00:00/0.1", 
			"pqlExpr", literals.parseDefaultDatetime, float)
		self.assertEqual(res, P([PR(
			start=datetime.datetime(2010, 11, 01, 10, 00, 00),
			stop=datetime.datetime(2010, 11, 24, 15, 00, 00),
			step=0.1)]))


class PQLSetValuedTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		literal, expected = sample
		res = pql.parsePQL(literal, "pqlExpr", int)
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
		res = pql.parsePQL(literal, "pqlExpr", int)
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


################### SSA tests proper

class RDTest(testhelpers.VerboseTest):
# tests for some aspects of the ssap rd.
	def testUtypes(self):
		srcTable = getRD().getById("hcdtest")
		self.assertEqual("ssa:Access.Reference",
			srcTable.getColumnByName("accref").utype)

	def testDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_spectralSI").value, 
			"m")

	def testNullDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_creator").value, 
			None)

	def testOverriddenParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_instrument").value, 
			"DaCHS test suite")
	def testNormalizedDescription(self):
		self.failUnless("matches your query" in
			getRD().getById("hcdouttest").getColumnByName("ssa_score"
				).description)
		
if __name__=="__main__":
	testhelpers.main(PQLParsesTest)
