"""
Tests for the various modules in utils.
"""

from gavo import utils
from gavo.utils import algotricks

import testhelpers

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


if __name__=="__main__":
	testhelpers.main(PrefixTest)
