"""
Runs all known tests on the main gavo code tree (i.e. .../gavo).

This script *asssumes* it is run from tests subdirectory of the code
tree and silently won't work (properly) otherwise.
"""

import unittest
import doctest
import glob
import os

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


if __name__=="__main__":
	unittestSuite = unittest.defaultTestLoader.loadTestsFromNames(
		unittestModules)
	doctestSuite = getDoctests()
	runner = unittest.TextTestRunner()
	runner.run(unittest.TestSuite([unittestSuite, doctestSuite]))
