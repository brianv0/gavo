"""
STC tests requiring XSD validation (slow...)
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import stc
from gavo.stc import stcxgen


class StanValidationTests(testhelpers.VerboseTest, testhelpers.XSDTestMixin):
	"""tests for generation of XSD-valid documents from the xml stan.
	"""
	def testExample1(self):
		for name in dir(stc.STC):
			if not name.startswith("_"):
				exec "%s = getattr(stc.STC, %s)"%(name, repr(name))
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


class STCSValidationTests(testhelpers.VerboseTest, testhelpers.XSDTestMixin):
	"""tests for generation of XSD-valid documents from STC-S
	"""
	def assertFromSTCSValidates(self, stcsLiteral):
		ast = stc.parseSTCS(stcsLiteral)
		tree = stcxgen.astToStan(ast, stc.STC.STCResourceProfile)
		self.assertValidates(tree.render(),leaveOffending=__name__=="__main__")

	def testSimpleCoos(self):
		self.assertFromSTCSValidates("Time TT 2009-03-10T09:56:10.015625"
			" Spectral NEPTUNE 12 unit Angstrom Error 4 3"
			" Redshift TOPOCENTER VELOCITY RELATIVISTIC 0.1")

	def testComplexCoos(self):
		self.assertFromSTCSValidates("Time TT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2")

	def testComplexSpaceCoos(self):
		self.assertFromSTCSValidates("Position ICRS 12000.3 14000 unit arcsec"
			" Error 0.1 0.14 Resolution 0.5 0.5 Size 1 1.1  4.8 2.3 PixSize 0.2 0.25")

	def test1DIntervals(self):
		self.assertFromSTCSValidates("TimeInterval TT 2009-03-10T09:56:10.015625"
			" PositionInterval UNKNOWNFrame CART1 1 2 unit mm"
			" SpectralInterval 1e10 1e11 unit Hz"
			" RedshiftInterval 1000 7500 unit km/s")

	def test2DInterval(self):
		self.assertFromSTCSValidates("PositionInterval ICRS 12 13 14 15 Error 1 2")
			
	def test3DInterval(self):
		self.assertFromSTCSValidates(
			"Time TT 2000-01-01T12:00:00"
			" PositionInterval ECLIPTIC CART3 12 13 10 14 15 9")

	def testAllSky(self):
		self.assertFromSTCSValidates("AllSky ICRS")

	def testCircles(self):
		self.assertFromSTCSValidates("Circle ICRS 12 13 1")
		self.assertFromSTCSValidates("Circle UNKNOWNFrame CART3 12 13 1 4")

	def testEllipse(self):
		self.assertFromSTCSValidates("Ellipse ICRS 12 13 1 0.75 0")

	def testBox(self):
		self.assertFromSTCSValidates("Box fillfactor 0.1 ICRS 70 190 23 18")

	def testPolygon(self):
		self.assertFromSTCSValidates("Polygon ICRS 70 190 23 18 12 45"
			" 30 -10")

	def testConvex(self):
		self.assertFromSTCSValidates("Convex ICRS 70 190 23 0.125 12 45"
			" 30 -0.25")
	
	def testSimpleUnion(self):
		self.assertFromSTCSValidates("Union ICRS (Circle 10 10 2 Box 11 11 2 3"
			" Ellipse 12 13 1 0.75 0)")

	def testInsaneRegion(self):
		self.assertFromSTCSValidates(
			"Difference ICRS (AllSky Union (Circle 10 10 2"
			" Intersection (Polygon 10 2 2 10 10 10 Intersection( Ellipse 11 11 2 3 30"
			" Not (Difference (Circle 12 12 3 Box 11 11 2 3))))))")

if __name__=="__main__":
	testhelpers.main(STCSValidationTests)
