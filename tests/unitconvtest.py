# -*- coding: iso-8859-1 -*-

"""
Tests for the unit conversion subsystem
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


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
		except base.BadUnit:
			raise AssertionError("%s doesn't parse"%source)

	def _assertFailure(self, sample):
		expr, kind = sample
		if kind=='hard':
			self.assertRaisesVerbose(base.BadUnit,
				unitconv.parseUnit, (expr,), 
				"%s is bad but was accepted"%expr)
		else:
			res = unitconv.parseUnit(expr)
			self.failIf(not res.isUnknown, "%s is bad but was accepted"%expr)


class _AtomicUnitBase(GrammarTest):
# a base class for test on unit_atom
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	
	unitGrammar = base.unitconv.getUnitGrammar.symbols["unit_atom"]
	

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
		("daa", (315576000.0, 's')),
		("da", (3155760.0, 's')),
		("ha", (3155760000.0, 's')),
		("aa", (3.15576e-11, 's')),
#15
		("hyr", (3155760000.0, 's')),
		("dam", (10., 'm')),
		("mm", (1e-3, 'm')),
		("cd", (1, 'cd')),
		("chan", (1, "chan")),
#20
		("ma", (31557.6, 's')),
		("mag", (1., 'mag')),
		("au", (149598000000.0, 'm')),
		("u", (1.6605388600000002e-27, 'kg')),
		("uu", (1.6605388600000002e-33, 'kg')),
#25
		("ua", (31.5576, 's')),
		("Marcsec", (4.84813681109536, 'rad')),
	]


class NotAtomicUnitTest(_AtomicUnitBase):
	def _runTest(self, sample):
		self.assertRaisesWithMsg(base.BadUnit,
			"No Prefixes allowed on "+sample[1:],
			self.unitGrammar.parseString,
			(sample,), parseAll=True)
	
	samples = [
		"dd",
		"aph",
		"kau",
		"ysolLum",
		"Gchan",
		"nvoxel",
		"mmin",
		"fD",
	]


class UnknownUnitTest(GrammarTest):
	def testUnquotedNormalUnit(self):
		res = base.parseUnit("Klodeckel")
		self.assertEqual(res.term.unit.unit, "Klodeckel")
		self.assertEqual(res.isUnknown, True)
	
	def testUnquotedPrefixedUnit(self):
		res = base.parseUnit("klodeckel")
		self.assertEqual(res.term.unit.unit, "lodeckel")
		self.assertEqual(res.term.unit.prefix, "k")
		self.assertEqual(str(res), "klodeckel")
		self.assertEqual(res.isUnknown, True)

	def testQuotedNormalUnit(self):
		res = base.parseUnit("'Klodeckel'")
		self.assertEqual(res.term.unit.unit, "Klodeckel")
		self.assertEqual(str(res), "'Klodeckel'")
		self.assertEqual(res.isUnknown, True)
	
	def testQuotedPrefixedUnit(self):
		res = base.parseUnit("'klodeckel'")
		self.assertEqual(res.term.unit.unit, "klodeckel")
		self.assertEqual(str(res), "'klodeckel'")
		self.assertEqual(res.isUnknown, True)


	def testCombinedUnit(self):
		res = base.parseUnit("4.5 m/(s.kg**2/'klodeckel'**4)")
		self.assertEqual(res.isUnknown, True)


class GoodUnitStringTest(GrammarTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		source, result = sample
#		unitconv.getUnitGrammar.enableDebuggingOutput()
		self._assertParsesTo(source, result)

	samples = [
		("km/s", "km/s"),
		("10 km/s", "10. km/s"),
		("10.5 m.s**-1", "10.5 m.s**-1"),
		("10.5e4 m/s", "1.05e+5 m/s"),
		("kg.m/s**2", "kg.m/s**2"),
# 5
		("mas**(2/3)", "mas**(2/3)"),
		("(mas/yr).m", "mas/yr.m"),
		("mmag/(m**2.s)", "mmag/(m**2.s)"),
		("(am/fs)/((m/s)/(pc/a))", "am/fs/(m/s/(pc/a))"),
		("(km**(3.25)/s**(3.25))/pc", "km**(13/4)/s**(13/4)/pc"),
#10
		("log(Hz)", "log(Hz)"),
		("sqrt(m**2)", "sqrt(m**2)"),
		("(exp(J**(3/2)/m**2)/ln(solMass)).lyr", 
			"exp(J**(3/2)/m**2)/ln(solMass).lyr"),
		("10**-27 J/(s.m**2.Angstrom)", "1.e-27 J/(s.m**2.Angstrom)"),
		("ks**3", "ks**3"),
#15
		("1.4e4 ks**3", "1.4e+4 ks**3"),
		("pixel/s", "pixel/s"),
		("mHz**2.Gs**-3.mmag.mm**3", "mHz**2.Gs**-3.mmag.mm**3"),
		("m**-3", "m**-3"),
		("m**+3", "m**3"),
		("0.1 nm", "0.1 nm"),
		("10 m", "10. m"),
		("10.0m", "10. m"),
	]


class BadUnitStringTest(GrammarTest):
	"""tests for parsing of unit strings.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self._assertFailure(sample)

	samples = [
		("counts-1", "hard"),
		("mas**2/3", "hard"),
		("r7", "hard"),
		("foo", "soft"),
		("a-b", "hard"),
		("+b", "hard"),
		("10e7'm'", "soft"),
		("cd/(ms*zm", "hard"),
		("sin(s)", "soft"),
		("n", "soft"),
		("m *kg", "hard"),
		("m* kg", "hard"),
		("m   . kg", "hard"),
		("m**3/kg/s**2", "hard"),
		("m)s", "hard"),
		("m***3", "hard"),
		("m=s", "hard"),
		("-0.1m", "hard"),
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
			("mas**2/d", (2.72042020128e-22, {"rad": 2, "s": -1})),
#5
			("ks**3/hm**2", (1e5, {'s': 3, 'm': -2})),
			("13 ks**3/hm**2", (1.3e6, {'s': 3, 'm': -2})),
			("log(Yadu**-4)", (-96, {('log', 'adu'): -4})),
			("10**+4 sqrt(log(uadu**-4))", (48989.7948557, {('log', 'adu'): -2})),
			("log(km)", (3, {('log', 'm'): 1})),
			("dam.dm**2", (0.1, {'m': 3})),
			]


class GoodConvFactorTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		example, expected = sample
		res = base.computeConversionFactor(*example)
		self.assertEqualToWithin(res, expected, 1e-10)

	samples = [
		(("m/s", "cm/s"), 100),
		(("10**+4 V/m", "kV/dm"), 1),
		(("arcsec/a", "mas/d"), 2.73785078713),
		(("kHz", "GHz"), 1e-6), 
		(("sqrt(Mm/us)", "m**(0.5).s**(-0.5)"), 1e6),
		(("10e-3 furlong/s", "kurlong/h"), 3.6e-17),
		(("furlong/s", "'urlong'/h"), 3.6e-12),
		(("'furlong'/s", "'furlong'/h"), 3600.),
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
				" [<Column 'col0'>, <Column 'col1'>, <Column 'col2'>]"
				" cannot be satisfied in"
				" [<Column 'col0'>, <Column 'col1'>]",
			base.computeColumnConversions, (self._mCL("km", "s", "arcsec"),
			self._mCL("m", "h")))
		# Ok: Col in old but not in new
		base.computeColumnConversions(self._mCL("km", "s"),
			self._mCL("m", "h", "arcsec"))

	def testWaveNumber(self):
		self.assertAlmostEqual(unitconv.computeConversionFactor("cm**-1", "J"),
			1.986445824e-23)

	def testInverseWaveNumber(self):
		self.assertAlmostEqual(
			unitconv.computeConversionFactor("MeV", "m**-1")*1e-11,
			8.065544005)


class NoGarbargeTest(testhelpers.VerboseTest):
	def testNoGarbage(self):
		md = testhelpers.getMemDiffer(allItems=True)
		foundFactor, foundPowers = unitconv.parseUnit("mas/yr").getSI()
		md = testhelpers.getMemDiffer(allItems=True)
		foundFactor, foundPowers = unitconv.parseUnit("mas/yr").getSI()
		no = md()
		self.assertEqual(len(no), 4)
		

if __name__=="__main__":
	testhelpers.main(ColumnConvTest)
