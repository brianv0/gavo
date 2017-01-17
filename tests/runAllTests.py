"""
Runs all unit tests defined for DaCHS.

This script *asssumes* it is run from tests subdirectory of the code
tree and silently won't work (properly) otherwise.

If ran with no arguments, it executes the tests from the current directory
and then tries to locate further, data-specific unit test suites.

If ran with the single argument "data", the program will read 
$GAVO_INPUTS/__tests/__unitpaths__, interpret each line as a
inputs-relative directory name and run out-of-tree unittests there.

Location of unit tests: pyunit-based test suites are files matching
*test.py, trial-based suites are found by looking for test_*.py.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
import sys

if len(sys.argv)==1:
	pass
elif len(sys.argv)==2 and sys.argv[1]=="data":
	os.environ["GAVO_OOTTEST"] = "dontcare"
else:
	raise sys.exit(
		'%s takes zero arguments or just "data"'%sys.argv[0])

os.environ["GAVO_LOG"] = "no"

import unittest
import doctest
import glob
import subprocess
import warnings


from gavo.helpers import testhelpers

from gavo.imp import testresources

from gavo import base

warnings.simplefilter("ignore", category=UserWarning)





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
	if glob.glob("test_*.py"):
		print "\nTrial-based tests:"
		subprocess.call("trial --reporter text test_*.py", shell=True)


def runAllTests(includeDoctests=True):
	pyunitSuite = testresources.TestLoader().loadTestsFromNames(
		[n[:-3] for n in glob.glob("*test.py")])
	runner = unittest.TextTestRunner(
		verbosity=int(os.environ.get("TEST_VERBOSITY", 1)))
	if includeDoctests:
		pyunitSuite = unittest.TestSuite([pyunitSuite, getDoctests()])
 	runner.run(pyunitSuite)
	runTrialTests()


def runDataTests():
	"""reads directory names from __tests/__unitpaths__ and then runs
	tests defined there.
	"""
	inputsDir = base.getConfig("inputsDir")
	dirFile = os.path.join(inputsDir, "__tests", "__unitpaths__")
	if not os.path.exists(dirFile):
		return
	with open(dirFile) as f:
		for dirName in f:
			dirName = dirName.strip()
			if dirName and not dirName.startswith("#"):
				os.chdir(os.path.join(inputsDir, dirName))
				curDir = os.getcwd()
				sys.path[0:0] = [curDir]

				print "\n\nTests from %s:\n\n"%dirName
				runAllTests(includeDoctests=False)
				sys.path.remove(curDir)


if __name__=="__main__":
	base.DEBUG = False

	if len(sys.argv)==1:
		runAllTests()

		subprocess.check_call(["python", "runAllTests.py", "data"],
			env=testhelpers.originalEnvironment)

	else:
		runDataTests()
