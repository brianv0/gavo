"""
Tests for STC conversions and conforming.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import math

from gavo.helpers import testhelpers

from gavo import stc
from gavo import utils
from gavo.stc import bboxes
from gavo.stc import units
from gavo.utils import DEG



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
		self.assertRaisesWithMsg(stc.STCUnitError, "One of 'deg' or 'm'"
			" is no valid distance unit", units.getDistConv, ('deg', 'm'))
		self.assertRaisesWithMsg(stc.STCUnitError, "One of 'cy' or 'pc'"
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
		self.assertRaises(stc.STCUnitError, units.getBasicConverter,
			"Mhz", "lyr")
		self.assertRaises(stc.STCUnitError, units.getVectorConverter,
			("m", "m"), ("km", "pc", "Mpc"))
		self.assertRaises(stc.STCUnitError, units.getVectorConverter,
			("m", "m", "deg"), ("km", "pc", "Hz"))


class WiggleCoercionTest(testhelpers.VerboseTest):
	"""tests for unit coercion of wiggles parsed from STX-C.
	"""
	def _getAST(self, coo):
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x"><SpaceFrame><ICRS/></SpaceFrame>'
			'</AstroCoordSystem>'
			'<AstroCoords coord_system_id="x">'+
			coo+'</AstroCoords></ObservationLocation>')[0][1]

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
		ast = self._getAST('<Time unit="s"><TimeInstant>'
			'<ISOTime>2009-03-10T09:56:10'
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
	"""tests for various forms of unit coercion with geometries.
	"""
	def _getAST(self, coo, pos=""):
		if pos:
			pos = '<AstroCoords coord_system_id="x">%s</AstroCoords>'%pos
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x"><SpaceFrame><ICRS/></SpaceFrame>'
			'</AstroCoordSystem>'+pos+
			'<AstroCoordArea coord_system_id="x">'+
			coo+'</AstroCoordArea></ObservationLocation>')[0][1]

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

	def testBoxPositionCoerc(self):
		ast = self._getAST('<Box><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Size><C1 unit="arcmin">1</C1><C2 unit="arcsec">2</C2></Size>'
			'</Box>', 
			'<Position2D><Value2><C1 unit="rad"/><C2 unit="deg"/>'
			'</Value2></Position2D>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.boxsize[0], 1/60.*utils.DEG)
		self.assertAlmostEqual(a.boxsize[1], 2/3600.)
		self.assertAlmostEqual(a.center[0], 1.5*utils.DEG)
		self.assertAlmostEqual(a.center[1], 1.5)
	
	def testCirclePositionCoerc(self):
		ast = self._getAST('<Circle unit="kpc"><Center>'
			'<C1>1.5</C1><C2>1.5</C2></Center>'
			'<Radius pos_unit="pc">2</Radius></Circle>',
			'<Position2D><Value2><C1 unit="m"/><C2 unit="km"/>'
			'</Value2></Position2D>')
		a = ast.areas[0]
		self.assertAlmostEqual(a.center[0]*1e-13, 1.5*units.onePc*1000*1e-13)
		self.assertAlmostEqual(a.center[1]*1e-13, 1.5*units.onePc*1e-13)
		self.assertAlmostEqual(a.radius*1e-13, 2*units.onePc*1e-13)


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


class _STCSMatchTestBase(testhelpers.VerboseTest):
	def assertMatchingSTCS(self, srcSTCS, sysSTCS, expected):
		srcAst, sysAst = stc.parseSTCS(srcSTCS), stc.parseSTCS(sysSTCS)
		found = stc.getSTCS(stc.conformTo(srcAst, sysAst))
		self.assertEqual(found, expected)


class GeometryConformTest(_STCSMatchTestBase):
	"""tests for conforming of Boxes, Circles and friends.
	"""
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


class TimeConformTest(_STCSMatchTestBase):
	def testNoDestSystem(self):
		self.assertMatchingSTCS("Time TT 2005-03-07T16:33:20",
			"Position GALACTIC unit rad",
			"Time TT 2005-03-07T16:33:20")
	
	def testToUTC(self):
		self.assertMatchingSTCS(
			"Time TT 2005-03-07T16:33:20",
			"Time UTC",
			"Time UTC 2005-03-07T16:33:20.184000")

	def testFromUTC(self):
		self.assertMatchingSTCS(
			"Time UTC 2005-03-07T16:33:20.184000",
			"Time TT",
			"Time TT 2005-03-07T16:33:20")

	def testTwostep(self):
		self.assertMatchingSTCS(
			"Time TCB 2005-03-07T16:33:20",
			"Time TAI",
			"Time TAI 2005-03-07T16:31:57.946772")


class HeadingTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		args, expected = sample
		res = bboxes.getHeading(*(a*DEG for a in args))
		self.assertAlmostEqual(res, expected*DEG, 7,
			"%s, %s!=%s"%(args, expected, res/DEG))

	samples = [
		((0, 0, 1, 0), 90.),
		((0, 0, -1, 0), 270.),
		((0, 0, 0, 1), 0.),
		((0, 20, 0, 1), 180.),
		((50, 20, 70, 40), 36.2122360568),
#5
		((50, -20, 70, -40), 180-36.2122360568),
		((100-50, -20, 100-70, -40), 180+36.2122360568),
		((100-50, 20, 100-70, 40), 360-36.2122360568),
		((50, 20, 230, 40), 0),
		((230, 40, 50, 20), 0),
#10
		((230, 90, 50, 20), 180),
		((120, 40, 110, 40), 273.218731205),
		((110, -40, 120, -10), 19.2250728671),
		((110, -40, 150, -30), 85.5408032012),
		((110, -40, 210, -30), 119.355123886),
	]


class GreatCircleSpecialTest(testhelpers.VerboseTest):

	def testLatForLongLat(self):
		gc = bboxes.GCSegment.fromDegrees(20, 60, 130, 60)
		for long, expected in [
				(20, 60),
				(75, 71.677478167328047),
				(130, 60)]:
			self.assertAlmostEqual(gc.latForLong(long*DEG), expected*DEG)

	def testLatForLongMerid(self):
		gc = bboxes.GCSegment.fromDegrees(20, 60, 20, -60)
		self.assertAlmostEqual(gc.latForLong(23*DEG), 20*DEG)

	def testLatForLongOblique(self):
		gc = bboxes.GCSegment.fromDegrees(20, -60, 180, 45)
		for long, expected in [
				(20, -60),
				(75, -68.171528804315329),
				(156.65, -0.0066479410359413316),
				(180, 45)]:
			self.assertAlmostEqual(gc.latForLong(long*DEG), expected*DEG, 7,
				"Bad sample: %f %f"%(long, expected))

	def testNoNull(self):
		self.assertRaisesWithMsg(ValueError,
			"Null segment: start and end are identical",
			bboxes.GCSegment,
			(0.1, 0.3, 0.1, 0.3))

class GreatCircleBboxTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _assertBBox(self, found, expected):
		# lazy: found is in rad, expected in deg
		terminal = [(0,0,0,0)]
		for fb, eb in zip(found+terminal, expected+terminal):
			fb = tuple(f/utils.DEG for f in fb)
			for f, e in zip(fb, eb):
				self.assertAlmostEqual(f, e, 7, "%s!=%s"%(fb, eb))

	def _runTest(self, sample):
		args, expected = sample
		gc = bboxes.GCSegment.fromDegrees(*args)
		self._assertBBox(gc.getBBs(), expected)

	samples = [
		((20, 60, 120, 60), [(20, 60, 120, 69.63942512)]),
		((20, -60, 120, -60), [(20, -69.63942512, 120, -60)]),
		((0, 0, 10, 1), [(0, 0, 10, 1)]),
		((0, -10, 20, 1), [(0, -10, 20, 1)]),
		((20, 30, 100, -1), [(20, -1, 100, 30)]),
# 5
		((110, 40, 160, 20), [(110, 20, 160, 40)]),
		((-10, -40, 40, 20), [
			(0.0, -31.864374833103472, 40.0, 20.0),
			(350.0, -40.0, 360.0, -31.864374833103472)]),
	]


class BboxTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		stcsString, expected = sample
		ast = stc.parseSTCS(stcsString)
		found = list(bboxes.getBboxes(ast))
		self.assertEqual(len(found), len(expected), "Wrong # of bboxes: %s %s"%(
			expected, found))
		for fbb, ebb in zip(found, expected):
			for fc, ec in zip (fbb, ebb):
				self.assertAlmostEqual(fc, ec, 7, "Bad coo:%s %s"%(
					expected, found))

	samples = [
		("Circle ICRS 1.1 -0.2 0.1 unit rad", 
			[(57.295779513082323, -17.188733853924699, 
				68.754935415698796, -5.729577951308233)]),
		("Circle GALACTIC 1.1 -0.2 0.1 unit rad", 
			[(302.43329340145374, 14.559998345530186, 
				313.89244930407017, 26.019154248146652)]),
		("Circle ICRS 40 70 30", [(0, 40.0, 360, 90)]),
		("Circle ICRS 40 70 60", [(0, 10.0, 360, 90)]),
		("Circle ICRS 40 10 60", 
			[(0, -50.0, 100, 70), (340, -50, 360, 70)]),
# 5
		("Circle ICRS 40 90 10", [(0, 80, 360, 90)]),
		("Ellipse ICRS 40 10 60 20 280", 
			[(0, -50.0, 100, 70), (340, -50, 360, 70)]),
		("Box ICRS 90 0 30 30", 
			[(60, -33.690067525979771, 120, 33.690067525979771)]),
		("Box ICRS 0 0 30 30", [
			(0, -33.690067525979771, 30, 33.690067525979771),
			(330, -33.690067525979771, 360, 33.690067525979771)]),
		("Box ICRS 0 -90 20 10", [(0, -90, 360, -80)]),
# 10
		("Box ICRS 0 -89 20 1", [(0, -90, 360, -88)]),
		("Box ICRS 0 89 20 1", [(0, 88, 360, 90)]),
		("AllSky ICRS", [(0, -90, 360, 90)]),
		("Polygon ICRS 0 0 10 3 12 -3", [(0, -3, 12, 3)]),
		("Polygon ICRS 100 30 120 30 122 9 110 -2", 
			[(100, -2, 122, 30.381255142470486)]),
# 15
		("Polygon ICRS -10 30 120 30 122 9 110 -2", [
			(0.0, -2.0, 122, 53.796010254893815), 
			(350.0, 30, 360.0, 38.081479977806467)]),
		("PositionInterval ICRS 90 -90 180 0", [
			(90.0, -90.0, 180.0, 0.0)]),
		("PositionInterval ICRS 180 0", [
			(180, 0, 360, 90)]),
		("PositionInterval ICRS", []),
		("PositionInterval ICRS -10 -10 10 10", [
			(0, -10, 10, 10),
			(350., -10, 360, 10),]),
# 20
		("Union ICRS (Circle 1.1 -0.2 0.1"
			" Box 0 0 0.5235987755982989 0.5235987755982989) unit rad", [
				(57.295779513082323, -17.188733853924699, 
					68.754935415698796, -5.729577951308233),
				(0, -33.690067525979771, 30, 33.690067525979771),
				(330, -33.690067525979771, 360, 33.690067525979771)]),	
		("Intersection ICRS (AllSky Circle 50 0 30)", [
			(20, -30, 80, 30)]),
		("Intersection ICRS (Box 0 0 30 30 AllSky)", [
			(0, -33.690067525979771, 30, 33.690067525979771),
			(330, -33.690067525979771, 360, 33.690067525979771)]),
		("Intersection ICRS (Circle 20 0 30 Union ("
			" Circle 20 10 5 Circle 355 0 10)"
			" AllSky)", [
			(15.0, 5.0, 25.0, 15.0), 
			(0, -10.0, 5.0, 10.0), 
			(350.0, -10.0, 360, 10.0)]),
		("Difference ICRS (Circle 100 30 50 Circle 50 50 70)", [
			(50., -20, 150, 80)]),
		# 25
		("Not ICRS (Circle 180 0 180)", [
			(0, -90, 360, 90)]),
	]

if __name__=="__main__":
	testhelpers.main(BboxTest)
