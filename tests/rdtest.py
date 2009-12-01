"""
Tests for resource descriptor handling
"""

import cStringIO
import os
import unittest

from gavo import base
from gavo import rscdef
from gavo import rscdesc
from gavo.base import meta
from gavo.protocols import basic
from gavo.protocols import tap
from gavo.rscdef import tabledef

import testhelpers


class MetaTest(unittest.TestCase):
	"""Test for correct interpretation of meta information.
	"""
	def setUp(self):
		# get a fresh copy of the RD since we're modifying the thing
		self.rd = testhelpers.getTestRD()
		meta.configMeta.addMeta("test.fromConfig", "from Config")
	
	def testMetaAttachment(self):
		"""tests for proper propagation of meta information.
		"""
		recDef = self.rd.getTableDefById("noname")
		self.assert_(str(recDef.getMeta("test.inRec")), "from Rec")
		self.assert_(str(recDef.getMeta("test.inRd")), "from Rd")
		self.assert_(str(recDef.getMeta("test.fromConfig")), "from Config")
		self.assertEqual(recDef.getMeta("test.doesNotExist"), None)

	def testComplexMeta(self):
		"""tests for handling of complex meta items.
		"""
		data = self.rd.getById("metatest")
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
		self.rd = testhelpers.getTestRD()

	def testNumeric(self):
		"""tests for correct evaluation of numeric limits.
		"""
		recDef = self.rd.getTableDefById("valspec")
		self.assert_(recDef.validateRow({"numeric": 10,
			"enum": None})==None)
		self.assert_(recDef.validateRow({"numeric": 15,
			"enum": None})==None)
		self.assert_(recDef.validateRow({"numeric": 13,
			"enum": None})==None)
		self.assertRaises(base.ValidationError, 
			recDef.validateRow, {"numeric": 16, "enum": None})
		self.assertRaises(base.ValidationError, 
			recDef.validateRow, {"numeric": 1, "enum": None})
		try:
			recDef.validateRow({"numeric": 1, "enum":None})
		except base.ValidationError, ex:
			self.assertEqual(ex.colName, "numeric")
	
	def testOptions(self):
		"""tests for correct interpretation of values enumeration.
		"""
		recDef = self.rd.getTableDefById("valspec")
		self.assert_(recDef.validateRow({"numeric": 10, "enum": "bad"})==None)
		self.assert_(recDef.validateRow({"numeric": 10, "enum": "gruesome"})==None)
		self.assertRaises(base.ValidationError, recDef.validateRow, 
			{"numeric": 10, "enum": "excellent"})
		try:
			recDef.validateRow({"numeric": 10, "enum": "terrible"})
		except base.ValidationError, ex:
			self.assertEqual(ex.colName, "enum")
	
	def testOptional(self):
		"""tests for correct validation of non-optional values.
		"""
		recDef = self.rd.getTableDefById("valspec")
		rec = {}
		try:
			recDef.validateRow(rec)
		except base.ValidationError, ex:
			self.assertEqual(ex.colName, "numeric")
		rec["enum"] = "abysimal"
		self.assertRaises(base.ValidationError, recDef.validateRow,
			rec)
		rec["numeric"] = 14
		self.assert_(recDef.validateRow(rec)==None)


class MacroTest(unittest.TestCase):
	"""Tests for macro evaluation within RDs.
	"""
	def testDefinedMacrosEasy(self):
		rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="test"><macDef name="foo">abc</macDef></resource>')
		self.assertEqual(rd.expand("foo is \\foo."), "foo is abc.")

	def testDefinedMacrosWhitespace(self):
		rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="test"><macDef name="foo"> a\nbc  </macDef></resource>')
		self.assertEqual(rd.expand("foo is \\foo."), "foo is  a\nbc  .")


class ViewTest(testhelpers.VerboseTest):
	"""tests for interpretation of view elements.
	"""
	def setUp(self):
		# tweak inputs such that test.rd will be found
		self.origInputs = base.getConfig("inputsDir")
		base.setConfig("inputsDir", os.getcwd())

	def tearDown(self):
		base.setConfig("inputsDir", self.origInputs)

	def testBadRefRaises(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At <internal source>, last known position: 1, 67: "
			"No field 'noexist' in table test.prodtest", 
			base.parseFromString, (tabledef.SimpleView, '<simpleView>'
			'<fieldRef table="data/test#prodtest" column="noexist"/></simpleView>'))

	def testTableDefCreation(self):
		rd = base.parseFromString(rscdesc.RD,
			'<resource schema="test2">'
			'<simpleView id="vv">'
			'<fieldRef table="data/test#prodtest" column="alpha"/>'
			'<fieldRef table="data/test#prodtest" column="delta"/>'
			'<fieldRef table="data/test#prodtest" column="object"/>'
			'<fieldRef table="data/test#adql" column="mag"/>'
			'</simpleView></resource>')
		self.assertEqual(len(rd.tables), 1)
		td = rd.tables[0]
		self.failUnless(isinstance(td, rscdef.TableDef))
		self.assertEqual(td.scripts[0].content_, 'CREATE VIEW test2.vv AS'
			' (SELECT test.prodtest.alpha,test.prodtest.delta,test.prodtest.'
			'object,test.adql.mag FROM test.prodtest NATURAL JOIN test.adql)')
		self.assertEqual(td.onDisk, True)
		self.assertEqual(rd.getById("vv"), td)


class TAP_SchemaTest(testhelpers.VerboseTest):
	"""test for working tap_schema export.

	This is another mega test that runs a bunch of functions in sequence.
	We really should have a place to put those.
	"""
	def setUp(self):
		self.rd = testhelpers.getTestRD()
		self.rd.getById("adqltable").foreignKeys.append(
			base.parseFromString(tabledef.ForeignKey, 
				'<foreignKey table="test.adql" source="foo" dest="rv"/>'))
		self.conn = base.getDBConnection("test")

	def tearDown(self):
		self.rd.getById("adqltable").foreignKeys = []
		self.conn.rollback()

	def _checkPublished(self):
		q = base.SimpleQuerier()
		tables = set(r[0] for r in
			(q.query("select table_name from TAP_SCHEMA.tables where sourcerd"
			" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(tables, set(['test.adqltable', 'test.adql']))
		columns = set(r[0] for r in
			(q.query("select column_name from TAP_SCHEMA.columns where sourcerd"
			" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(columns, 
			set([u'alpha', u'rv', u'foo', u'mag', u'delta']))
		fkeys = set(q.query("select from_table, target_table"
				" from TAP_SCHEMA.keys where sourcerd"
				" like %(rdid)s", {"rdid": self.rd.sourceId}))
		self.assertEqual(fkeys, 
			set([(u'test.adqltable', u'test.adql')]))
		fkcols = set(r for r in
			(q.query("select from_column, target_column"
				" from TAP_SCHEMA.key_columns -- where sourcerd"
				" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(fkcols, set([(u'foo', u'rv')]))

	def _checkUnpublished(self):
		q = base.SimpleQuerier()
		tables = set(r[0] for r in
			(q.query("select table_name from TAP_SCHEMA.tables where sourcerd"
			" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(tables, set())
		columns = set(r[0] for r in
			(q.query("select column_name from TAP_SCHEMA.columns where sourcerd"
			" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(columns, set())
		fkeys = set(q.query("select from_table, target_table"
				" from TAP_SCHEMA.keys where sourcerd"
				" like %(rdid)s", {"rdid": self.rd.sourceId}))
		self.assertEqual(fkeys, set())
		fkcols = set(r for r in
			(q.query("select from_column, target_column"
				" from TAP_SCHEMA.key_columns -- where sourcerd"
				" like %(rdid)s", {"rdid": self.rd.sourceId})))
		self.assertEqual(fkcols, set())

	def testMega(self):
		tap.publishToTAP(self.rd, self.conn)
		self._checkPublished()
		tap.publishToTAP(self.rd, self.conn)
		self._checkPublished()
		tap.unpublishFromTAP(self.rd, self.conn)
		self._checkUnpublished()


if __name__=="__main__":
	testhelpers.main(TAP_SchemaTest)
