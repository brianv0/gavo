"""
Tests for resource descriptor handling
"""

import cStringIO
import os
import unittest

from gavo import config
from gavo import datadef
from gavo import meta
from gavo import nullui
from gavo.parsing import columngrammar
from gavo.parsing import importparser
from gavo.parsing import resource
import gavo
import gavo.parsing

gavo.parsing.verbose = True


class MetaTest(unittest.TestCase):
	"""Test for correct interpretation of meta information.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
		config.addMeta("test.fromConfig", "from Config")
	
	def testMetaAttachment(self):
		"""tests for proper propagation of meta information.
		"""
		recDef = self.rd.getDataById("metatest").getRecordDefByName("noname")
		self.assert_(str(recDef.getMeta("test.inRec")), "from Rec")
		self.assert_(str(recDef.getMeta("test.inRd")), "from Rd")
		self.assert_(str(recDef.getMeta("test.fromConfig")), "from Config")
		self.assertEqual(recDef.getMeta("test.doesNotExist"), None)

	def testComplexMeta(self):
		"""tests for handling of complex meta items.
		"""
		data = self.rd.getDataById("metatest")
		data.addMeta("testStatus", meta.makeMetaValue("I'm so well I could cry",
			infoValue="OK", type="info"))
		self.assert_(isinstance(data.getMeta("testStatus").children[0], 
			meta.InfoItem))
		self.assertEqual(data.getMeta("testStatus").children[0].infoValue, "OK")
		self.assertEqual(str(data.getMeta("testStatus")),
			"I'm so well I could cry")


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


class SimpleDataTest(unittest.TestCase):
	"""Test for building of simple tables.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
	
	def testEmptySimpleDataDesc(self):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		self.assertEqual(str(dataDesc.getMeta("test.inRd")), "from Rd")

	def testSimpleDataDescWithParse(self):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [
			datadef.DataField(dest="foo", source="1-4"),
			datadef.DataField(dest="bar", source="5-7")])
		dataDesc.set_Grammar(columngrammar.ColumnGrammar())
		inData = resource.InternalDataSet(dataDesc, 
			dataSource=cStringIO.StringIO("12.35.3\n0.120.7\n"))
		self.assertAlmostEqual(inData.getPrimaryTable().rows[0]["foo"], 12.3)
		outData = resource.parseFromTable([
			datadef.DataField(dest="baz", source="bar")],
			inData)
		self.assertAlmostEqual(outData.getPrimaryTable().rows[0]["baz"], 5.3)

if __name__=="__main__":
	unittest.main()
