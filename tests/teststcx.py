"""
Tests for STC-X parsing and generation.
"""

import re

from gavo.stc import stcxast
from gavo.stc import dm

import testhelpers


def assertEqualWithoutIds(withId, template):
	"""raises an AssertionError if withId and template are different after
	all ids (and similar) in withId are blanked.

	We want this since the ids given to our elements are essentially random.
	"""
	withoutId = re.sub('id="[^"]*"', '', withId)
	if withoutId!=template:
		raise AssertionError("%r != %r"%(withoutId, template))


class SpaceFrameTest(testhelpers.VerboseTest):
	def testSimple(self):
		assertEqualWithoutIds(stcxast.astToStan(dm.SpaceFrame(
			flavor="CARTESIAN", nDim=2, refFrame="ICRS", name="rotten",
			refPos=dm.RefPos(standardOrigin="GEOCENTER"))).render(),
		'<SpaceFrame ><Name>rotten</Name><ICRS /><GEOCENTER />'
			'<CARTESIAN coord_naxes="2" /></SpaceFrame>')


if __name__=="__main__":
	testhelpers.main(SpaceFrameTest)
