# -*- coding: iso-8859-1 -*-

"""
Tests for the unit conversion subsystem
"""

import sys
import unittest


from gavo import base
from gavo import rscdef
from gavo.base import unitconv
from gavo.helpers import testhelpers


class GrammarTest(testhelpers.VerboseTest):
	def _assertResults(self, *examples):
		for expr, res in examples:
			try:
				self.assertEqual(str(self.unitGrammar.parseString(expr)[0]), res)
			except base.ParseException:
				raise AssertionError("%s doesn't parse"%expr)
			except:
				sys.stderr.write("\nFailed example is %s\n"%expr)
				raise

	def _assertFailures(self, *examples):
		for expr in examples:
			self.assertRaisesVerbose(base.ParseException,
				self.unitGrammar.parseString, (expr,), 
				"%s is bad but was accepted"%expr)


class UnitsStringTest(GrammarTest):
	"""tests for parsing of unit strings.
	"""
	def setUp(self):
		self.unitGrammar = base.unitconv.getUnitGrammar()

	def testExpressions(self):
		"""tests for correct parsing of "good" unit strings.
		"""
		self._assertResults(
			("S", "S"),
			("m", "m"),
			("deg", "deg"),
			("km/s", "1000.0m s-1"),
			("km/10s", "1000.0m 10.0s-1"),
			("ms-1.m", "0.001s-1 m"),
			("mas/yr", "mas yr-1"),
			("mas/yr/m", "mas yr-1 m-1"),
			("mas/yr.m", "mas yr-1 m"),
			("mmag", "0.001mag"),
			("50x10+3yr/m", "50000.0yr m-1"),
			("2.2x10-3V/C", "0.0022V C-1"),
		)

	def testFailures(self):
		"""test for rejction of mailformed unit strings.
		"""
		self._assertFailures("r7",
			"foo",
			"a-b",
			"+b",
			"10e7m",)


class ElementaryUnitTest(GrammarTest):
	"""tests that all elementary units parse correctly.

	This is necessary since there are units like mas that would be
	parsed as <milli><year>*crash*.
	"""
	def setUp(self):
		self.unitGrammar = base.unitconv.getUnitGrammar()

	def testUnits(self):
		self._assertResults(*[(unit, unit) for unit in base.unitconv.units])


class NormalizationTest(unittest.TestCase):
	"""tests for correct normalization of unit expressions.
	"""
	def setUp(self):
		self.unitGrammar = base.unitconv.getUnitGrammar()
	
	def testNormalization(self):
		"""tests for correct normalization of unit expressions.
		"""
		for example, expected in [
				("Mm/s", "1e+06 m s-1"),
				("km/ks", "m s-1"),
				("kpc/yr", "9.77799e+11 m s-1"),
				("mas/d", "5.61127e-14 rad s-1"),
			]:
			res = str(self.unitGrammar.parseString(example)[0].normalize())
			self.assertEqual(res, expected, "Bad normalization of %s, expected %s,"
				" got %s"%(example, expected, res))


class ConvFactorTest(testhelpers.VerboseTest):
	"""tests for the functionality of the getFactor top-level function.
	"""
	def testFactors(self):
		"""tests for factors with valid unit strings.
		"""
		for example, expected in [
				(("m/s", "cm/s"), 100),
				(("1x10+4V/m", "kV/dm"), 1),
				(("arcsec/a", "mas/d"), 2.737851),
				(("kHz", "GHz"), 1e-6),
			]:
			res = base.computeConversionFactor(*example)
			self.assertAlmostEqual(res, expected, 6, msg="getFactor%s yielded %f,"
				" expected %f."%(example, res, expected))

	def testFactorFails(self):
		"""tests for correct exceptions raised for bad unit strings or conversions.
		"""
		for example, exception in [
				(("m7v", "cm/s"), base.BadUnit),
				(("m/ks", "cm..s"), base.BadUnit),
				(("m/s", "V/m"), base.IncompatibleUnits),
				(("arcsec/m", "byte"), base.IncompatibleUnits),
			]:
			self.assertRaisesVerbose(exception, base.computeConversionFactor, example,
				"getFactors%s didn't raise an exception (or raised the wrong"
				" one)")


class ColumnConvTest(testhelpers.VerboseTest):
	"""tests for bulk conversion factor computation.
	"""
	def _mCL(self, *units):
		return rscdef.ColumnList(rscdef.Column(None, name="col%d"%ind, unit=u)
			for ind, u in enumerate(units))

	def testNull(self):
		res = base.computeColumnConversions(self._mCL("m", "s"),
			self._mCL("m", "s"))
		self.assertEqual(res, {})

	def testSimple(self):
		res = base.computeColumnConversions(self._mCL("km", "s"),
			self._mCL("m", "h"))
		self.assertEqual(res, {'col0': 0.001, 'col1': 3600})

	def testRaises(self):
		# Bad: Col in new but not in old.
		self.assertRaisesWithMsg(base.DataError, "Request for column col2 from"
				" [<Column col0>, <Column col1>] cannot be satisfied"
				" in [<Column col0>, <Column col1>, <Column col2>]",
			base.computeColumnConversions, (self._mCL("km", "s", "arcsec"),
			self._mCL("m", "h")))
		# Ok: Col in old but not in new
		base.computeColumnConversions(self._mCL("km", "s"),
			self._mCL("m", "h", "arcsec"))

if __name__=="__main__":
	testhelpers.main(ColumnConvTest)
