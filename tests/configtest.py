"""
Tests for the configuration infrastructure.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
from cStringIO import StringIO

from gavo.helpers import testhelpers

from gavo import base
from gavo.base import config
from gavo.utils import fancyconfig


# The tests from fancyconfig itself
fcTest = fancyconfig._getTestSuite()


class RCParseTest(testhelpers.VerboseTest):
# NOTE: if these things actually change something in config, they
# must undo these changes (at least on success)

	def _parseFragment(self, fragment):
		config._config.addFromFp(StringIO(fragment), origin="testsuite")

	def testAuthorityRejected(self):
		self.assertRaisesWithMsg(fancyconfig.BadConfigValue,
			"[ivoa]authority must match [a-zA-Z0-9][a-zA-Z0-9._~-]{2,}$ ('more than three normal characters')",
			self._parseFragment,
			("[ivoa]\nauthority:ivo://x-invalid\n",))


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
