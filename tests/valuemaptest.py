"""
Tests for value mapping

[The stuff tested here will be changed significantly soon]
"""

import datetime

from gavo import base
from gavo import rscdef
from gavo.base import valuemappers
from gavo.helpers import testhelpers
from gavo.utils import pgsphere


class MapperTest(testhelpers.VerboseTest):
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
	

class StandardMapperTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		structArgs, value, mapped = sample
		dataField = base.makeStruct(rscdef.Column, **structArgs)
		cp = valuemappers.VColDesc(dataField)
		cp["sample"] = value
		res = valuemappers.defaultMFRegistry.getMapper(cp)(value)
		if isinstance(mapped, float):
			self.assertAlmostEqual(mapped, res, places=3)
		else:
			self.assertEqual(mapped, res)

	samples = [
		({"name":"d", "type":"date", "unit":"Y-M-D"},
			datetime.date(2003, 5, 4), "2003-05-04"),
		({"name":"d", "type":"date", "unit":"yr"},
			datetime.date(2003, 5, 4), 2003.33607118),
		({"name":"d", "type":"date", "unit":"d"},
			datetime.date(2003, 5, 4), 2452763.5),
		({"name":"d", "type":"timestamp", "unit":"d"},
			datetime.datetime(2003, 5, 4, 20, 23), 2452764.34931),
		({"name":"d", "type":"date", "unit":"d", 
				"ucd":"VOX:Image_MJDateObs"},
			datetime.date(2003, 5, 4), 52763.0),
		({"name":"d", "type":"date", "unit":"yr"},
			None, None),
		({"name":"d", "type":"integer"},
			None, None),
		({"name": "b", "type": "sbox"}, pgsphere.SBox(
			pgsphere.SPoint(0.2, -0.1), pgsphere.SPoint(0.5, 0.2)),
			"PositionInterval ICRS 11.4591559026 -5.7295779513"
			" 28.6478897565 11.4591559026"),
	]


if __name__=="__main__":
	testhelpers.main(StandardMapperTest)
