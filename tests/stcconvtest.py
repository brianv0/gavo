"""
Tests for STC conversions and conforming.
"""

from gavo.stc import units

import testhelpers

class UnitTest(testhelpers.VerboseTest):
	"""tests for simple unit conversion.
	"""
	def testSpatial(self):
		self.assertAlmostEqual(units.getDistConv("mm", "km")(1), 1e-6)
		self.assertAlmostEqual(units.getDistConv("lyr", "m")(1), 
			9.4607304725808e15, 13)
		self.assertAlmostEqual(units.getDistConv("pc", "AU")(0.00000484813681113),
			1., 10)

	def testAngular(self):
		self.assertAlmostEqual(units.getAngleConv("rad", "deg")(1), 
			57.2957795130823, 13)
		self.assertAlmostEqual(units.getAngleConv("h", "deg")(1), 15.)
		self.assertAlmostEqual(units.getAngleConv("arcsec", "h")(1), 
			1.8518518518518518e-05)

	def testTime(self):
		self.assertAlmostEqual(units.getTimeConv("cy", "s")(1),
			3.15576e9)

	def testFrequency(self):
		self.assertAlmostEqual(units.getFreqConv("eV", "GHz")(1), 
			241798.94566132812)
		self.assertAlmostEqual(units.getFreqConv("MeV", "Hz")(1), 
			2.4179894566132813e+20)
	
	def testSpectral(self):
		self.assertAlmostEqual(units.getSpectralConv("eV", "Angstrom")(4),
			3099.6046858274931)
		self.assertAlmostEqual(units.getSpectralConv("mm", "MHz")(50000),
			5.9958491599999997)

	def testRaises(self):
		self.assertRaisesWithMsg(units.STCUnitError, "One of 'deg' or 'm'"
			" is no valid distance unit", units.getDistConv, ('deg', 'm'))
		self.assertRaisesWithMsg(units.STCUnitError, "One of 'cy' or 'pc'"
			" is no valid time unit", units.getTimeConv, ('cy', 'pc'))


class GenericConverterTest(testhelpers.VerboseTest):
	def testScalars(self):
		self.assertAlmostEqual(units.getScalarConverter("AU", "lyr")(500), 
			0.0079062537044346792)
		self.assertAlmostEqual(units.getScalarConverter("arcmin", "rad")(60*57),
			0.99483767363676778)
		self.assertAlmostEqual(units.getScalarConverter("yr", "s")(0.1),
			3.155760e6)
		self.assertAlmostEqual(units.getScalarConverter("mm", "GHz")(210),
			1.4275831333333335)

	def testRedshifts(self):
		self.assertAlmostEqual(units.getRedshiftConverter("km", "h", 
			("m", "s"))(3.6), 1)

	def testSpatial(self):
		self.assertAlmostEqualVector(
			units.getVectorConverter(("deg", "arcmin"), ("rad", "rad"))((2, 300)),
			(0.034906585039886591, 0.087266462599716474))
		self.assertAlmostEqualVector(
			units.getVectorConverter(("m", "lyr", "deg"), ("km", "pc", "arcsec"))(
					(2100, 6.6, 0.001)),
				(2.1000000000000001, 2.0235691991103377, 3.6000000000000001))

	def testVelocity(self):
		self.assertAlmostEqualVector(units.getVelocityConverter(("m",),
			("s",), ("km", "h"))((1,)), (3.6,))
		self.assertAlmostEqualVector(units.getVelocityConverter(("deg", "deg"),
				("cy", "cy"), ("arcsec", "a"))((1,2)),  
			(36.000000000000007, 72.000000000000014))

	def testRaising(self):
		self.assertRaises(units.STCUnitError, units.getScalarConverter,
			"Mhz", "lyr")
		self.assertRaises(units.STCUnitError, units.getRedshiftConverter,
			"m", "Mhz", ("s"))
		self.assertRaises(units.STCUnitError, units.getVectorConverter,
			("m", "m"), ("km", "pc", "Mpc"))
		self.assertRaises(units.STCUnitError, units.getVectorConverter,
			("m", "m", "deg"), ("km", "pc", "Mpc"))

if __name__=="__main__":
	testhelpers.main(GenericConverterTest)
