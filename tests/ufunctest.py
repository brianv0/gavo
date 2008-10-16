"""
Tests for ADQL user defined functions and Region expressions.
"""

import unittest

from gavo import adql
from gavo import adqlglue
from gavo.adql import ufunctions # magic registration of ufuncs takes place
                                 # during import

import testhelpers


class BasicTest(unittest.TestCase):
	"""tests for some basic properties of user defined functions.
	"""
	def testRaising(self):
		"""tests for plausible exceptions.
		"""
		self.assertRaises(adql.UfuncError, adql.parseToTree,
			"SELECT x FROM y WHERE gavo_foo(8)=7")


class RegionTest(unittest.TestCase):
	"""tests for sane parsing of our default region expressions.
	"""
	def testRaising(self):
		"""tests for plausible exceptions.
		"""
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS(REGION('78y'), REGION('zzy9'))")
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS(REGION(dbColumn || otherColumn),"
			" CIRCLE('ICRS', 10, 10 ,2))")

	def testSimbad(self):
		"""tests for the simbad region.
		"""
		t = adql.parseToTree("SELECT x FROM y WHERE 1=CONTAINS("
			"REGION('simbad Aldebaran'), CIRCLE('ICRS', 10, 10, 1))")
		self.assertEqual(adql.flatten(t), "SELECT x FROM y WHERE 1 ="
			" CONTAINS ( POINT ( 'ICRS' , 68.9801611000 , 16.5093014000 )"
			" , CIRCLE ( 'ICRS' , 10 , 10 , 1 ) )")
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS("
			"REGION('simbad Wozzlfoo7xx'), CIRCLE('ICRS', 10, 10, 1))")


if __name__=="__main__":
	testhelpers.main(RegionTest)
