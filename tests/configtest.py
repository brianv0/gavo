"""
Tests for the configuration infrastructure.
"""

from gavo.utils import fancyconfig


# The tests from fancyconfig itself
fcTest = fancyconfig._getTestSuite()


if __name__=="__main__":
	import unittest
	unittest.main()
