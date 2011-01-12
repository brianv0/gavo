"""
Tests for ADQL user defined functions and Region expressions.
"""

import re
import unittest

from gavo import adql
from gavo import rscdesc
from gavo.helpers import testhelpers
from gavo.protocols import adqlglue
from gavo.protocols import simbadinterface # for getSesame registration
from gavo.adql import nodes 
from gavo.adql import ufunctions 


class BasicTest(unittest.TestCase):
	def testRaising(self):
		self.assertRaises(adql.UfuncError, adql.parseToTree,
			"SELECT x FROM y WHERE gavo_foo(8)=7")

	def testFlattening(self):
		self.assertEqual(
			adql.parseToTree("SELECT x FROM y WHERE 1=gavo_match('x.*', frob)"
				).flatten(),
			"SELECT x FROM y WHERE 1 = (CASE WHEN frob ~ 'x.*' THEN 1 ELSE 0)")


class _UfuncDefinition(testhelpers.TestResource):
	def make(self, nodeps):
		@adql.userFunction("testingXXX",
			"(x INTEGER) -> INTEGER",
			"""
			This function returns its argument decreased by one.
			
			This is the end.
			""")
		def _(args):
			if len(args)!=1:
				raise adql.UfuncError("gavo_testingXXX takes only a single argument")
			return "(%s+1)"%nodes.flatten(args[0])
		return True
	
	def clean(self, ignored):
		del ufunctions.UFUNC_REGISTRY["GAVO_TESTINGXXX"]


class UfuncDefTest(testhelpers.VerboseTest):
	resources = [("ufunc_defined", _UfuncDefinition())]

	def testUfuncMeta(self):
		f = ufunctions.UFUNC_REGISTRY["GAVO_TESTINGXXX"]
		self.assertEqual(f.adqlUDF_name, "gavo_testingXXX")
		self.assertEqual(f.adqlUDF_signature, 
			"gavo_testingXXX(x INTEGER) -> INTEGER")
		self.assertEqual(f.adqlUDF_doc, "This function returns its argument"
			" decreased by one.\n\nThis is the end.")
	
	def testFlattening(self):
		self.assertEqual(
			adql.parseToTree("SELECT GAVO_TESTINGXXX(frob) FROM x"
				).flatten(),
			"SELECT (frob+1) FROM x")


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
		# Simbad applies proper motions to objects.  Let's just
		# use REs to check, this will be ok for a few years.
		self.assert_(re.match("SELECT x FROM y WHERE 1 ="
			r" CONTAINS\(POINT\(68.98.*, 16.50.*\)"
			", CIRCLE\(10, 10, 1\)\)", adql.flatten(t)))
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS("
			"REGION('simbad Wozzlfoo7xx'), CIRCLE('ICRS', 10, 10, 1))")


if __name__=="__main__":
	testhelpers.main(UfuncDefTest)
