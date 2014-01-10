"""
Tests for the configuration infrastructure.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os

from gavo.helpers import testhelpers

from gavo import base
from gavo.utils import fancyconfig


# The tests from fancyconfig itself
fcTest = fancyconfig._getTestSuite()


class UserConfigTest(testhelpers.VerboseTest):
	def testSimpleResolution(self):
		s = base.resolveCrossId("%#_test-script", None)
		self.assertEqual(s.name, "test instrumentation")
	
	def testOverriding(self):
		userConfigPath = os.path.join(
			base.getConfig("configDir"), "userconfig.rd")
		base.caches.clearForName(userConfigPath[:-3])
		with open(userConfigPath, "w") as f:
			f.write("""<resource schema="__system"><script id="_test-script"
				lang="SQL" name="test exstrumentation" type="preIndex"/>
				</resource>\n""")
		try:
			s = base.resolveCrossId("%#_test-script", None)
			self.assertEqual(s.name, "test exstrumentation")
		finally:
			os.unlink(userConfigPath)

	def testNonexisting(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"Element with id 'dashiergibtsnicht' could not be located"
			" in etc/userconfig.rd",
			base.resolveCrossId,
			("%#dashiergibtsnicht", None))


if __name__=="__main__":
	testhelpers.main(UserConfigTest)
