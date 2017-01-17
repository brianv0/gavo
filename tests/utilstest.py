"""
Tests for the various modules in utils.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import utils
from gavo.utils import algotricks
from gavo.utils import stanxml
from gavo.utils import typeconversions


class TopoSortTest(testhelpers.VerboseTest):
	def testEmpty(self):
		self.assertEqual(algotricks.topoSort([]), [])

	def testSimpleGraph(self):
		self.assertEqual(algotricks.topoSort([(1,2), (2,3), (3,4)]), [1,2,3,4])

	def testComplexGraph(self):
		self.assertEqual(algotricks.topoSort([(1,2), (2,3), (1,3), (3,4),
			(1,4), (2,4)]), [1,2,3,4])

	def testCyclicGraph(self):
		self.assertRaisesWithMsg(ValueError, "Graph not acyclic, cycle: 1->2", 
			algotricks.topoSort, ([(1,2), (2,1)],))


class PrefixTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	def _runTest(self, args):
		s1, s2, prefixLength = args
		self.assertEqual(utils.commonPrefixLength(s1, s2), prefixLength)
	
	samples = [
		("abc", "abd", 2),
		("abc", "a", 1),
		("abc", "", 0),
		("", "abc", 0),
		("a", "abc", 1),
		("z", "abc", 0),]


class IdManagerTest(testhelpers.VerboseTest):
	"""tests for working id manager.
	"""
	def setUp(self):
		self.im = utils.IdManagerMixin()

	def testNoDupe(self):
		testob = 1
		self.assertEqual(self.im.makeIdFor(testob), 
			utils.intToFunnyWord(id(testob)))
		self.assertEqual(self.im.makeIdFor(testob), None)

	def testRetrieve(self):
		testob = "abc"
		theId = self.im.makeIdFor(testob)
		self.assertEqual(self.im.getIdFor(testob), theId)
	
	def testRefRes(self):
		testob = "abc"
		theId = self.im.makeIdFor(testob)
		self.assertEqual(self.im.getForId(theId), testob)
	
	def testUnknownOb(self):
		self.assertRaises(utils.NotFoundError, self.im.getIdFor, 1)

	def testUnknownId(self):
		self.assertRaises(utils.NotFoundError, self.im.getForId, "abc")

	def testSuggestion(self):
		testob = object()
		givenId = self.im.makeIdFor(testob, "ob1")
		self.assertEqual(givenId, "ob1")
		testob2 = object()
		id2 = self.im.makeIdFor(testob2, "ob1/")
		self.assertEqual(id2, "ob10")
		self.failUnless(testob is self.im.getForId("ob1"))
		self.failUnless(testob2 is self.im.getForId("ob10"))


class LoadModuleTest(testhelpers.VerboseTest):
	"""tests for cli's module loader.
	"""
	def testLoading(self):
		ob = utils.loadInternalObject("utils.codetricks", "loadPythonModule")
		self.failUnless(hasattr(ob, "__call__"))
	
	def testNotLoading(self):
		self.assertRaises(ImportError, utils.loadInternalObject, "noexist", "u")
	
	def testBadName(self):
		self.assertRaises(AttributeError, utils.loadInternalObject, 
			"utils.codetricks", "noexist")


class CachedGetterTest(testhelpers.VerboseTest):
	def testNormal(self):
		g = utils.CachedGetter(lambda c: [c], 3)
		self.assertEqual(g(), [3])
		g().append(4)
		self.assertEqual(g(), [3, 4])
	
	def testMortal(self):
		g = utils.CachedGetter(lambda c: [c], 3,
			isAlive=lambda l: len(l)<3)
		g().append(4)
		self.assertEqual(g(), [3,4])
		g().append(5)
		self.assertEqual(g(), [3])


class SimpleTextTest(testhelpers.VerboseTest):
	def testFeatures(self):
		with testhelpers.testFile("test.txt",
				r"""# Test File\
	this is stripped   
An empty line is ignored

Contin\
uation lines \
# (a comment in between is ok)
  are concatenated
""")    as fName:
			with open(fName) as f:
				res = list(utils.iterSimpleText(f))

		self.assertEqual(res, [
			(2, "this is stripped"),
			(3, "An empty line is ignored"),
			(8, "Continuation lines are concatenated")])

	def testNoTrailingBackslash(self):
		with testhelpers.testFile("test.txt",
				"""No
non-finished\\
continuation\\""") as fName:
			with open(fName) as f:
				self.assertRaisesWithMsg(utils.SourceParseError,
					"At line 3: File ends with a backslash",
					lambda f: list(utils.iterSimpleText(f)),
					(f,))


class TypeConversionTest(testhelpers.VerboseTest):
	def testDPArray(self):
		self.assertEqual(
			typeconversions.sqltypeToVOTable("double precision[2]"),
			 ('double', '2', None))


if __name__=="__main__":
	testhelpers.main(CachedGetterTest)
