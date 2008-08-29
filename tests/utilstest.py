"""
Some tests for stuff in utils
"""

import sys
import traceback
import unittest

import gavo
from gavo import utils

import testhelpers


class TestReraise(unittest.TestCase):
	"""Tests for keeping the stack when reraising mogrified exceptions.
	"""
# This is in here because raiseTb used to be in utils.  Well, let's move
# it some day.
	def testOneLevel(self):
		"""test for simple reraising.
		"""
		def bar():
			z = 1/0

		def foo(arg):
			try:
				bar()
			except Exception, msg:
				gavo.raiseTb(gavo.Error, "Trouble in foo: %s"%msg)

		try:
			foo("xy")
		except gavo.Error:
			stackTuples = traceback.extract_tb(sys.exc_info()[-1])
		self.assertEqual(stackTuples[-1][-1], "z = 1/0")


class TestBisectMin(unittest.TestCase):
	"""Tests for naive minimum finding by bisection.
	"""
	def testGood(self):
		"""tests for finding the minimum of "good" functions.
		"""
		self.assertAlmostEqual(utils.findMinimum(lambda x: x**2, -10, 5), 0)
		self.assertAlmostEqual(utils.findMinimum(lambda x: x**2, -5, 10), 0)
		self.assertAlmostEqual(utils.findMinimum(lambda x: x**2, -0.1, 100), 0)
		self.assertAlmostEqual(utils.findMinimum(lambda x: (x-10)**2, -100, 100), 
			10)
		self.assertAlmostEqual(utils.findMinimum(lambda x: (x-10)**2+4*x, 
			-100, 100), 8, 7)
	
	def testConstant(self):
		"""tests for proper handling of the constant function.
		"""
		self.assertAlmostEqual(utils.findMinimum(lambda x: 2, -10, 5), -10, 6)


class TestDeferredDict(unittest.TestCase):
	"""Tests for deferred construction/calling of things.
	"""
	def testWithFunction(self):
		def f(a, b, callCount=[0]):
			callCount[0] += 1
			return (a, b, callCount[0])

		d = utils.DeferringDict()
		d["foo"] = (f, (1, 2))
		self.assertEqual(d["foo"], (1, 2, 1))
		self.assertEqual(d["foo"], (1, 2, 1), "DeferredDict doesn't cache results")
	
	def testWithClass(self):
		class Foo(object):
			consCount = [0]
			def __init__(self):
				self.consCount[0] += 1
		d = utils.DeferringDict()
		d["foo"] = Foo
		d["bar"] = Foo
		o1 = d["foo"]
		o2 = d["foo"]
		self.assert_(o1 is o2)
		self.assertEqual(Foo.consCount[0], 1)
		o3 = d["bar"]
		self.failIf(o1 is o3)
		self.assertEqual(Foo.consCount[0], 2)


if __name__=="__main__":
	testhelpers.main(TestDeferredDict, "test")
