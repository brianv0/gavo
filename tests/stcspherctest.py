"""
Tests for the calculations with various spherical coordinate systems.
"""

import testhelpers

from gavo import stc
from gavo import utils
from gavo.stc import spherc
from gavo.stc import times


class PrecTest(testhelpers.VerboseTest):
	"""tests for various precessions.
	"""
	def testLieskeConstantsFromJ2000(self):
		for year, zetaL, zL, thetaL in [
				(1950, -1153.036, -1152.838, -1002.257),
				(1980, -461.232, -461.200, -400.879),
				(2050, 1153.187, 1153.385, 1002.044)]:
			destEp = stc.jYearToDateTime(year)
			zeta, z, theta = spherc.prec_IAU1976(times.dtJ2000, destEp)
			self.assertAlmostEqual(zeta*utils.radToArcsec, zetaL, places=3)
			self.assertAlmostEqual(z*utils.radToArcsec, zL, places=3)
			self.assertAlmostEqual(theta*utils.radToArcsec, thetaL, places=3)

	def testLieskeConstantsToJ2000(self):
		for year, zetaL, zL, thetaL in [
				(1850, 3456.881, 3458.664, 3007.246),
				(1920, 1844.273, 1844.781, 1603.692),
				(1965, 807.055, 807.152, 701.570),]:
			srcEp = stc.bYearToDateTime(year)
			zeta, z, theta = spherc.prec_IAU1976(srcEp, times.dtJ2000)
			self.assertAlmostEqual(zeta*utils.radToArcsec, zetaL, places=3)
			self.assertAlmostEqual(z*utils.radToArcsec, zL, places=3)
			self.assertAlmostEqual(theta*utils.radToArcsec, thetaL, places=3)


if __name__=="__main__":
	testhelpers.main(PrecTest)
