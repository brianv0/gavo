"""
Tests for value mapping

[The stuff tested here will be changed significantly RSN]
"""

import datetime
import urllib

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.base import valuemappers
from gavo.protocols import products
from gavo.utils import pgsphere


class MapperTest(testhelpers.VerboseTest):
	def assertMapsTo(self, colDef, inValue, expectedValue):
		dataField = base.parseFromString(rscdef.Column, 
			"<column %s</column>"%colDef)
		cp = valuemappers.VColDesc(dataField)
		cp["sample"] = inValue
		res = valuemappers.defaultMFRegistry.getMapper(cp)(inValue)
		if isinstance(expectedValue, float):
			self.assertAlmostEqual(expectedValue, res, places=3)
		else:
			self.assertEqual(expectedValue, res)


class MapperMiscTest(testhelpers.VerboseTest):
# TODO: Rationalize, split up...
	def testJdMap(self):
		colDesc = {"sample": datetime.datetime(2005, 6, 4, 23, 12, 21),
			"unit": "d", "ucd": None}
		mapper = valuemappers.datetimeMapperFactory(colDesc)
		self.assertAlmostEqual(2453526.4669097224,
			mapper(datetime.datetime(2005, 6, 4, 23, 12, 21)))
		self.assertAlmostEqual(2434014.6659837961,
			mapper(datetime.datetime(1952, 1, 3, 3, 59, 1)))
		self.assertAlmostEqual(2451910.0,
			mapper(datetime.datetime(2000, 12, 31, 12, 00, 00)))
		self.assertAlmostEqual(2451909.999988426,
			mapper(datetime.datetime(2000, 12, 31, 11, 59, 59)))

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
	

class StandardMapperTest(MapperTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self.assertMapsTo(*sample)

	samples = [
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
		('name="d" type="date" unit="yr">',
			None, None),
		('name="d" type="integer">',
			None, None),
		('name= "b" type= "sbox">', pgsphere.SBox(
			pgsphere.SPoint(0.2, -0.1), pgsphere.SPoint(0.5, 0.2)),
			"PositionInterval UNKNOWN 11.4591559026 -5.7295779513"
			" 28.6478897565 11.4591559026"),
	]


class ProductMapperTest(MapperTest):
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


class STCMappingTest(MapperTest):
	def testSimple(self):
		td = base.parseFromString(rscdef.TableDef, """<table>
			<stc>Position FK5 TOPOCENTER [pos]</stc>
			<column name="pos" type="spoint"/></table>""")
		table = rsc.TableForDef(td, rows=[{"pos": pgsphere.SPoint(0.2, 0.6)}])
		res = list(valuemappers.SerManager(table).getMappedValues())[0]
		self.failUnless(res["pos"].startswith("Position FK5 TOPOCENTER"))


if __name__=="__main__":
	testhelpers.main(ProductMapperTest)
