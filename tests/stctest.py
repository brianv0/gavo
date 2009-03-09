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

class ValidationTests():#unittest.TestCase, testhelpers.XSDTestMixin):
	"""tests for generation of XSD-valid documents from the xml stan.
	"""
	def testExample1(self):
		for name in dir(stcx.STC):
			if not name.startswith("_"):
				exec "%s = getattr(stcx.STC, %s)"%(name, repr(name))
		tree = STCResourceProfile[
			AstroCoordSystem(id="TT-ICRS-CXO")[
				TimeFrame[
					Name["Time"],
					TimeScale["TT"],
					TOPOCENTER],
				SpaceFrame[
					Name["Space"],
					ICRS,
					TOPOCENTER,
					SPHERICAL],
				SpectralFrame[
					Name["Energy"],
					TOPOCENTER]],
			AstroCoords(coord_system_id="TT-ICRS-CXO")[
				Time[
					Name["Time"],
					Error[0.000005],
					Error[0.0001],
					Resolution[0.000016],
					Resolution["3.0"],
					Size["1000"],
					Size[170000]],
				Position2D(unit="arcsec")[
					Name["Position"],
					Error2Radius[1.0],
					Resolution2Radius[0.5],
					Size2[
						C1[1000],
						C2[1000]],
					Size2[
						C1[1000],
						C2[1000]]],
				Spectral(unit="keV")[
					Name["Energy"],
					Error[0.1],
					Resolution[0.02],
					Resolution[2.0],
					Size[2],
					Size[10]]],
				AstroCoordArea(id="AllSky-CXO", coord_system_id="TT-ICRS-CXO")[
					TimeInterval[
						StartTime[
							Timescale["TT"],
							ISOTime["1999-07-23T16:00:00"]]],
					AllSky(fill_factor="0.02"),
					SpectralInterval(unit="keV")[
						LoLimit[0.12],
						HiLimit[10.0]]]]
		self.assertValidates(tree.render(), leaveOffending=__name__=="__main__")

	def _testExample2(self):
# I can't figure out why xlink:href is not allowed on these documents.
# Someone else figure this whole xsd mess out.  Holy cow, it's really
# a sensation if you come across an XSD-based doc that actually verifies.
		for name in dir(stc.STC):
			if not name.startswith("_"):
				exec "%s = getattr(stc.STC, %s)"%(name, repr(name))
		tree = ObsDataLocation[
			ObservatoryLocation(id="KPNO", type="simple",
				href="ivo://STClib/Observatories#KPNO"),
			ObservationLocation[
				AstroCoords(coord_system_id="TT-ICRS-TOPO", type="simple",
						href="ivo://STClib/CoordSys#TT-ICRS-TOPO")[
					Time(unit="s")[
						TimeInstant[
							ISOTime["2004-07-15T08:23:56"]],
						Error[2]],
					Position2D(unit="deg")[
						Value2[
							C1[148.88821],
							C2[69.06529]],
						Error2Radius[0.03]]],
				AstroCoordArea(coord_system_id="TT-ICRS-TOPO")[
					Polygon(unit="deg")[
						Vertex[
							Position[
								C1[148.88821],
								C2[68.81529]]],
						Vertex[
							Position[
								C1[148.18821],
								C2[69.01529]]],
						Vertex[
							Position[
								C1[148.88821],
								C2[69.31529]]],
						Vertex[
							Position[
								C1[149.58821],
								C2[69.01529]]]]]]]
		self.assertValidates(tree.render(), leaveOffending=__name__=="__main__")


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


class OtherCoordTest(testhelpers.VerboseTest):
	def testSimpleTime(self):
		ast = stcsast.parseSTCS("Time TT 2000-12-20T23:02:12 unit yr Error 2")
		self.assertEqual(ast.times[0].frame.timeScale, "TT")
		self.assertEqual(ast.times[0].error, (2.0,))
		self.assertEqual(ast.times[0].value, 
			datetime.datetime(2000, 12, 20, 23, 2, 12))
		
	def testSimpleSpectral(self):
		ast = stcsast.parseSTCS("Spectral BARYCENTER 23 Resolution 0.25 0.5")
		self.assertEqual(ast.freqs[0].frame.refPos.standardOrigin, "BARYCENTER")
		self.assertEqual(ast.freqs[0].value, 23.)
		self.assertEqual(ast.freqs[0].resolution, (0.25, 0.5))

	def testSimpleRedshift(self):
		ast = stcsast.parseSTCS("Redshift BARYCENTER 2 unit km/s")
		self.assertEqual(ast.redshifts[0].frame.refPos.standardOrigin, 
			"BARYCENTER")
		self.assertEqual(ast.redshifts[0].value, 2.)

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
		self.assertEqual(ast.places[0].units, ["deg", "deg"])
		self.assertEqual(ast.places[0].pixSize, ((4.5, 3.75),))
	
	def testPixSizeRange(self):
		ast = stcsast.parseSTCS("Position FK5 TOPOCENTER 2 4.25 unit deg"
			" PixSize 4.5 3.75 1 5")
		self.assertEqual(ast.places[0].pixSize, ((4.5, 3.75), (1., 5.)))

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

	def testOneAndAHalfInterval(self):
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
		self.assertEqual(ast.freqAs[0].units, ["Hz"])

	def testRedshiftInterval(self):
		ast = stcsast.parseSTCS("RedshiftInterval REDSHIFT 2 4")
		self.assertEqual(len(ast.redshiftAs), 1)
		self.assertEqual(ast.redshiftAs[0].frame.type,
			"REDSHIFT")
		self.assertEqual(ast.redshiftAs[0].lowerLimit, 2.0)
		self.assertEqual(ast.redshiftAs[0].upperLimit, 4.0)


class SpaceCoordIntervalTest(testhelpers.VerboseTest):
	def testSimple2D(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 12.25 23.75 13.5 25.0")
		self.assertEqual(ast.areas[0].frame.refPos.standardOrigin, 
			"UNKNOWNRefPos")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(ast.areas[0].lowerLimit, (12.25, 23.75))
		self.assertEqual(ast.areas[0].upperLimit, (13.5, 25.0))
		self.assertEqual(len(ast.places), 0)
	
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
		self.assertEqual(ast.areas[0].error, ((.25, .5, .75),))
	
	def testWithPosition(self):
		ast = stcsast.parseSTCS("PositionInterval ICRS 12.25 23.75 13.5 25.0"
			" Position 12 24")
		self.assertEqual(len(ast.areas), 1)
		self.assertEqual(len(ast.places), 1)
		self.assertEqual(ast.places[0].value, (12., 24.))
	
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
		self.assertEqual(c.majAxis, 1.5)
		self.assertEqual(c.minAxis, 0.75)
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


if __name__=="__main__":
	testhelpers.main(GeometryTest)
