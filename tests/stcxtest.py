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


class TimeTest(STCMappingTest):
	def testSimple(self):
		self.assertMapsto("Time TT 2009-03-10T09:56:10.015625", 
			'<V><AstroCoordSystem ><TimeFrame ><UNKNOWNRefPos /><TimeScale>TT<'
			'/TimeScale></TimeFrame></AstroCoordSystem><AstroCoords ><Time ><T'
			'imeInstant><ISOTime>2009-03-10T09:56:10.015625</ISOTime></TimeIns'
			'tant></Time></AstroCoords></V>')


if __name__=="__main__":
	testhelpers.main(TimeTest)
