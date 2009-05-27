"""
Tests for STC conversions and conforming.
"""

import math

from gavo import stc
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

	def testFromParallax(self):
		conv = units.getVectorConverter(
			("deg", "deg", "arcsec"), ("deg", "deg", "kpc"))
		self.assertAlmostEqual(conv((2,2,2))[2], 0.0005)
	
	def testToParallax(self):
		conv = units.getVectorConverter(
			("deg", "deg", "m"), ("deg", "deg", "arcmin"))
		self.assertAlmostEqual(conv((0,0,3.0856775813e+16/60.))[2], 1.)

	def testRaises(self):
		self.assertRaisesWithMsg(units.STCUnitError, "One of 'deg' or 'm'"
			" is no valid distance unit", units.getDistConv, ('deg', 'm'))
		self.assertRaisesWithMsg(units.STCUnitError, "One of 'cy' or 'pc'"
			" is no valid time unit", units.getTimeConv, ('cy', 'pc'))


class GenericConverterTest(testhelpers.VerboseTest):
	def testScalars(self):
		self.assertAlmostEqual(units.getBasicConverter("AU", "lyr")(500), 
			0.0079062537044346792)
		self.assertAlmostEqual(units.getBasicConverter("arcmin", "rad")(
			60*57), 0.99483767363676778)
		self.assertAlmostEqual(units.getBasicConverter("yr", "s")(0.1),
			3.155760e6)
		self.assertAlmostEqual(units.getBasicConverter("mm", "GHz")(210),
			1.4275831333333335)

	def testRedshifts(self):
		self.assertAlmostEqual(units.getRedshiftConverter("km", "h", 
			"m", "s")(3.6), 1)

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
			("s",), "km", "h")((1,)), (3.6,))
		self.assertAlmostEqualVector(units.getVelocityConverter(("deg", "deg"),
				("cy", "cy"), "arcsec", "a")((1,2)),  
			(36.000000000000007, 72.000000000000014))
		self.assertAlmostEqualVector(units.getVelocityConverter(("rad",),
			("cy",), "arcsec", "yr")((1,)), (2062.6480624709639,))

	def testRaising(self):
		self.assertRaises(units.STCUnitError, units.getBasicConverter,
			"Mhz", "lyr")
		self.assertRaises(units.STCUnitError, units.getVectorConverter,
			("m", "m"), ("km", "pc", "Mpc"))
		self.assertRaises(units.STCUnitError, units.getVectorConverter,
			("m", "m", "deg"), ("km", "pc", "Hz"))


class WiggleCoercionTest(testhelpers.VerboseTest):
	"""tests for unit coercion of wiggles parsed from STX-C.
	"""
	def _getAST(self, coo):
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x"><SpaceFrame><ICRS/></SpaceFrame>'
			'</AstroCoordSystem>'
			'<AstroCoords coord_system_id="x">'+
			coo+'</AstroCoords></ObservationLocation>')[0]

	def testBasic(self):
		ast = self._getAST('<Position2D unit="deg"><C1>1</C1><C2>2</C2>'
			'<Error2 unit="arcsec"><C1>0.1</C1><C2>0.15</C2></Error2>'
			'<Size2><C1 unit="arcsec">60</C1><C2 unit="arcmin">1</C2></Size2>'
			'<Resolution2Radius unit="rad">0.00001</Resolution2Radius>'
			'</Position2D>')
		pos = ast.place
		self.assertAlmostEqual(pos.value[0], 1)
		self.assertAlmostEqual(pos.error.values[0][0], 2.7777777777777779e-05)
		self.assertAlmostEqual(pos.resolution.radii[0], 0.00057295779513082329)
		self.assertAlmostEqual(pos.size.values[0][1], 0.016666666666666666)

	def testWeirdBase(self):
		ast = self._getAST('<Position2D><C1 unit="arcsec">1</C1>'
			'<C2 unit="rad">2</C2>'
			'<Error2 unit="arcsec"><C1>0.1</C1><C2>0.15</C2></Error2>'
			'<Size2><C1 unit="arcmin">0.1</C1><C2 unit="arcsec">1</C2></Size2>'
			'<Resolution2Radius unit="rad">0.00001</Resolution2Radius>'
			'</Position2D>')
		pos = ast.place
		self.assertAlmostEqual(pos.error.values[0][0], 0.1)
		self.assertAlmostEqual(pos.error.values[0][1], 7.2722052166430391e-07)
		self.assertAlmostEqual(pos.resolution.radii[0], 2.0626480624709638)
		self.assertAlmostEqual(pos.size.values[0][0], 6.0)
		self.assertAlmostEqual(pos.size.values[0][1], 4.8481368110953598e-06)

	def testWithTime(self):
		ast = self._getAST('<Velocity2D><C1 unit="arcsec" vel_time_unit="yr">1'
			'</C1><C2 unit="rad" vel_time_unit="cy">2</C2>'
			'<Error2 unit="arcmin" vel_time_unit="cy"><C1>0.01</C1><C2>0.015</C2>'
			'</Error2>'
			'<Size2><C1 unit="rad" vel_time_unit="s">1</C1>'
			'<C2 unit="arcsec" vel_time_unit="yr">1</C2></Size2>'
			'<Resolution2Radius unit="deg" vel_time_unit="cy">0.00001'
			'</Resolution2Radius>'
			'</Velocity2D>')
		pos = ast.velocity
		self.assertEqual(pos.unit, ('arcsec', 'rad'))
		self.assertEqual(pos.velTimeUnit, ('yr', 'cy'))
		self.assertAlmostEqual(pos.error.values[0][0], 0.006)
		self.assertAlmostEqual(pos.error.values[0][1], 4.3633231299858233e-06)
		self.assertAlmostEqual(pos.size.values[0][0], 6509222249623.3682)

	def testOthersDefaultUnits(self):
		ast = self._getAST('<Time><TimeInstant><ISOTime>2009-03-10T09:56:10'
			'</ISOTime></TimeInstant><Error>2</Error><Resolution unit="h">'
			'0.001</Resolution><Size unit="yr">0.1</Size></Time>'
			'<Spectral unit="Angstrom"><Value>12.0</Value><Error unit="nm">'
			'0.01</Error><Error>0.02</Error></Spectral>'
			'<Redshift><Value>0.1</Value><Error>0.01</Error></Redshift>')
		t = ast.time
		self.assertEqual(t.unit, "s")
		self.assertEqual(t.error.values[0], 2)
		self.assertAlmostEqual(t.resolution.values[0], 3.6)
		self.assertAlmostEqual(t.size.values[0], 3155760.0)
		s = ast.freq
		self.assertEqual(s.unit, "Angstrom")
		self.assertAlmostEqual(s.error.values[0], 0.1)
		self.assertAlmostEqual(s.error.values[1], 0.2)
		r = ast.redshift
		self.assertEqual(r.unit, None)
		self.assertAlmostEqual(r.error.values[0], 0.01)

	def testOthersFunnyUnits(self):
		ast = self._getAST('<Time unit="yr"><TimeInstant>'
			'<ISOTime>2009-03-10T09:56:10'
			'</ISOTime></TimeInstant><Error>0.0001</Error><Resolution unit="d">'
			'1</Resolution><Size unit="cy">0.1</Size></Time>'
			'<Spectral unit="keV"><Value>12.0</Value><Error unit="eV">'
			'0.01</Error><Resolution unit="Hz">200</Resolution></Spectral>'
			'<Redshift unit="pc" vel_time_unit="cy"><Value>0.1</Value>'
			'<Error unit="km" vel_time_unit="s">10</Error></Redshift>')
		t = ast.time
		self.assertEqual(t.unit, "yr")
		self.assertEqual(t.error.values[0], 0.0001)
		self.assertAlmostEqual(t.resolution.values[0], 0.0027378507871321013)
		self.assertAlmostEqual(t.size.values[0], 10.0)
		s = ast.freq
		self.assertEqual(s.unit, "keV")
		self.assertAlmostEqual(s.error.values[0], 1e-5)
		self.assertAlmostEqual(s.resolution.values[0], 8.2713346600000008e-16)
		r = ast.redshift
		self.assertEqual(r.unit, 'pc')
		self.assertAlmostEqual(r.error.values[0], 0.0010227121651092258)


class GeoCoercionTest(testhelpers.VerboseTest):
	"""tests that "dependent" units on Geometries are properly adapted.
	"""
	def _getAST(self, coo):
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x"><SpaceFrame><ICRS/></SpaceFrame>'
			'</AstroCoordSystem>'
			'<AstroCoordArea coord_system_id="x">'+
			coo+'</AstroCoordArea></ObservationLocation>')[0]

	def testCircleDefault(self):
		ast = self._getAST("<Circle><Center><C1>1.5</C1><C2>1.5</C2></Center>"
			'<Radius pos_unit="arcsec">1</Radius></Circle>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.radius, 1/3600.)

	def testCircleCenterUnit(self):
		ast = self._getAST('<Circle><Center unit="km">'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Radius pos_unit="m">1</Radius></Circle>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.radius, 1/1000.)

	def testCircleCompUnit(self):
		ast = self._getAST('<Circle><Center>'
			'<C1 unit="kpc">1.5</C1><C2 unit="kpc">1.5</C2></Center>'
			'<Radius pos_unit="pc">2</Radius></Circle>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.radius, 2/1000.)

	def testCircleGlobalUnit(self):
		ast = self._getAST('<Circle unit="kpc"><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Radius pos_unit="pc">2</Radius></Circle>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.radius, 2/1000.)

	def testEllipse(self):
		ast = self._getAST('<Ellipse unit="kpc"><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<SemiMajorAxis pos_unit="pc">2</SemiMajorAxis>'
			'<SemiMinorAxis pos_unit="lyr">1</SemiMinorAxis>'
			'<PosAngle unit="rad">1</PosAngle>'
			'</Ellipse>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.smajAxis, 2/1000.)
		self.assertAlmostEqual(a.sminAxis, 0.00030660139380459661)
		self.assertAlmostEqual(a.posAngle, 57.295779513082323)

	def testBoxGlobalCoo(self):
		ast = self._getAST('<Box unit="deg"><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Size unit="arcsec"><C1>1</C1><C2>2</C2></Size>'
			'</Box>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.boxsize[0], 1/3600.)
		self.assertAlmostEqual(a.boxsize[1], 2/3600.)

	def testBoxCenterCoo(self):
		ast = self._getAST('<Box><Center unit="deg">'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Size unit="arcsec"><C1>1</C1><C2>2</C2></Size>'
			'</Box>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.boxsize[0], 1/3600.)
		self.assertAlmostEqual(a.boxsize[1], 2/3600.)

	def testBoxCompCoo(self):
		ast = self._getAST('<Box><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Size><C1 unit="arcmin">1</C1><C2 unit="arcsec">2</C2></Size>'
			'</Box>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.boxsize[0], 1/60.)
		self.assertAlmostEqual(a.boxsize[1], 2/3600.)


class UnitConformTest(testhelpers.VerboseTest):
	"""tests for simple unit conforming.
	"""
	def testSimplePos(self):
		ast0 = stc.parseSTCS("Position ICRS 10 12 unit deg Error 0.01 0.01"
			" Spectral 1250 unit MHz")
		ast1 = stc.parseSTCS("Position ICRS unit arcmin Spectral unit GHz")
		res = stc.conformTo(ast0, ast1)
		self.assertEqual(res.place.unit, ("arcmin", "arcmin"))
		self.assertEqual(res.place.value[0], 10*60)
		self.assertEqual(res.place.value[1], 12*60)
		self.assertAlmostEqual(res.place.error.radii[0], 0.6)
		self.assertEqual(res.freq.unit, "GHz")
		self.assertEqual(res.freq.value, 1.25)

	def testAreaConform(self):
		ast0 = stc.parseSTCS("PositionInterval ICRS 9 11 11 13 Position 10 12"
			" RedshiftInterval 1000 2000 Redshift 1500 unit m/s")
		ast1 = stc.parseSTCS("Position ICRS unit arcmin Redshift unit km/s")
		res = stc.conformTo(ast0, ast1)
		self.assertEqual(res.place.value[0], 10*60)
		self.assertEqual(res.areas[0].lowerLimit[0], 9*60)
		self.assertEqual(res.areas[0].upperLimit[1], 13*60)
		self.assertEqual(res.redshiftAs[0].upperLimit, 2)
		self.assertEqual(res.redshift.unit, "km")
		self.assertEqual(res.redshift.velTimeUnit, "s")


class GeometryConformTest(testhelpers.VerboseTest):
	"""tests for conforming of Boxes, Circles and friends.
	"""
	def assertMatchingSTCS(self, srcSTCS, sysSTCS, expected):
		srcAst, sysAst = stc.parseSTCS(srcSTCS), stc.parseSTCS(sysSTCS)
		found = stc.getSTCS(stc.conformTo(srcAst, sysAst))
		self.assertEqual(found, expected)

	def testCircleToGal(self):
		self.assertMatchingSTCS("Circle ICRS 45 -60 1",
			"Position GALACTIC unit rad",
			"Circle GALACTIC 4.85565465308 -0.881494801129 0.0174532925199 unit rad")

	def testCircleFromGal(self):
		self.assertMatchingSTCS(
			"Circle GALACTIC 4.85565465308 -0.881494801129 0.0174532925199 unit rad",
			"Position ICRS",
			"Circle ICRS 44.9999999998 -60.0000000001 0.999999999998")
	
	def testBox(self):
		self.assertMatchingSTCS(
			"Box ICRS 360000 36000 20 30 unit arcsec",
			"Position ECLIPTIC J1950",
			"Polygon ECLIPTIC J1950.0 99.4089149593 -13.1039695064 99.4077016165 -13.0873447912 99.4189071078 -13.0865685226 99.420121778 -13.1031931456")


	def testVelocityNoSystem(self):
		self.assertMatchingSTCS(
			"Position ICRS VelocityInterval 0.1 0.2 unit arcsec/yr",
			"Position ICRS VelocityInterval unit deg/cy",
			"Position ICRS VelocityInterval 0.00277777777778 0.00555555555556 unit"
			" deg/cy")


if __name__=="__main__":
	testhelpers.main(UnitConformTest)
