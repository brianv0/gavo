"""
Tests for the various modules in utils.
"""

from gavo import utils
from gavo.utils import algotricks
from gavo.utils import stanxml

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
		self.assertEqual(givenId, "ob")
		testob2 = object()
		id2 = self.im.makeIdFor(testob2, "ob1")
		self.assertEqual(id2, "ob0")
		self.failUnless(testob is self.im.getForId("ob"))
		self.failUnless(testob2 is self.im.getForId("ob0"))


class StanXMLTest(testhelpers.VerboseTest):
	"""tests for our ad hoc XML DOM.
	"""
	class E(object):
		class LocalElement(stanxml.Element):
			namespace = "http://bar.com"
			local = mayBeEmpty = True
		class A(LocalElement):
			a_x = None
		class B(LocalElement):
			a_y = None
		class NSElement(stanxml.Element):
			namespace = "http://foo.com"
		class C(NSElement):
			a_z = "ab"

	def testTraversal(self):
		tree = self.E.A[self.E.B, self.E.B, self.E.A]
		def record(elName, content, attrDict, childIter):
			return (elName,
				[c.traverse(record) for c in childIter])
		self.assertEqual(tree.traverse(record),
			('A', [('B', []), ('B', []), ('A', [])]))
	
	def testSimpleRender(self):
		tree = self.E.A[self.E.B, self.E.B, self.E.A]
		self.assertEqual(tree.render(), '<A><B /><B /><A /></A>')
	
	def testRenderWithText(self):
		E = self.E
		tree = E.A[E.C["arg"], E.C(z="c")[E.B["muss"], E.A]]
		self.assertEqual(tree.render(), 
			'<A><ns0:C z="ab" xmlns:ns0="http://foo.com">arg</ns0:C><ns0:C z='
			'"c" xmlns:ns0="http://foo.com"><B>muss</B><A /></ns0:C></A>')

if __name__=="__main__":
	testhelpers.main(StanXMLTest)
