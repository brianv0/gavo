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
	def testOneLevel(self):
		"""test for simple reraising.
		"""
		def bar():
			z = 1/0

		def foo(arg):
			try:
				bar()
			except Exception, msg:
				utils.raiseTb(gavo.Error, "Trouble in foo: %s"%msg)

		try:
			foo("xy")
		except gavo.Error:
			stackTuples = traceback.extract_tb(sys.exc_info()[-1])
		self.assertEqual(stackTuples[-1][-1], "z = 1/0")


if __name__=="__main__":
	unittest.main()
