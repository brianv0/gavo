"""
Some tests for stuff in utils
"""

import sys
import traceback
import unittest

import gavo
from gavo import utils


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

if __name__=="__main__":
	unittest.main()
