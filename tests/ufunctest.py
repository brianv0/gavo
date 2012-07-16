"""
Tests for ADQL user defined functions and Region expressions.
"""

import re
import unittest

from gavo.helpers import testhelpers

from gavo import adql
from gavo import rscdesc
from gavo.protocols import adqlglue
from gavo.protocols import simbadinterface # for getSesame registration
from gavo.adql import nodes 
from gavo.adql import ufunctions 

import adqltest
import tresc


class BasicTest(unittest.TestCase):
	def testRaising(self):
		self.assertRaises(adql.UfuncError, adql.parseToTree,
			"SELECT x FROM y WHERE gavo_foo(8)=7")

	def testFlattening(self):
		self.assertEqual(
			adql.parseToTree("SELECT x FROM y WHERE 1=gavo_match('x.*', frob)"
				).flatten(),
			"SELECT x FROM y WHERE 1 = (CASE WHEN frob ~ 'x.*' THEN 1 ELSE 0 END)")


class _UfuncDefinition(testhelpers.TestResource):
	def make(self, nodeps):
		@adql.userFunction("gavo_testingXXX",
			"(x INTEGER) -> INTEGER",
			"""
			This function returns its argument decreased by one.
			
			This is the end.
			""")
		def _f1(args):
			if len(args)!=1:
				raise adql.UfuncError("gavo_testingXXX takes only a single argument")
			return "(%s+1)"%nodes.flatten(args[0])
		
		@adql.userFunction("gavo_testingYYY",
			"(x DOUBLE PRECISION) -> DOUBLE PRECISION",
			"This function will not work (since it's not defined in the DB)")
		def _f2(args):
			return None
	
	def clean(self, ignored):
		del ufunctions.UFUNC_REGISTRY["GAVO_TESTINGXXX"]
		del ufunctions.UFUNC_REGISTRY["GAVO_TESTINGYYY"]


_ufuncDefinition = _UfuncDefinition()

class UfuncDefTest(testhelpers.VerboseTest):
	resources = [("ufunc_defined", _ufuncDefinition),
		("adqlTestTable", adqltest.adqlTestTable),
		("querier", adqltest.adqlQuerier)]

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
	
	def testFlatteningTransparent(self):
		self.assertEqual(
			adql.parseToTree("SELECT GAVO_TESTINGYYY(CIRCLE('', a, b, c), u) FROM x"
				).flatten(),
			'SELECT GAVO_TESTINGYYY(CIRCLE(a, b, c), u) FROM x')

	def testQueryInSelectList(self):
		self.assertEqual(adqlglue.query(self.querier,
			"SELECT GAVO_TESTINGXXX(rV) FROM test.adql").rows[0].values(),
			[1.])

	def testQueryInWhereClause(self):
		self.assertEqual(adqlglue.query(self.querier,
			"SELECT rV FROM test.adql where GAVO_TESTINGXXX(rV)>0").rows[0].values(),
			[0.])


class BuiltinUfuncTest(testhelpers.VerboseTest):
	resources = [
		("ssaTestTable", tresc.ssaTestTable),
		("querier", adqltest.adqlQuerier)]

	def testHaswordQuery(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'rat hole')").rows,
			[{'ssa_targname': u'rat hole in the yard'}])

	def testHaswordQueryInsensitive(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'Booger')").rows,
			[{'ssa_targname': u'booger star'}])

	def testHaswordQueryBorders(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'ooger')").rows,
			[])
	
	def testHashlistSimple(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'nork') as h"
				" FROM test.hcdtest").rows,
			[{'h': 1}])

	def testHashlistBorders(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'ork') as h"
				" FROM test.hcdtest").rows,
			[{'h': 0}])

	def testHashlistNocase(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'nOrk') as h"
				" FROM test.hcdtest").rows,
			[{'h': 1}])
	
	def testNocasecmp(self):
		self.assertEqual(len(adqlglue.query(self.querier,
			"select ssa_targname FROM test.hcdtest"
				" WHERE 1=ivo_nocasecmp(ssa_targname, 'BOOGER star')").rows),
			2)

	def testNocasecmpSymm(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_nocasecmp('FooBar', 'fOObAR') as h"
				" FROM test.hcdtest").rows,
			[{'h': 1}])

	def testNocasecmpFalse(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_nocasecmp('FooBa', 'fOObAR') as h"
				" FROM test.hcdtest").rows,
			[{'h': 0}])


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
