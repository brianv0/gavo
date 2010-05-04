"""
The main entry point to CLI usage of GAVO code.
"""

from __future__ import with_statement


# The idea here is that you expose a CLI functionality by giving, as
# strings, the module and function to call.
#
# We also give a little startup note if we're running on a tty.
# While we do this, we import api; that should take care of most
# of the real startup time.

import imp
import os
import sys
import textwrap
import traceback
from contextlib import contextmanager


functions = {
	"tap": ("protocols.taprunner", "main"),
	"imp": ("user.importing", "main"),
	"drop": ("user.dropping", "main"),
	"cred": ("protocols.creds", "main"),
	"pub": ("registry.publication", "main"),
	"publish": ("registry.publication", "main"),
	"mkboost": ("grammars.directgrammar", "main"),
	"config": ("base.config", "main"),
	"gendoc": ("user.docgen", "main"),
	"stc": ("stc.cli", "main"),
	"serve": ("user.serve", "main"),
	"adql": ("protocols.adqlglue", "localquery"),
	"raise": ("user.errhandle", "bailOut"),
}


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


def _enablePDB():
# This can't be a callback to the --enable-pdb option since it needs
# errhandle, and we only want to import this after the command line
# is parsed
	import pdb
	def enterPdb(type, value, tb):
		traceback.print_exception(type, value, tb)
		pdb.pm()
	sys.excepthook = enterPdb


@contextmanager
def _progressText(opts):
	"""a quick note that something is happening if we're on a tty.
	"""
# We probably should rather make import faster...
	if not opts.disableSpew and os.isatty(sys.stdout.fileno()):
		sys.stdout.write("Starting up...")
		sys.stdout.flush()
		yield None
		sys.stdout.write("\r                 \r")
		sys.stdout.flush()
	else:
		yield None


def _parseCLArgs():
	"""parses the command line and returns instructions on how to go on.

	As a side effect, sys.argv is manipulated such that the program
	called thinks it was execd in the first place.
	"""
	from optparse import OptionParser
	parser = OptionParser(usage="%prog {<global option>} <func>"
		" {<func option>} {<func argument>}\n"+
		textwrap.fill("<func> is one of %s"%(", ".join(sorted(functions))),
		initial_indent='', subsequent_indent='  '),
		description="Try %prog <func> --help for function-specific help")
	parser.disable_interspersed_args()
	parser.add_option("--traceback", help="print a traceback on all errors.",
		action="store_true", dest="alwaysTracebacks")
	parser.add_option("--enable-pdb", help="run pdb on all errors.",
		action="store_true", dest="enablePDB")
	parser.add_option("--disable-spew", help='Suppress silly "starting up".',
		action="store_true", dest="disableSpew")
	parser.add_option("--profile-to", metavar="PROFILEPATH",
		help="enable profiling and write a profile to PROFILEPATH",
		action="store", dest="profilePath", default=None)

	opts, args = parser.parse_args()
	if len(args)<1:
		parser.print_help()
		sys.exit(2)

	try:
		module, funcName = functions[args[0]]
	except KeyError:
		parser.print_help()
		sys.exit(2)
	
	parser.destroy()
	args[0] = "gavo "+args[0]
	sys.argv = args
	return opts, module, funcName

	
def main():
	global api, errhandle
	opts, module, funcName = _parseCLArgs()
	with _progressText(opts):
		from gavo import api
		from gavo.user import errhandle
		if opts.enablePDB:
			_enablePDB()
		funcToRun = getattr(loadGAVOModule(module), funcName)

	if opts.profilePath:
		import cProfile
		cProfile.runctx("funcToRun()", globals(), locals(), opts.profilePath)
		return

	try:
		funcToRun()
	except Exception, ex:
		if opts.alwaysTracebacks:
			traceback.print_exc()
		errhandle.raiseAndCatch(opts)


if __name__=="__main__":
	main()
