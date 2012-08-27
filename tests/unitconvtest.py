# -*- coding: iso-8859-1 -*-

"""
Tests for the unit conversion subsystem
"""

import sys
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import rscdef
from gavo.base import unitconv


class GrammarTest(testhelpers.VerboseTest):
	def _assertParsesTo(self, source, result):
		try:
			tree = unitconv.parseUnit(source)
			self.assertEqual(str(tree), result)
		except base.ParseException:
			raise AssertionError("%s doesn't parse"%source)
		except:
			sys.stderr.write("\nFailed example is %s\n"%source)
			raise

	def _assertFailure(self, expr):
		self.assertRaisesVerbose(base.BadUnit,
			unitconv.parseUnit, (expr,), 
			"%s is bad but was accepted"%expr)


class _AtomicUnitBase(GrammarTest):
# a base class for test on atomicUnit
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	
	unitGrammar = base.unitconv.getUnitGrammar.symbols["atomicUnit"]
	

class AtomicUnitTest(_AtomicUnitBase):
	def _runTest(self, sample):
		source, result = sample
		factor, powers = self.unitGrammar.parseString(
			source, parseAll=True)[0].getSI()
		baseUnit = powers.keys()[0]
		self.failUnless(powers[baseUnit], 1)
		self.failUnless(len(powers.keys()), 1)
		failMsg = "Expected %s, got %s"%(result, (factor, baseUnit))
		self.assertEqual(result[1], baseUnit, failMsg)
		self.assertEqualToWithin(result[0], factor, 1e-10, failMsg)
	
	samples = [
		("s", (1., "s")),
		("m", (1., "m")),
		("deg", (0.017453292519943295, 'rad')),
		("mas", (4.8481368110953602e-09, 'rad')),
		("g", (0.001, "kg")),
#5
		("kg", (1, "kg")),
		("mAngstrom", (1e-13, "m")),
		("uarcsec", (4.8481368110953598e-12, 'rad')),
		("Perg", (100000000.0, 'J')),
		("daadu", (10.0, 'adu')),
#10
		("dadu", (0.1, 'adu')),
		("dad", (864000.0, 's')),
		("da", (3155760.0, 's')),
		("ha", (3155760000.0, 's')),
		("aa", (3.15576e-11, 's')),
#15
		("ad", (8.64e-14, 's')),
		("hyr", (3155760000.0, 's')),
		("dam", (10., 'm')),
		("mm", (1e-3, 'm')),
		("cd", (1, 'cd')),
#20
		("chan", (1, "chan")),
		("ch", (36, "s")),
		("ysolMass", (1989000, 'kg')),
		("ma", (31557.6, 's')),
		("mag", (1., 'mag')),
	]


class NotAtomicUnitTest(_AtomicUnitBase):
	def _runTest(self, sample):
		self.assertRaises(base.ParseException,
			self.unitGrammar.parseString,
			sample, parseAll=True)
	
	samples = [
		"k m",
		"mmm",
	]


class GoodUnitStringTest(GrammarTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		source, result = sample
#		unitconv.getUnitGrammar.enableDebuggingOutput()
		self._assertParsesTo(source, result)

	samples = [
		("km/s", "km/s"),
		("10 km/s", "10. km/s"),
		("10.5 m s-1", "10.5 m s-1"),
		("10.5 10+4 m/s", "1.05 10+5 m/s"),
		("kg*m/s2", "(kg m)/s2"),
# 5
		("mas**(2/3)", "mas**(2/3)"),
		("mas/yr.m", "(mas/yr) m"),
		("mmag/(m2 s)", "mmag/(m2 s)"),
		("(am/fs)/((m/s)/(pc/a))", "(am/fs)/((m/s)/(pc/a))"),
		("(km^(3.25)/s^(3.25))/pc", "(km**(13/4)/s**(13/4))/pc"),
#10
		("log(Hz)", "log(Hz)"),
		("sqrt(m2)", "sqrt(m2)"),
		("exp(J^(3/2)/m2)/ln(solMass).lyr", "(exp(J**(3/2)/m2)/ln(solMass)) lyr"),
	]


class BadUnitStringTest(GrammarTest):
	"""tests for parsing of unit strings.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self._assertFailure(sample)

	samples = [
		"10.2m",
		"counts-1",
		"mas2/3",
		"r7",
		"foo",
		"a-b",
		"+b",
		"10e7m",
		"cd/(ms*zm",
		"ks**3",
		"ks^3",
		"sin(s)",
		"exp(s)^(3/2)",
	]


class GetSITest(testhelpers.VerboseTest):
	"""tests for obtaining SI factors for units
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		"""tests for correct normalization of unit expressions.
		"""
		unitString, (exFactor, exPowers) = sample
		foundFactor, foundPowers = unitconv.parseUnit(unitString).getSI()
		self.assertEqualToWithin(exFactor, foundFactor, 1e-10)
		self.assertEqual(exPowers, foundPowers)

	samples = [
			("Mm/s", (1e+06, {"m": 1, "s": -1})),
			("km/ks", (1, {"m": 1, "s": -1})),
			("kpc/yr", (977799325677.0, {"m": 1, "s": -1})),
			("mas/d", (5.61126945729e-14, {"rad": 1, "s": -1})),
			("mas2/d", (2.72042020128e-22, {"rad": 2, "s": -1})),
#5
			("ks3/hm2", (1e5, {'s': 3, 'm': -2})),
			("13 ks3/hm2", (1.3e6, {'s': 3, 'm': -2})),
			("log(Yadu-4)", (-96, {('log', 'adu'): -4})),
			("10+4 sqrt(log(uadu-4))", (48989.7948557, {('log', 'adu'): -2})),
			("log(km)", (3, {('log', 'm'): 1})),
			]


class GoodConvFactorTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		example, expected = sample
		res = base.computeConversionFactor(*example)
		self.assertEqualToWithin(res, expected, 1e-10)

	samples = [
		(("m/s", "cm/s"), 100),
		(("1 10+4 V/m", "kV/dm"), 1),
		(("arcsec/a", "mas/d"), 2.73785078713),
		(("kHz", "GHz"), 1e-6), 
		(("sqrt(Mm/us)", "m^(0.5) s**(-0.5)"), 1e6),
	]


class BadConvFactorTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		example, excType = sample
		self.assertRaisesVerbose(excType, 
			base.computeConversionFactor, example,
			"getFactors%s didn't raise an exception (or raised the wrong"
			" one)")

	samples = [
		(("m7v", "cm/s"), base.BadUnit),
		(("m/ks", "cm..s"), base.BadUnit),
		(("m/s", "V/m"), base.IncompatibleUnits),
		(("arcsec/m", "byte"), base.IncompatibleUnits),
		(("log(Mm/us)", "log(m/s)"), base.IncompatibleUnits),
		]


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
				" [<Column 'col0'>, <Column 'col1'>] cannot be satisfied"
				" in [<Column 'col0'>, <Column 'col1'>, <Column 'col2'>]",
			base.computeColumnConversions, (self._mCL("km", "s", "arcsec"),
			self._mCL("m", "h")))
		# Ok: Col in old but not in new
		base.computeColumnConversions(self._mCL("km", "s"),
			self._mCL("m", "h", "arcsec"))


if __name__=="__main__":
	testhelpers.main(ColumnConvTest)
