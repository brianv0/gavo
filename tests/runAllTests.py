"""
Runs all known tests on the main gavo code tree (i.e. .../gavo).

This script *asssumes* it is run from tests subdirectory of the code
tree and silently won't work (properly) otherwise.
"""

import unittest
import doctest
import glob
import os
import subprocess
import warnings

from gavo.helpers import testhelpers

from gavo.imp import testresources

warnings.simplefilter("ignore", category=UserWarning)


unittestModules = [n[:-3] for n in glob.glob("*test.py")]


def hasDoctest(fName):
	f = open(fName)
	tx = f.read()
	f.close()
	return "doctest.testmod" in tx


def getDoctests():
	doctests = []
	for dir, dirs, names in os.walk("../gavo"):
		parts = dir.split("/")[1:]
		for name in [n for n in names if n.endswith(".py")]:
			if hasDoctest(os.path.join(dir, name)):
				name = ".".join(parts+[name[:-3]])
				doctests.append(doctest.DocTestSuite(name))
	return unittest.TestSuite(doctests)


def runTrialTests():
	"""runs trial-based tests, suppressing output, but raising an error if
	any of the tests failed.
	"""
	try:
		del os.environ["GAVO_INPUTSDIR"]
	except KeyError:
		pass
	subprocess.call("trial --reporter text test_*.py", shell=True)
	

if __name__=="__main__":
	unittestSuite = testresources.TestLoader().loadTestsFromNames(
		unittestModules)
	runner = unittest.TextTestRunner(verbosity=1)
 	runner.run(unittest.TestSuite([unittestSuite, getDoctests()]))
	print "\nTrial-based tests:"
	runTrialTests()
