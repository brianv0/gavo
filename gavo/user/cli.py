"""
The main entry point to CLI usage of GAVO code.
"""

# The idea here is that you expose a CLI functionality by giving, as
# strings, the module and function to call.
#
# The function's docstring is printed in the function directory.
# If a valid function selector is given, this selector is removed
# from sys.argv and control is handed over to the function selected.
#
# The module imports api so top-level components have getRD and friends.

import imp
import sys

from gavo import api

functions = {
	"tap": ("protocols.taprunner", "main"),
	"imp": ("commandline", "main"),
	"adql": ("protocols.adqlglue", "localquery"),
}

def printHelp():
	print "Usage: %s <function> [<function arguments]"%sys.argv[0]
	print "where <function> is one of %s"%(", ".join(sorted(functions)))
	print ""
	print "<function> = help gives explanations on what functions do."
	print "Use %s <function> -h for help of individual functions."%sys.argv[0]


def loadGAVOModule(moduleName):
	"""loads the a module from the gavo packages.

	In effect, this loads "gavo."+moduleName, where moduleName may contain
	dots.
	"""
	names = ["gavo"]+moduleName.split(".")
	path = None
	for name in names:
		moddesc = imp.find_module(name, path)
		imp.acquire_lock()
		try:
			modNS = imp.load_module(name, *moddesc)
			try:
				path = modNS.__path__
			except AttributeError: 
				pass # NS is a non-package module; this should be the end of the loop.
		finally:
			imp.release_lock()
	return modNS


def runFunction(module, funcName):
	"""imports funcName from module and calls it without arguments.
	"""
	getattr(loadGAVOModule(module), funcName)()


def main():
	try:
		module, funcName = functions[sys.argv[1]]
	except (IndexError, KeyError):
		printHelp()
	del sys.argv[1]
	runFunction(module, funcName)


if __name__=="__main__":
	main()
