"""
Tests for resource descriptor handling
"""

import unittest
import os

from gavo import config
import gavo.parsing
from gavo.parsing import importparser

gavo.parsing.verbose = True

class MetaTest(unittest.TestCase):
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
		config.setMeta("test.fromConfig", "from Config")
	
	def testMetaAttachment(self):
		"""tests for proper propagation of meta information.
		"""
		recDef = self.rd.getDataById("metatest").getRecordDefByName("noname")
		self.assert_(str(recDef.getMeta("test.inRec")), "from Rec")
		self.assert_(str(recDef.getMeta("test.inRd")), "from Rd")
		self.assert_(str(recDef.getMeta("test.fromConfig")), "from Config")
		self.assertEqual(recDef.getMeta("test.doesNotExist"), None)


if __name__=="__main__":
	unittest.main()
