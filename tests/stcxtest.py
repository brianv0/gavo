"""
Tests for STC-X parsing and generation.
"""

import re

from gavo import stc
from gavo.stc import stcxgen
from gavo.stc import dm

import testhelpers


def _purgeIds(stcx):
	return re.sub('(frame_|coord_system_)?id="[^"]*"', '', stcx)

def assertEqualWithoutIds(withId, template, msg=None):
	"""raises an AssertionError if withId and template are different after
	all ids (and similar) in withId are blanked.

	We want this since the ids given to our elements are essentially random.
	"""
	withoutId = _purgeIds(withId)
	if withoutId!=template:
		if msg:
			raise AssertionError(msg)
		else:
			raise AssertionError("%r != %r"%(withoutId, template))


class SpaceFrameTest(testhelpers.VerboseTest):
	def testSimple(self):
		assertEqualWithoutIds(stcxgen.nodeToStan(dm.SpaceFrame(
			flavor="CARTESIAN", nDim=2, refFrame="ICRS", name="rotten",
			refPos=dm.RefPos(standardOrigin="GEOCENTER"))).render(),
		'<SpaceFrame ><Name>rotten</Name><ICRS /><GEOCENTER />'
			'<CARTESIAN coord_naxes="2" /></SpaceFrame>')


class V(stc.STC.STCElement):
	"""A spartan STC-X root for test purposes.
	"""


class STCMappingTest(testhelpers.VerboseTest):
	def assertMapsto(self, stcsLiteral, stcxExpected):
		ast = stc.parseSTCS(stcsLiteral)
		stcxResult = stcxgen.astToStan(ast, V).render()
		assertEqualWithoutIds(stcxResult, stcxExpected,
			"Failed stcs map: %s, got %s"%(stcsLiteral, _purgeIds(stcxResult)))


class OtherCoordTest(STCMappingTest):
	def testSimple(self):
		self.assertMapsto("Time TT 2009-03-10T09:56:10.015625", 
			'<V><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame></AstroCoordSystem><AstroCoords ><Time  unit="s"><TimeInstant><ISOTime>2009-03-10T09:56:10.015625</ISOTime></TimeInstant></Time></AstroCoords></V>')

	def testComplex(self):
		self.assertMapsto("Time TT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2",
			'<V><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame></AstroCoordSystem><AstroCoords ><Time  unit="s"><TimeInstant><ISOTime>2009-03-10T09:56:10.015625</ISOTime></TimeInstant><Error>0.0001</Error><Error>0.0002</Error><Resolution>0.0001</Resolution><PixSize>2.0</PixSize></Time></AstroCoords></V>')

	def testRedSpect(self):
		self.assertMapsto("Spectral NEPTUNE 12 unit Angstrom Error 4 3"
			" Redshift TOPOCENTER 0.1 VELOCITY RELATIVISTIC", 
			'<V><AstroCoordSystem ><SpectralFrame ><NEPTUNE /></SpectralFrame><RedshiftFrame  value_type="VELOCITY"><DopplerDefinition>RELATIVISTIC</DopplerDefinition><TOPOCENTER /></RedshiftFrame></AstroCoordSystem><AstroCoords ><Spectral  unit="Angstrom"><Value>12.0</Value><Error>4.0</Error><Error>3.0</Error></Spectral><Redshift  unit="km" vel_time_unit="s"><Value>0.1</Value></Redshift></AstroCoords></V>')

class SpaceCoordTest(STCMappingTest):
	def testSimple(self):
		self.assertMapsto("Position ICRS 12.3 14.2",
			'<V><AstroCoordSystem ><SpaceFrame ><ICRS /><UNKNOWNRefPos /><SPHERICAL coord_naxes="2" /></SpaceFrame></AstroCoordSystem><AstroCoords ><Position2D  unit="deg"><Value2><C1>12.3</C1><C2>14.2</C2></Value2></Position2D></AstroCoords></V>')

class OtherCoordIntervalTest(STCMappingTest):
	def testSome(self):
		self.assertMapsto("TimeInterval TT 2009-03-10T09:56:10.015625"
			" SpectralInterval 1e10 1e11 unit Hz"
			" RedshiftInterval 1000 7500 unit km/s", 
			'<V><AstroCoordSystem ><TimeFrame ><TimeScale>TT</TimeScale><UNKNOWNRefPos /></TimeFrame><SpectralFrame ><UNKNOWNRefPos /></SpectralFrame><RedshiftFrame  value_type="VELOCITY"><DopplerDefinition>OPTICAL</DopplerDefinition><UNKNOWNRefPos /></RedshiftFrame></AstroCoordSystem><AstroCoordArea ><TimeInterval  unit="s"><StartTime><ISOTime>2009-03-10T09:56:10.015625</ISOTime></StartTime><StopTime><ISOTime /></StopTime></TimeInterval><SpectralInterval  unit="Hz"><LoLimit>10000000000.0</LoLimit><HiLimit>100000000000.0</HiLimit></SpectralInterval><RedshiftInterval  unit="km" vel_time_unit="s"><LoLimit>1000.0</LoLimit><HiLimit>7500.0</HiLimit></RedshiftInterval></AstroCoordArea></V>')


if __name__=="__main__":
	testhelpers.main(OtherCoordIntervalTest)
