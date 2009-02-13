"""
Some unit tests not yet fitting anywhere else.
"""

import cStringIO
import datetime
import os
import shutil
import tempfile
import unittest

from gavo import base
from gavo import rscdef
from gavo import rscdesc
from gavo.base import valuemappers
from gavo.helpers import filestuff
from gavo.utils import mathtricks

import testhelpers


class MapperTest(unittest.TestCase):
	"""collects tests for votable/html value mappers.
	"""
	def testJdMap(self):
		colProps = {"sample": datetime.datetime(2005, 6, 4, 23, 12, 21),
			"unit": "d"}
		mapper = valuemappers.datetimeMapperFactory(colProps)
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
	
	def testStandardMappers(self):
		def assertMappingResult(dataField, value, literal):
			cp = valuemappers.ColProperties(dataField)
			cp["sample"] = value
			self.assertEqual(literal,
				unicode(valuemappers.defaultMFRegistry.getMapper(cp)(value)))
			
		for dataField, value, literal in [
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="Y-M-D"),
				datetime.date(2003, 5, 4), "2003-05-04"),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="yr"),
				datetime.date(2003, 5, 4), '2003.33607118'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="d"),
				datetime.date(2003, 5, 4), '2452763.5'),
			(base.makeStruct(rscdef.Column, name="d", type="timestamp", unit="d"),
				datetime.datetime(2003, 5, 4, 20, 23), '2452764.34931'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="d", 
					ucd="VOX:Image_MJDateObs"),
				datetime.date(2003, 5, 4), '52763.0'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="yr"),
				None, ' '),
			(base.makeStruct(rscdef.Column, name="d", type="integer"),
				None, '-2147483648'),
		]:
			assertMappingResult(dataField, value, literal)


class RenamerDryTest(unittest.TestCase):
	"""tests for some aspects of the file renamer without touching the file system.
	"""
	def testSerialization(self):
		"""tests for correct serialization of clobbering renames.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', '2': '3', '1': '2'}
		self.assertEqual(f.makeRenameProc(fileMap),
			[('b', 'c'), ('a', 'b'), ('2', '3'), ('1', '2')])
	
	def testCycleDetection(self):
		"""tests for cycle detection in renaming recipies.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', 'c': 'a'}
		self.assertRaises(filestuff.Error, f.makeRenameProc, fileMap)


class RenamerWetTest(unittest.TestCase):
	"""tests for behaviour of the file renamer on the file system.
	"""
	def setUp(self):
		def touch(name):
			f = open(name, "w")
			f.close()
		self.testDir = tempfile.mkdtemp("testrun")
		for fName in ["a.fits", "a.txt", "b.txt", "b.jpeg", "foo"]:
			touch(os.path.join(self.testDir, fName))

	def tearDown(self):
		shutil.rmtree(self.testDir, onerror=lambda exc: None)

	def testOperation(self):
		"""tests an almost-realistic application
		"""
		f = filestuff.FileRenamer.loadFromFile(
			cStringIO.StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		found = set(os.listdir(self.testDir))
		expected = set(["b.fits", "b.txt", "c.txt", "c.jpeg", "bar"])
		self.assertEqual(found, expected)
	
	def testNoClobber(self):
		"""tests for effects of repeated application.
		"""
		f = filestuff.FileRenamer.loadFromFile(
			cStringIO.StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		self.assertRaises(filestuff.Error, f.renameInPath, self.testDir)


class TimeCalcTest(testhelpers.VerboseTest):
	"""tests for time transformations.
	"""
	def testJYears(self):
		self.assertEqual(mathtricks.jYearToDateTime(1991.25),
			datetime.datetime(1991, 04, 02, 13, 30, 00))
		self.assertEqual(mathtricks.jYearToDateTime(2005.0),
			datetime.datetime(2004, 12, 31, 18, 0))
	
	def testRoundtrip(self):
		for yr in range(2000):
			self.assertAlmostEqual(2010+yr/1000., mathtricks.dateTimeToJYear(
				mathtricks.jYearToDateTime(2010+yr/1000.)), 7,
				"Botched %f"%(2010+yr/1000.))


if __name__=="__main__":
	testhelpers.main(TimeCalcTest)
