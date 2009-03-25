"""
Tests for handling ivoa stc specifications.
"""

import datetime
import unittest

from gavo import stc
from gavo.stc import dm
from gavo.stc import stcs
from gavo.stc import stcsast
from gavo.stc import stcx

import testhelpers

class CoordSysTest(testhelpers.VerboseTest):
	def testBasic(self):
		cs = dm.CoordSys(name="testCase", ucd="test;useless")
		self.assertEqual(cs.timeFrame, None)
		self.assertEqual(cs.ucd, "test;useless")
		self.assertEqual(cs.name, "testCase")

	def testBasicRaises(self):
		self.assertRaises(TypeError, dm.CoordSys, x=8)

	def testFromSTCS(self):
		cst = stcs.getCST("TimeInterval TT BARYCENTER"
			" PositionInterval FK5 TOPOCENTER"
			" SpectralInterval GEOCENTER"
			" RedshiftInterval HELIOCENTER VELOCITY")
		cs = stcsast.getCoordSys(cst)[1]
		self.assertEqual(cs.redshiftFrame.dopplerDef, "OPTICAL")
		self.assertEqual(cs.spectralFrame.refPos.standardOrigin, "GEOCENTER")
		self.assertEqual(cs.spaceFrame.flavor, "SPHERICAL")
		self.assertEqual(cs.spaceFrame.nDim, 2)
		self.assertEqual(cs.spaceFrame.refFrame, "FK5")
		self.assertEqual(cs.timeFrame.timeScale, "TT")

	def testEquinoxes(self):
		ast = stcsast.parseSTCS("Position FK4 B1975 30 30")
		self.assertEqual(ast.astroSystem.spaceFrame.equinox, "B1975.0")
		self.assertEqual(ast.astroSystem.spaceFrame.getEquinox(),
			datetime.datetime(1974, 12, 31, 23, 28, 56, 228856))


class OtherCoordTest(testhelpers.VerboseTest):
	def testSimpleTime(self):
		ast = stcsast.parseSTCS("Time TT 2000-12-20T23:02:12 unit yr Error 2")
		self.assertEqual(ast.times[0].frame.timeScale, "TT")
		self.assertEqual(ast.times[0].error.values, (2.0,))
		self.assertEqual(ast.times[0].value, 
			datetime.datetime(2000, 12, 20, 23, 2, 12))
		
	def testSimpleSpectral(self):
		ast = stcsast.parseSTCS("Spectral BARYCENTER 23 Resolution 0.25 0.5")
		self.assertEqual(ast.freqs[0].frame.refPos.standardOrigin, "BARYCENTER")
		self.assertEqual(ast.freqs[0].value, 23.)
		self.assertEqual(ast.freqs[0].resolution.values, (0.25, 0.5))

	def testSimpleRedshift(self):
		ast = stcsast.parseSTCS("Redshift BARYCENTER 2 unit km/s")
		self.assertEqual(ast.redshifts[0].frame.refPos.standardOrigin, 
			"BARYCENTER")
		self.assertEqual(ast.redshifts[0].value, 2.)

	def testComplexRedshift(self):
		ast = stcsast.parseSTCS("Redshift BARYCENTER 2 REDSHIFT"
			" RADIO Error 0 0.125")
		self.assertEqual(ast.redshifts[0].error.values, (0, 0.125))
		self.assertEqual(ast.redshifts[0].frame.type, "REDSHIFT")
		self.assertEqual(ast.redshifts[0].frame.dopplerDef, "RADIO")

	def testRaising(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Time TT Error 1 2 3")
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Spectral BARYCENTER 23 Resolution 0.25 0.5 2.5")


class SpaceCoordTest(testhelpers.VerboseTest):
	def testSimple(self):
		ast = stcsast.parseSTCS("Position FK5 TOPOCENTER 2 4.25 unit deg"
			" PixSize 4.5 3.75")
		self.assertEqual(ast.places[0].frame.flavor, "SPHERICAL")
		self.assertEqual(ast.places[0].frame.nDim, 2)
		self.assertEqual(ast.places[0].value, (2., 4.25))
		self.assertEqual(ast.places[0].units, ("deg", "deg"))
		self.assertEqual(ast.places[0].pixSize.values, ((4.5, 3.75),))
	
	def testPixSizeRange(self):
		ast = stcsast.parseSTCS("Position FK5 TOPOCENTER 2 4.25 unit deg"
			" PixSize 4.5 3.75 1 5")
		self.assertEqual(ast.places[0].pixSize.values, ((4.5, 3.75), (1., 5.)))

	def testSizeRange(self):
		ast = stcsast.parseSTCS("Position FK5 TOPOCENTER 2 4.25 unit deg"
			" Size 4.5 3.75 1 5")
		self.assertEqual(ast.places[0].size.values, ((4.5, 3.75), (1., 5.)))

	def testRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Position FK5 TOPOCENTER 2 4.25 unit deg PixSize 4.5 3.75 2")


class OtherCoordIntervalTest(testhelpers.VerboseTest):
	def testEmptyInterval(self):
		ast = stcsast.parseSTCS("TimeInterval TOPOCENTER unit s")
		self.assertEqual(ast.timeAs[0].frame.refPos.standardOrigin, 
			"TOPOCENTER")
		self.assertEqual(ast.timeAs[0].upperLimit, None)
		self.assertEqual(ast.timeAs[0].lowerLimit, None)

	def testHalfOpenInterval(self):
		ast = stcsast.parseSTCS("TimeInterval MJD 2000")
		self.assertEqual(ast.timeAs[0].upperLimit, None)
		self.assertEqual(ast.timeAs[0].lowerLimit, 
			datetime.datetime(1864, 5, 9, 0, 0, 0, 1))

	def testOneInterval(self):
		ast = stcsast.parseSTCS("TimeInterval 2000-02-02 2000-02-02T13:20:33")
		self.assertEqual(ast.timeAs[0].upperLimit, 
			datetime.datetime(2000, 2, 2, 13, 20, 33))
		self.assertEqual(ast.timeAs[0].lowerLimit, 
			 datetime.datetime(2000, 2, 2, 0, 0))

	def _testOneAndAHalfInterval(self):
		ast = stcsast.parseSTCS("TimeInterval 2000-02-02 2000-02-02T13:20:33"
			" MJD 80002")
		self.assertEqual(ast.timeAs[1].upperLimit, None)
		self.assertEqual(ast.timeAs[1].lowerLimit, 
			 datetime.datetime(2077, 11, 30, 0, 0, 0, 4))

	def testTimeWithPosition(self):
		ast = stcsast.parseSTCS("TimeInterval 2000-02-02 2000-02-02T13:20:33"
			" Time 2000-02-02T10:34:03.25")
		self.assertEqual(len(ast.timeAs), 1)
		self.assertEqual(len(ast.times), 1)
		self.assertEqual(ast.times[0].value, 
			datetime.datetime(2000, 2, 2, 10, 34, 3, 250000))

	def testSpecInterval(self):
		ast = stcsast.parseSTCS("SpectralInterval 23 45 unit Hz")
		self.assertEqual(len(ast.freqAs), 1)
		self.assertEqual(ast.freqAs[0].frame.refPos.standardOrigin,
			"UNKNOWNRefPos")
		self.assertEqual(ast.freqAs[0].lowerLimit, 23.0)
		self.assertEqual(ast.freqAs[0].upperLimit, 45.0)
		self.assertEqual(ast.freqAs[0].unit, "Hz")

	def testRedshiftInterval(self):
		ast = stcsast.parseSTCS("RedshiftInterval REDSHIFT 2 4")
		self.assertEqual(len(ast.redshiftAs), 1)
		self.assertEqual(ast.redshiftAs[0].frame.type,
			"REDSHIFT")
		self.assertEqual(ast.redshiftAs[0].lowerLimit, 2.0)
		self.assertEqual(ast.redshiftAs[0].upperLimit, 4.0)

	def testStartTime(self):
		ast = stcsast.parseSTCS("StartTime TT MJD24000.5")
		self.assertEqual(len(ast.timeAs), 1)
		self.assertEqual(ast.timeAs[0].upperLimit, None)
		self.assertEqual(ast.timeAs[0].lowerLimit, 
			datetime.datetime(1924, 8, 3, 12, 0))

	def testStopTime(self):
		ast = stcsast.parseSTCS("StopTime TT MJD24000.5")
		self.assertEqual(len(ast.timeAs), 1)
		self.assertEqual(ast.timeAs[0].lowerLimit, None)
		self.assertEqual(ast.timeAs[0].upperLimit, 
			datetime.datetime(1924, 8, 3, 12, 0))


class SpaceCoordIntervalTest(testhelpers.VerboseTest):
	def testSimple2D(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 12.25 23.75 13.5 25.0")
		self.assertEqual(ast.areas[0].frame.refPos.standardOrigin, 
			"UNKNOWNRefPos")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(ast.areas[0].lowerLimit, (12.25, 23.75))
		self.assertEqual(ast.areas[0].upperLimit, (13.5, 25.0))
		self.assertEqual(len(ast.places), 1)
	
	def test2DWithError(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 12.25 23.75 13.5 25.0 Error 1 2")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(len(ast.places), 1)
		self.assertEqual(ast.places[0].error.values, ((1., 2.),))

	def testSimple3D(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS CART3 1 2 3")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(ast.areas[0].lowerLimit, (1.0, 2.0, 3.0))
		self.assertEqual(ast.areas[0].upperLimit, None)

	def test3DWithError(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS CART3 1 2 3 4 5 6"
			" Error 0.25 0.5 0.75")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(ast.areas[0].lowerLimit, (1.0, 2.0, 3.0))
		self.assertEqual(ast.areas[0].upperLimit, (4.0, 5.0, 6.0))
		self.assertEqual(ast.places[0].error.values, ((.25, .5, .75),))
	
	def testWithPosition(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 12.25 23.75 13.5 25.0"
			" Position 12 24")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(len(ast.places), 1)
		self.assertEqual(ast.places[0].value, (12., 24.))

	def test1D(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS CART1 1"
			" Error 0.25 0.5")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(ast.areas[0].lowerLimit, (1.0,))
		self.assertEqual(ast.places[0].error.values[0], (0.25,))
		self.assertEqual(ast.places[0].error.values[1], (0.5,))

	def testBadPositionRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS, 
			"PositionInterval ICRS 12.25 23.75 13.5 25.0 Position 12 24 3 4")


class GeometryTest(testhelpers.VerboseTest):
	def testAllSky(self):
		ast = stcsast.parseSTCS("AllSky ICRS")
		self.assert_(isinstance(ast.areas[0], dm.AllSky))
		self.assertEqual(ast.areas[0].frame.refFrame, 'ICRS')

	def testAllSkyRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"AllSky ICRS 12")

	def testCircle2D(self):
		ast = stcsast.parseSTCS("Circle ICRS CART2 12 13 1.5")
		c = ast.areas[0]
		self.assert_(isinstance(c, dm.Circle))
		self.assertEqual(c.frame.refFrame, 'ICRS')
		self.assertEqual(c.center, (12., 13.))
		self.assertEqual(c.radius, 1.5)

	def testCircle3D(self):
		ast = stcsast.parseSTCS("Circle FK5 CART3 12 13 15 1.5")
		c = ast.areas[0]
		self.assert_(isinstance(c, dm.Circle))
		self.assertEqual(c.frame.refFrame, 'FK5')
		self.assertEqual(c.center, (12., 13., 15.))
		self.assertEqual(c.radius, 1.5)

	def testCircleRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Circle ICRS 12")
	
	def testEllipse(self):
		ast = stcsast.parseSTCS("Ellipse ICRS 12 13 1.5 0.75 0")
		c = ast.areas[0]
		self.assert_(isinstance(c, dm.Ellipse))
		self.assertEqual(c.center, (12., 13.))
		self.assertEqual(c.smajAxis, 1.5)
		self.assertEqual(c.sminAxis, 0.75)
		self.assertEqual(c.posAngle, 0)

	def testEllipseRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Ellipse ICRS 12 13 14")
	
	def testBox(self):
		ast = stcsast.parseSTCS("Box ICRS 12 13 1.5 0.75")
		c = ast.areas[0]
		self.assert_(isinstance(c, dm.Box))
		self.assertEqual(c.center, (12., 13.))
		self.assertEqual(c.boxsize, (1.5, 0.75))

	def testBoxRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Box ICRS 12 13 1.5 0.75 0")

	def testPolygon(self):
		ast = stcsast.parseSTCS("Polygon ICRS 12 13 15 14 11 10")
		c = ast.areas[0]
		self.assert_(isinstance(c, dm.Polygon))
		self.assertEqual(c.vertices[0], (12., 13.))
		self.assertEqual(c.vertices[1], (15., 14.))
		self.assertEqual(c.vertices[2], (11., 10.))
		self.assertEqual(len(c.vertices), 3)
	
	def testPolygonRaises(self):
		self.assertRaises(stc.STCSParseError, stcsast.parseSTCS,
			"Polygon ICRS 12 13 1.5 0.75 0")

	def testConvex(self):
		ast = stcsast.parseSTCS("Convex ICRS 12 13 15 0.25 14 11 10 -0.25")
		c = ast.areas[0]
		self.assertEqual(c.vectors[0], (12., 13., 15., 0.25))
		self.assertEqual(c.vectors[1], (14., 11., 10., -0.25))
		self.assertEqual(len(c.vectors), 2)


class UnitParseTest(testhelpers.VerboseTest):
	"""tests for parsing units.
	"""
	def test2DSpatial(self):
		ast = stcsast.parseSTCS("Position ICRS 1 200 unit deg")
		self.assertEqual(ast.places[0].units, ("deg", "deg"))
	
	def test3DGeo(self):
		ast = stcsast.parseSTCS("Position GEO_D SPHER3 49.39861 8.72083 560")
		self.assertEqual(ast.places[0].units, ("deg", "deg", "m"))
	
	def test1DSpatialInterval(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS CART1 1 unit km")
		self.assertEqual(ast.places[0].units, ("km",))
		self.assertEqual(ast.areas[0].units, ("km",))

	def test2DSpatialInterval(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 1 2 2 3 unit rad")
		self.assertEqual(ast.places[0].units, ("rad", "rad"))
		self.assertEqual(ast.areas[0].units, ("rad", "rad"))
	
	def testSpectral(self):
		ast = stcsast.parseSTCS("SpectralInterval 1 2 unit nm")
		self.assertEqual(ast.freqs[0].unit, "nm")
		self.assertEqual(ast.freqAs[0].unit, "nm")

	def testTime(self):
		ast = stcsast.parseSTCS("TimeInterval MJD56 MJD57 unit a")
		self.assertEqual(ast.times[0].unit, "a")
		self.assertEqual(ast.timeAs[0].unit, "a")

	def testRedshift(self):
		ast = stcsast.parseSTCS("RedshiftInterval 1000 2000 unit km/s")
		self.assertEqual(ast.redshifts[0].unit, "km")
		self.assertEqual(ast.redshiftAs[0].unit, "km")
		self.assertEqual(ast.redshifts[0].velTimeUnit, "s")
		self.assertEqual(ast.redshiftAs[0].velTimeUnit, "s")


class VelocityTest(testhelpers.VerboseTest):
	"""tests for velocity handling.
	"""
	def testTrivial(self):
		ast = stcsast.parseSTCS("Position ICRS VelocityInterval 1 2")
		self.failUnless(ast.velocities[0].frame is ast.astroSystem.spaceFrame)
		self.assertEqual(ast.velocityAs[0].units, ("m", "m"))
		self.assertEqual(ast.velocityAs[0].velTimeUnits, ("s", "s"))
		self.assertEqual(ast.velocityAs[0].lowerLimit, (1., 2.0))
		self.assertEqual(ast.velocityAs[0].upperLimit, None)
	
	def testSimple(self):
		ast = stcsast.parseSTCS("Position ICRS VelocityInterval Velocity 1 2"
			" unit deg/cy")
		self.assertEqual(ast.velocities[0].units, ("deg", "deg"))
		self.assertEqual(ast.velocities[0].velTimeUnits, ("cy", "cy"))
		self.assertEqual(ast.velocities[0].value, (1., 2.))
		self.assertEqual(len(ast.velocityAs), 1)
	
	def testComplex(self):
		ast = stcsast.parseSTCS("Position ICRS VelocityInterval -0.125 2.5"
			" 0.125 3 unit deg/cy Error 0.125 0.25 Resolution 1.5 1"
			" PixSize 0.5 0.5")
		self.assertEqual(ast.velocityAs[0].lowerLimit, (-0.125, 2.5))
		self.assertEqual(ast.velocityAs[0].upperLimit, (0.125, 3))
		self.assertEqual(ast.velocities[0].error.values[0], (0.125, 0.25))
		self.assertEqual(ast.velocities[0].resolution.values[0], (1.5, 1))
		self.assertEqual(ast.velocities[0].pixSize.values[0], (0.5, 0.5))


class STCSRoundtripTest(testhelpers.VerboseTest):
	"""tests for STC-S strings going though parsing, STC-X generation, STC-X parsing, and STC-Sgeneration largely unscathed.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, item):
		stcsIn, stcsOut = item
		ast = stc.parseSTCS(stcsIn)
		stcx = stc.getSTCXProfile(ast)
		ast = stc.parseSTCX(stcx)[0]
		self.assertEqual(stc.getSTCS(ast), stcsOut)
	
	samples = [
		("Position ICRS 12.75 14.25", "Position ICRS 12.75 14.25"),
		("Position ICRS 12000.3 14000 unit arcsec Error 0.1 0.14 Resolution 0.5 0.55"
			" Size 1 1.1  4.8 2.3 PixSize 0.2 0.2",
			"Position ICRS 12000.3 14000.0 unit arcsec Error 0.1 0.14 Resolution 0.5 0.55"
			" Size 1.0 1.1 4.8 2.3 PixSize 0.2 0.2"),
		("PositionInterval UNKNOWNFrame CART1 1 2 unit mm",
			"PositionInterval UNKNOWNFrame CART1 1.0 2.0 unit mm"),
		("PositionInterval ICRS 12 13 14 15",
			"PositionInterval ICRS 12.0 13.0 14.0 15.0"),
		("PositionInterval ICRS 12 13 14 15 Size 1 1.5 1.75 2",
			"PositionInterval ICRS 12.0 13.0 14.0 15.0 Size 1.0 1.5 1.75 2.0"),
		("PositionInterval ECLIPTIC CART3 12 13 10 14 15 9 PixSize 1 1 1",
			"PositionInterval ECLIPTIC CART3 12.0 13.0 10.0 14.0 15.0 9.0 PixSize 1.0 1.0 1.0"),
		("Circle ICRS 12 13 1 unit arcsec",
			"Circle ICRS 12.0 13.0 1.0 unit arcsec"),
		("Circle ICRS 12 13 1 unit arcsec Resolution 1 2 PixSize 2 1",
			"Circle ICRS 12.0 13.0 1.0 unit arcsec Resolution 1.0 2.0 PixSize 2.0 1.0"),
		("Ellipse ICRS 12 13 1 0.75 0 Resolution 1 1",
			"Ellipse ICRS 12.0 13.0 1.0 0.75 0.0 Resolution 1.0 1.0"),
		("Box fillfactor 0.125 ICRS 70 190 23 18",
			"Box fillfactor 0.125 ICRS 70.0 190.0 23.0 18.0"),
		("Polygon ICRS 70 190 23 18 12 45 30 -10",
			"Polygon ICRS 70.0 190.0 23.0 18.0 12.0 45.0 30.0 -10.0"),
		("Convex FK5 J1990 70 190 23 0.125 12 45 30 -0.25",
			"Convex FK5 J1990.0 70.0 190.0 23.0 0.125 12.0 45.0 30.0 -0.25"),
		("TimeInterval TT 2009-03-10T09:56:10.015625"
			" SpectralInterval 1e10 1e11 unit Hz"
			" RedshiftInterval 1000 7500 unit km/s",
			"StartTime TT 2009-03-10T09:56:10.015625\nSpectralInterval"
			" 10000000000.0 100000000000.0\nRedshiftInterval 1000.0 7500.0"),
		("Time TT 2009-03-10T09:56:10.015625",
			"Time TT 2009-03-10T09:56:10.015625"),
		("Time TDT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2",
			"Time TDT 2009-03-10T09:56:10.015625"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2.0"),
		("TimeInterval TDT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2",
			"StartTime TDT 2009-03-10T09:56:10.015625"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2.0"),
		("Spectral NEPTUNE 12 unit Angstrom Error 4 3"
			" Redshift TOPOCENTER 0.1 REDSHIFT RELATIVISTIC",
			"Spectral NEPTUNE 12.0 unit Angstrom Error 4.0 3.0\nRedshift"
			" TOPOCENTER REDSHIFT RELATIVISTIC 0.1"),
	]


if __name__=="__main__":
	testhelpers.main(STCSRoundtripTest)
