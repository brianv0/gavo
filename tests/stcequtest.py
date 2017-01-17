"""
Tests for the STC equivalence mechanism.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import stc
from gavo import utils
from gavo.stc import eq




class EquivalenceBasicsTest(testhelpers.VerboseTest):
	"""tests for equivalence policies.
	"""
	def testBadKeysEquivalent(self):
		self.assertRaises(ValueError, eq.KeysEquivalent, "")
		self.assertRaises(ValueError, eq.KeysEquivalent, 
			";os.system('rm -rf /')")

	def testTrivial(self):
		ep = stc.EquivalencePolicy([])
		self.failUnless(ep.match(None, "foo"))


def _equPolSTCSmatch(policy, stcs1, stcs2):
	return policy.match(
		stc.parseSTCS(stcs1).astroSystem,
		stc.parseSTCS(stcs2).astroSystem)


class EquivalenceTest(testhelpers.VerboseTest):
# Define a policy and samples.
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		stcs1, stcs2 = sample
		self.failUnless(_equPolSTCSmatch(self.policy, stcs1, stcs2),
			"%r and %r are not considered equivalent but should be"%(
				stcs1, stcs2))


class NonEquivalenceTest(testhelpers.VerboseTest):
# Define a policy and samples.
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		stcs1, stcs2 = sample
		self.failIf(_equPolSTCSmatch(self.policy, stcs1, stcs2),
			"%r and %r are considered equivalent but should not be"%(
				stcs1, stcs2))


class SimpleEquivalenceTest(EquivalenceTest):
	policy = stc.EquivalencePolicy(
		["timeFrame.timeScale", "spaceFrame.refFrame"])

	samples = [
		("Position ICRS", "Position ICRS"),
		("Position ICRS BARYCENTER", "Position ICRS TOPOCENTER"),
		("Position ICRS", "Time TT Position ICRS"),
		("Position ICRS", "Position UNKNOWNFrame"),
		("Position ICRS", "Time TT"),
		("Position FK5 J1980.0", "Position FK5 J1990.0"),
	]


class SimpleNonEquivalenceTest(NonEquivalenceTest):
	policy = stc.EquivalencePolicy(
		["timeFrame.timeScale", "spaceFrame.refFrame"])

	samples = [
		("Position ICRS", "Position FK5"),
		("Time TT Position ICRS", "Time UTC Position ICRS"),
	]


class DefaultEquivalenceTest(EquivalenceTest):
	policy = stc.defaultPolicy

	samples = [
		("Position ICRS", "Position ICRS"),
		("Position ICRS", "Position FK5"),
		("Position ICRS BARYCENTER", "Position ICRS TOPOCENTER"),
		("Position ICRS", "Time TT Position ICRS"),
		("Position ICRS", "Position UNKNOWNFrame"),
		("Position ICRS", "Time TT"),
		("Spectral BARYCENTER", "Spectral"),
		("Spectral BARYCENTER", "Redshift RADIO"),
		("Redshift", "Redshift OPTICAL"),
		("Redshift", "Redshift REDSHIFT"),
	]


class DefaultNonEquivalenceTest(NonEquivalenceTest):
	policy = stc.defaultPolicy

	samples = [
		("Position ICRS", "Position FK4"),
		("Time TT Position ICRS", "Time UTC Position ICRS"),
		("Position FK5 J1980.0", "Position FK5 J1990.0"),
		("Spectral BARYCENTER", "Spectral TOPOCENTER"),
		("Redshift BARYCENTER", "Redshift TOPOCENTER"),
		("Redshift OPTICAL", "Redshift RADIO"),
		("Redshift VELOCITY", "Redshift REDSHIFT"),
	]


if __name__=="__main__":
	testhelpers.main(SimpleEquivalenceTest)

