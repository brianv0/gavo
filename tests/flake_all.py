"""
A program to run pyflakes on all in-tree source files, with some 
basic ignoring capabilities.

This assumes it's being called from the tests subdirectory of
a complete DaCHS checkout.

This is essentially a leaned-down version of the pyflakes script
with some stuff for which we feel we can crash removed.

See docs/develNotes.rstx for extra ignoring features of this
script.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import _ast
import os

from pyflakes import checker


def iterSourceFiles():
	doctests = []
	for dir, dirs, names in os.walk("../gavo"):
		parts = dir.split("/")[1:]
		if parts[-1]=='imp':
			# Don't check files we don't actually maintain
			del dirs[:]
			continue

		for name in names:
			if name.endswith(".py"):
				yield os.path.join(dir, name)


def checkOne(filename):
	with open(filename) as f:
		codeString = f.read()
		lines = codeString.split("\n")
	if "# Not checked by pyflakes" in codeString:
		return

	tree = compile(codeString, filename, "exec", _ast.PyCF_ONLY_AST)
	w = checker.Checker(tree, filename)
	w.messages.sort(key=lambda msg: msg.lineno)
	for msg in w.messages:
		if not "#noflake" in lines[msg.lineno-1]:
			
			# globally ignore import * warnings (and decide whether to get
			# rid of the imports or fix pyflakes)
#			if (msg.message
#					=="'from %s import *' used; unable to detect undefined names"):
#				continue

			print msg


def main():
	for filename in iterSourceFiles():
		checkOne(filename)


if __name__=="__main__":
	main()
