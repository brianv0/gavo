"""
Tests for value mapping

[The stuff tested here will be changed significantly RSN]
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import urllib

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.base import valuemappers
from gavo.protocols import products
from gavo.utils import pgsphere
from gavo.web import htmltable


class AnnotationTest(testhelpers.VerboseTest):
	def testBasic(self):
		col = valuemappers.AnnotatedColumn(base.parseFromString(rscdef.Column,
			'<column name="abc" type="integer" displayHint="sf=2" required="True"/>'))
		self.assertEqual(col.original.name, "abc")
		self.assertEqual(col["name"], "abc")
		self.failUnless(col["displayHint"] is col.original.displayHint)
		self.assertEqual(col["datatype"], "int")
		self.assertEqual(col["arraysize"], '1')
		self.failUnless(col["id"] is None)

	def testSetting(self):
		col = valuemappers.AnnotatedColumn(base.parseFromString(rscdef.Column,
			'<column name="abc" type="integer" displayHint="sf=2"/>'))
		col["name"] = "changed"
		self.assertEqual(col.original.name, "abc")
		self.assertEqual(col["name"], "changed")

	def testWrapping(self):
		col = valuemappers.AnnotatedColumn(testhelpers.getTestRD(
			).getById("pgs_siaptable").getColumnByName("dateObs"))
		self.assertEqual(col["ucd"], "VOX:Image_MJDateObs")


class MapperBasicTest(testhelpers.VerboseTest):
	def testFactorySequence(self):
		m1 = lambda cp: lambda val: "First"
		m2 = lambda cp: lambda val: "Second"
		mf = valuemappers.ValueMapperFactoryRegistry()
		mf.registerFactory(m1)
		self.assertEqual(mf.getMapper({})(0), "First", 
			"Registring mappers doesn't work")
		mf.registerFactory(m2)
		self.assertEqual(mf.getMapper({})(0), "Second", 
			"Factories registred later are not tried first")


class _MapperTestBase(testhelpers.VerboseTest):
	def assertMapsTo(self, colDef, inValue, expectedValue):
		column = base.parseFromString(rscdef.Column, 
			"<column %s</column>"%colDef)
		annCol = valuemappers.AnnotatedColumn(column)
		res = valuemappers.defaultMFRegistry.getMapper(annCol)(inValue)
		if isinstance(expectedValue, float):
			self.assertAlmostEqual(expectedValue, res, places=3)
		else:
			self.assertEqual(expectedValue, res)


class _EnumeratedMapperTest(_MapperTestBase):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self.assertMapsTo(*sample)

	samples = []


class StandardMapperTest(_EnumeratedMapperTest):
	samples = [
# 0
		('name="d" type="date" unit="Y-M-D">',
			datetime.date(2003, 5, 4), "2003-05-04"),
		('name="d" type="date" unit="yr">',
			datetime.date(2003, 5, 4), 2003.33607118),
		('name="d" type="date" unit="d">',
			datetime.date(2003, 5, 4), 2452763.5),
		('name="d" type="timestamp" unit="d">',
			datetime.datetime(2003, 5, 4, 20, 23), 2452764.34931),
		('name="d" type="date" unit="d" ucd="VOX:Image_MJDateObs">',
			datetime.date(2003, 5, 4), 52763.0),
# 5
		('name="d" type="date" unit="yr">',
			None, None),
		('name="d" type="integer"><values nullLiteral="-1"/>',
			None, None),
		('name= "b" type= "sbox">', pgsphere.SBox(
			pgsphere.SPoint(0.2, -0.1), pgsphere.SPoint(0.5, 0.2)),
			"PositionInterval UNKNOWNFrame 11.4591559026 -5.7295779513"
			" 28.6478897565 11.4591559026"),
		('name="d" unit="d" type="timestamp">', 
			datetime.datetime(2005, 6, 4, 23, 12, 21),
			2453526.4669097224),
		('name="d" unit="d" type="timestamp">', 
			datetime.datetime(1952, 1, 3, 3, 59, 1),
			2434014.6659837961),
# 10
		('name="d" unit="d" type="timestamp">', 
			datetime.datetime(2000, 12, 31, 12, 00, 00),
			2451910.0),
		('name="d" unit="d" type="timestamp">', 
			datetime.datetime(2000, 12, 31, 11, 59, 59),
			2451909.999988426),
		('name="d" unit="d" xtype="mjd">',
			54320.2,
			54320.2),
	]


class HTMLMapperTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, args):
		colDef, inValue, expected, propDict = args
		column = base.parseFromString(rscdef.Column, 
			"<column %s</column>"%colDef)
		annCol = valuemappers.AnnotatedColumn(column)
		res = htmltable._htmlMFRegistry.getMapper(annCol)(inValue)
		self.assertEqual(res, expected)
		for key, value in propDict.iteritems():
			self.assertEqual(annCol[key], value)
	
	samples = [
		('name="d" unit="d" type="double precision" displayHint="type=humanDate">',
			2451909.999988426,
			"2000-12-31T11:59:59Z",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" unit="d" ucd="vox:MJDTrash" displayHint="type=humanDate">',
			51909.499988,
			"2000-12-31T11:59:58Z",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" unit="d" xtype="mjd" displayHint="type=humanDate">',
			51909.499988,
			"2000-12-31T11:59:58Z",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" unit="yr" displayHint="type=humanDate">',
			1994.25,
			"1994-04-02T07:30:00Z",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" unit="s" displayHint="type=humanDate">',
			1e9,
			"2001-09-09T01:46:40Z",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
# 05
		('name="d" type="timestamp" displayHint="type=humanDate">',
			datetime.datetime(2001, 9, 9, 1, 46, 40),
			"2001-09-09 01:46:40",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" type="date" displayHint="type=humanDate">',
			datetime.date(2001, 9, 9),
			"2001-09-09 00:00:00",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" type="date" displayHint="type=humanDay">',
			datetime.date(2001, 9, 9),
			"2001-09-09",
			{"xtype": "adql:TIMESTAMP", "arraysize": "*", "unit": ""}),
		('name="d" type="double precision" displayHint="type=dms,sf=3">',
			245.3002,
			"+245 18 00.720",
			{"unit": "d:m:s"}),
		('name="a" type="real[2]" unit="deg/pix"'
			' displayHint="displayUnit=arcsec/pix,sf=4">',
			[0.002, 0.004],
			"[7.2000, 14.4000]",
			{"unit": "arcsec/pix"}),

	]


class ProductMapperTest(_MapperTestBase):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		colDef, prodName, encoded = sample
		colDef = colDef+' type="text">'
		prodLink = "http://localhost:8080/getproduct/"+encoded
		self.assertMapsTo(colDef, prodName, prodLink)
	
	samples = [
		('name="accref"', "gobba", "gobba"),
		('name="uuxj" utype="ssa:Access.Reference"',
			"gobba", "gobba"),
		('name="uuxj" displayHint="type=product"',
			"gobba", "gobba"),
		('name="uuxj" ucd="VOX:Image_AccessReference"',
			"gobba", "gobba"),
		('name="accref"',
			"wierdo+name/goes somewhere&is/bad",
			"wierdo%2Bname/goes%20somewhere%26is/bad"),
		]


class STCMappingTest(_MapperTestBase):
	def testSimple(self):
		td = base.parseFromString(rscdef.TableDef, """<table>
			<stc>Position FK5 [pos]</stc>
			<column name="pos" type="spoint"/></table>""")
		table = rsc.TableForDef(td, rows=[{"pos": pgsphere.SPoint(0.2, 0.6)}])
		res = list(valuemappers.SerManager(table).getMappedValues())[0]
		self.failUnless(res["pos"].startswith("Position FK5"))


if __name__=="__main__":
	testhelpers.main(HTMLMapperTest)
