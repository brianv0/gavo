"""
Tests for STC-X parsing and generation.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
import re

from gavo.helpers import testhelpers

from gavo import stc
from gavo.stc import stcxgen
from gavo.stc import dm




def assertEqualWithoutIds(withId, template, desc="<Undescribed>"):
	"""raises an AssertionError if withId and template are different after
	all ids (and similar) in withId are blanked.

	We want this since the ids given to our elements are essentially random.
	"""
	# etree-based serialization has blanks in empty elements; we don't
	# want to fail on templates for that
	withoutId = testhelpers.cleanXML(withId)
	template = testhelpers.cleanXML(template)
	if withoutId!=template:
		matchLen = len(os.path.commonprefix([template, withoutId]))
		raise AssertionError("Didn't get expected STC XML for example '%s';"
			" non-matching part: %s"%(desc, withoutId[matchLen:]))


class SpaceFrameTest(testhelpers.VerboseTest):
	def testSimple(self):
		assertEqualWithoutIds(stcxgen._nodeToStan(dm.SpaceFrame(
			flavor="CARTESIAN", nDim=2, refFrame="ICRS", name="rotten",
			refPos=dm.RefPos(standardOrigin="GEOCENTER")), None).render(
				prefixForEmpty="stc"),
		'<SpaceFrame ><Name>rotten</Name><ICRS /><GEOCENTER />'
			'<CARTESIAN coord_naxes="2" /></SpaceFrame>')

	def testParsing(self):
		ast = stc.parseSTCX(
			'<STCSpec xmlns="http://www.ivoa.net/xml/STC/stc-v1.30.xsd"><Astro'
			'CoordSystem><SpaceFrame><GALACTIC_II/><BARYCENTER/></SpaceFrame><'
			'/AstroCoordSystem><AstroCoords><Position2D><Value2><C1>12.2</C1><'
			'C2>0.3</C2></Value2></Position2D></AstroCoords></STCSpec>')[0][1]
		self.assertEqual(ast.astroSystem.spaceFrame.refFrame, "GALACTIC_II")


class TimeFrameTest(testhelpers.VerboseTest):
	def testSimple(self):
		ast = stc.parseSTCX('<STCSpec xmlns="http://www.ivoa.net/xml/STC/stc-'
			'v1.30.xsd"><AstroCoordSystem><TimeFrame><TOPOCENTER/><TimeScale>TT'
			'</TimeScale></TimeFrame></AstroCoordSystem></STCSpec>')[0][1]
		self.assertEqual(ast.astroSystem.timeFrame.refPos.standardOrigin,
			"TOPOCENTER")
		self.assertEqual(ast.astroSystem.timeFrame.timeScale, "TT")


class V(stc.STC.STCElement):
	"""A spartan STC-X root for test purposes.
	"""


class STCMappingTest(testhelpers.VerboseTest):
	def assertMapsto(self, stcsLiteral, stcxExpected):
		ast = stc.parseSTCS(stcsLiteral)
		stcxResult = stcxgen.astToStan(ast, V).render(prefixForEmpty="stc")
		assertEqualWithoutIds(stcxResult, stcxExpected,
			stcsLiteral)


class OtherCoordTest(STCMappingTest):
	def testSimple(self):
		self.assertMapsto("Time TT 2009-03-10T09:56:10.015625", 
			'<V ><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame></AstroCoordSystem><AstroCoords ><Time unit="s"><TimeInstant><ISOTime>2009-03-10T09:56:10.015625</ISOTime></TimeInstant></Time></AstroCoords></V>')

	def testComplex(self):
		self.assertMapsto("Time TT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2",
			'<V ><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame></AstroCoordSystem><AstroCoords ><Time unit="s"><TimeInstant><ISOTime>2009-03-10T09:56:10.015625</ISOTime></TimeInstant><Error>0.0001</Error><Error>0.0002</Error><Resolution>0.0001</Resolution><PixSize>2.0</PixSize></Time></AstroCoords></V>')

	def testRedSpect(self):
		self.assertMapsto("Spectral NEPTUNE 12 unit Angstrom Error 4 3"
			" Redshift TOPOCENTER VELOCITY RELATIVISTIC 0.1", 
			'<V ><AstroCoordSystem ><SpectralFrame ><NEPTUNE /></SpectralFrame><RedshiftFrame value_type="VELOCITY"><DopplerDefinition>RELATIVISTIC</DopplerDefinition><TOPOCENTER /></RedshiftFrame></AstroCoordSystem><AstroCoords ><Spectral unit="Angstrom"><Value>12.0</Value><Error>4.0</Error><Error>3.0</Error></Spectral><Redshift unit="km" vel_time_unit="s"><Value>0.1</Value></Redshift></AstroCoords></V>')


class SpaceCoordTest(STCMappingTest):
	def testSimple(self):
		self.assertMapsto("Position ICRS 12.3 14.2",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoords ><Position2D unit="deg"><Value2><C1>12.3</C1><C2>14.2</C2></Value2></Position2D></AstroCoords></V>')

	def testComplex(self):
		self.assertMapsto("Position ICRS Epoch J200.3 12000.3 14000 unit arcsec"
			" Error 0.1 0.14 Resolution 0.5 0.55 Size 1 1.1 4.8 2.3 PixSize 0.2 0.2",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoords ><Position2D unit="arcsec"><Value2><C1>12000.3</C1><C2>14000.0</C2></Value2><Error2><C1>0.1</C1><C2>0.14</C2></Error2><Resolution2><C1>0.5</C1><C2>0.55</C2></Resolution2><Size2><C1>1.0</C1><C2>1.1</C2></Size2><Size2><C1>4.8</C1><C2>2.3</C2></Size2><PixSize2Radius>0.2</PixSize2Radius><Epoch yearDef="J">200.3</Epoch></Position2D></AstroCoords></V>')


class OtherCoordIntervalTest(STCMappingTest):
	def testSome(self):
		self.assertMapsto("TimeInterval TT 2009-03-10T09:56:10.015625"
			" SpectralInterval 1e10 1e11 unit Hz"
			" RedshiftInterval VELOCITY 1000 7500 unit km/s", 
			'<V ><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame><SpectralFrame ><UNKNOWNRefPos /></SpectralFrame><RedshiftFrame value_type="VELOCITY"><DopplerDefinition>OPTICAL</DopplerDefinition><UNKNOWNRefPos /></RedshiftFrame></AstroCoordSystem><AstroCoordArea ><TimeInterval ><StartTime><ISOTime>2009-03-10T09:56:10.015625</ISOTime></StartTime></TimeInterval><SpectralInterval unit="Hz"><LoLimit>10000000000.0</LoLimit><HiLimit>1e+11</HiLimit></SpectralInterval><RedshiftInterval unit="km" vel_time_unit="s"><LoLimit>1000.0</LoLimit><HiLimit>7500.0</HiLimit></RedshiftInterval></AstroCoordArea></V>')

	def testTimeWithError(self):
		self.assertMapsto("TimeInterval TT 2009-03-10T09:56:10 2009-03-10T09:57:10 Error"
			" 4 Resolution 1 2 PixSize 1",
			'<V ><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame></AstroCoordSystem><AstroCoords ><Time unit="s"><Error>4.0</Error><Resolution>1.0</Resolution><Resolution>2.0</Resolution><PixSize>1.0</PixSize></Time></AstroCoords><AstroCoordArea ><TimeInterval ><StartTime><ISOTime>2009-03-10T09:56:10</ISOTime></StartTime><StopTime><ISOTime>2009-03-10T09:57:10</ISOTime></StopTime></TimeInterval></AstroCoordArea></V>')

	def testSpectralWithError(self):
		self.assertMapsto("SpectralInterval 1e10 1e11 unit Hz Error 1 2",
			'<V ><AstroCoordSystem ><SpectralFrame ><UNKNOWNRefPos /></SpectralFrame></AstroCoordSystem><AstroCoords ><Spectral unit="Hz"><Error>1.0</Error><Error>2.0</Error></Spectral></AstroCoords><AstroCoordArea ><SpectralInterval unit="Hz"><LoLimit>10000000000.0</LoLimit><HiLimit>1e+11</HiLimit></SpectralInterval></AstroCoordArea></V>')


class SpaceCoordIntervalTest(STCMappingTest):
	def test1D(self):
		self.assertMapsto("PositionInterval UNKNOWNFrame CART1 1 2 unit mm",
			'<V ><AstroCoordSystem ><SpaceFrame ><UNKNOWNFrame /><UNKNOWNRefPos /><CARTESIAN coord_naxes="1" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><PositionScalarInterval unit="mm"><LoLimit>1.0</LoLimit><HiLimit>2.0</HiLimit></PositionScalarInterval></AstroCoordArea></V>')

	def test2D(self):
		self.assertMapsto("PositionInterval ICRS 12 13 14 15",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Position2VecInterval unit="deg"><LoLimit2Vec><C1>12.0</C1><C2>13.0</C2></LoLimit2Vec><HiLimit2Vec><C1>14.0</C1><C2>15.0</C2></HiLimit2Vec></Position2VecInterval></AstroCoordArea></V>')

	def test2DWithSize(self):
		self.assertMapsto("PositionInterval ICRS 12 13 14 15 Size 1 1.5 1.75 2",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoords ><Position2D unit="deg"><Size2><C1>1.0</C1><C2>1.5</C2></Size2><Size2><C1>1.75</C1><C2>2.0</C2></Size2></Position2D></AstroCoords><AstroCoordArea ><Position2VecInterval unit="deg"><LoLimit2Vec><C1>12.0</C1><C2>13.0</C2></LoLimit2Vec><HiLimit2Vec><C1>14.0</C1><C2>15.0</C2></HiLimit2Vec></Position2VecInterval></AstroCoordArea></V>')

	def test3D(self):
		self.assertMapsto("Time TT 2000-01-01T12:00:00"
			" PositionInterval ECLIPTIC CART3 12 13 10 14 15 9",
			'<V ><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame><SpaceFrame ><ECLIPTIC><Equinox>J2000.0</Equinox></ECLIPTIC><UNKNOWNRefPos /><CARTESIAN coord_naxes="3" /></SpaceFrame></AstroCoordSystem><AstroCoords ><Time unit="s"><TimeInstant><ISOTime>2000-01-01T12:00:00</ISOTime></TimeInstant></Time></AstroCoords><AstroCoordArea ><Position3VecInterval unit="m"><LoLimit3Vec><C1>12.0</C1><C2>13.0</C2><C3>10.0</C3></LoLimit3Vec><HiLimit3Vec><C1>14.0</C1><C2>15.0</C2><C3>9.0</C3></HiLimit3Vec></Position3VecInterval></AstroCoordArea></V>')


class RegionTest(STCMappingTest):
	def assertRaisesValueError(self, stcsExpr):
		self.assertRaises(stc.STCValueError, 
			lambda s:stcxgen.astToStan(stc.parseSTCS(s), V), 
			stcsExpr)

	def testCircles(self):
		self.assertRaisesValueError("Circle UNKNOWNFrame CART1 12 4")
		self.assertMapsto("Circle ICRS 12 13 1", 
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Circle unit="deg"><Center><C1>12.0</C1><C2>13.0</C2></Center><Radius>1.0</Radius></Circle></AstroCoordArea></V>')
		self.assertMapsto("Circle UNKNOWNFrame CART3 12 13 1 4", 
			'<V ><AstroCoordSystem ><SpaceFrame ><UNKNOWNFrame /><UNKNOWNRefPos /><CARTESIAN coord_naxes="3" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Sphere unit="m"><Radius>4.0</Radius><Center><C1>12.0</C1><C2>13.0</C2><C3>1.0</C3></Center></Sphere></AstroCoordArea></V>')

	def testEllipse(self):
		self.assertMapsto("Ellipse ICRS 12 13 1 0.75 0",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Ellipse unit="deg"><Center><C1>12.0</C1><C2>13.0</C2></Center><SemiMajorAxis>1.0</SemiMajorAxis><SemiMinorAxis>0.75</SemiMinorAxis><PosAngle>0.0</PosAngle></Ellipse></AstroCoordArea></V>')
	
	def testBox(self):
		self.assertMapsto("Box fillfactor 0.1 ICRS 70 190 23 18",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Box fill_factor="0.1" unit="deg"><Center><C1>70.0</C1><C2>190.0</C2></Center><Size><C1>23.0</C1><C2>18.0</C2></Size></Box></AstroCoordArea></V>')
		self.assertRaisesValueError("Box UNKNOWNFrame CART1 1 1")
	
	def testPolygon(self):
		self.assertMapsto("Polygon ICRS 70 190 23 18 12 45 30 -10",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Polygon unit="deg"><Vertex><Position><C1>70.0</C1><C2>190.0</C2></Position></Vertex><Vertex><Position><C1>23.0</C1><C2>18.0</C2></Position></Vertex><Vertex><Position><C1>12.0</C1><C2>45.0</C2></Position></Vertex><Vertex><Position><C1>30.0</C1><C2>-10.0</C2></Position></Vertex></Polygon></AstroCoordArea></V>')
		self.assertRaisesValueError("Polygon UNKNOWNFrame CART1 1 2 3 4")
	
	def testConvex(self):
		self.assertMapsto("Convex ICRS 70 190 23 0.125 12 45 30 -0.25",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><UNITSPHERE coord_naxes="3" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Convex ><Halfspace><Vector><C1>70.0</C1><C2>190.0</C2><C3>23.0</C3></Vector><Offset>0.125</Offset></Halfspace><Halfspace><Vector><C1>12.0</C1><C2>45.0</C2><C3>30.0</C3></Vector><Offset>-0.25</Offset></Halfspace></Convex></AstroCoordArea></V>')


class CompoundTest(STCMappingTest):
	def testSimpleUnion(self):
		self.assertMapsto("Union ICRS (Circle 10 10 2 Box 11 11 2 3)",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Union><Circle unit="deg"><Center><C1>10.0</C1><C2>10.0</C2></Center><Radius>2.0</Radius></Circle><Box unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><Size><C1>2.0</C1><C2>3.0</C2></Size></Box></Union></AstroCoordArea></V>')
	
	def testSimpleIntersection(self):
		self.assertMapsto("Intersection ICRS (Polygon 10 2 2 10 10 10"
			" Ellipse 11 11 2 3 30)",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Intersection><Polygon unit="deg"><Vertex><Position><C1>10.0</C1><C2>2.0</C2></Position></Vertex><Vertex><Position><C1>2.0</C1><C2>10.0</C2></Position></Vertex><Vertex><Position><C1>10.0</C1><C2>10.0</C2></Position></Vertex></Polygon><Ellipse unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><SemiMajorAxis>2.0</SemiMajorAxis><SemiMinorAxis>3.0</SemiMinorAxis><PosAngle>30.0</PosAngle></Ellipse></Intersection></AstroCoordArea></V>')

	def testUnionWithNot(self):
		self.assertMapsto("Union ICRS (Circle 10 10 2 Not (Box 11 11 2 3))",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Union><Circle unit="deg"><Center><C1>10.0</C1><C2>10.0</C2></Center><Radius>2.0</Radius></Circle><Negation><Box unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><Size><C1>2.0</C1><C2>3.0</C2></Size></Box></Negation></Union></AstroCoordArea></V>')

	def testSimpleDifference(self):
		self.assertMapsto("Difference ICRS (Circle 10 10 2 Not (Box 11 11 2 3))",
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Difference><Circle unit="deg"><Center><C1>10.0</C1><C2>10.0</C2></Center><Radius>2.0</Radius></Circle><Negation2><Box unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><Size><C1>2.0</C1><C2>3.0</C2></Size></Box></Negation2></Difference></AstroCoordArea></V>')
	
	def testInsaneRegion(self):
		self.assertMapsto("Difference ICRS (AllSky Union (Circle 10 10 2"
			" Intersection (Polygon 10 2 2 10 10 10 Ellipse 11 11 2 3 30"
			" Not (Difference (Circle 12 12 3 Box 11 11 2 3)))))", 
			'<V ><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoordArea ><Difference><AllSky unit="deg" /><Union2><Circle unit="deg"><Center><C1>10.0</C1><C2>10.0</C2></Center><Radius>2.0</Radius></Circle><Intersection><Polygon unit="deg"><Vertex><Position><C1>10.0</C1><C2>2.0</C2></Position></Vertex><Vertex><Position><C1>2.0</C1><C2>10.0</C2></Position></Vertex><Vertex><Position><C1>10.0</C1><C2>10.0</C2></Position></Vertex></Polygon><Ellipse unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><SemiMajorAxis>2.0</SemiMajorAxis><SemiMinorAxis>3.0</SemiMinorAxis><PosAngle>30.0</PosAngle></Ellipse><Negation><Difference><Circle unit="deg"><Center><C1>12.0</C1><C2>12.0</C2></Center><Radius>3.0</Radius></Circle><Box2 unit="deg"><Center><C1>11.0</C1><C2>11.0</C2></Center><Size><C1>2.0</C1><C2>3.0</C2></Size></Box2></Difference></Negation></Intersection></Union2></Difference></AstroCoordArea></V>')


class STCSRoundtripTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		src, expected = sample
		if expected is None:
			expected = src
		ast = stc.parseSTCS(src)
		xml = stc.getSTCXProfile(ast)
		ast2 = stc.parseSTCX(xml)[0][1]
		stcs = stc.getSTCS(ast2)
		self.assertEqual(stcs, expected)
	
	samples = [
		("AllSky ICRS", None),
		("Box ICRS 12 1 15 3", 'Box ICRS 12.0 1.0 15.0 3.0'),
	]


if __name__=="__main__":
	testhelpers.main(STCSRoundtripTest)
