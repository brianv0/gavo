"""
Tests for resource descriptor handling
"""

import unittest
import os

import gavo
from gavo import config
import gavo.parsing
from gavo.parsing import importparser

gavo.parsing.verbose = True

class MetaTest(unittest.TestCase):
	"""Test for correct interpretation of meta information.
	"""
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


class ValidationTest(unittest.TestCase):
	"""Test for validation of values.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))

	def testNumeric(self):
		"""tests for correct evaluation of numeric limits.
		"""
		recDef = self.rd.getTableDefByName("valspec")
		self.assert_(recDef.validate({"numeric": 10})==None)
		self.assert_(recDef.validate({"numeric": 15})==None)
		self.assert_(recDef.validate({"numeric": 13})==None)
		self.assertRaises(gavo.ValidationError, 
			recDef.validate, {"numeric": 16})
		self.assertRaises(gavo.ValidationError, 
			recDef.validate, {"numeric": 1})
		try:
			recDef.validate({"numeric": 1})
		except gavo.ValidationError, ex:
			self.assertEqual(ex.fieldName, "numeric")
	
	def testOptions(self):
		"""tests for correct interpretation of values enumeration.
		"""
		recDef = self.rd.getTableDefByName("valspec")
		self.assert_(recDef.validate({"numeric": 10, "enum": "bad"})==None)
		self.assert_(recDef.validate({"numeric": 10, "enum": "gruesome"})==None)
		self.assertRaises(gavo.ValidationError, recDef.validate, 
			{"numeric": 10, "enum": "excellent"})
		try:
			recDef.validate({"numeric": 10, "enum": "terrible"})
		except gavo.ValidationError, ex:
			self.assertEqual(ex.fieldName, "enum")
	
	def testOptional(self):
		"""tests for correct validation of non-optional values.
		"""
		recDef = self.rd.getTableDefByName("valspec")
		rec = {}
		try:
			recDef.validate(rec)
		except gavo.ValidationError, ex:
			self.assertEqual(ex.fieldName, "numeric")
		rec["enum"] = "abysimal"
		self.assertRaises(gavo.ValidationError, recDef.validate,
			rec)
		rec["numeric"] = 14
		self.assert_(recDef.validate(rec)==None)


	

if __name__=="__main__":
	unittest.main()
