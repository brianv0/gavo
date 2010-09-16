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

from gavo.user import common

functions = [
	("admin", ("user.admin", "main")),
	("adql", ("protocols.adqlglue", "localquery")),
	("config", ("base.config", "main")),
	("drop", ("user.dropping", "main")),
	("gendoc", ("user.docgen", "main")),
	("import", ("user.importing", "main")),
	("mkboost", ("grammars.directgrammar", "main")),
	("publish", ("registry.publication", "main")),
	("raise", ("user.errhandle", "bailOut")),
	("serve", ("user.serve", "main")),
	("stc", ("stc.cli", "main")),
	("taprun", ("protocols.taprunner", "main")),
]


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


def _enableDebug(*args):
	from gavo import base
	base.DEBUG = True


def _parseCLArgs():
	"""parses the command line and returns instructions on how to go on.

	As a side effect, sys.argv is manipulated such that the program
	called thinks it was execd in the first place.
	"""
	from optparse import OptionParser
	sels = [n for n,x in functions]
	sels.sort()
	parser = OptionParser(usage="%prog {<global option>} <func>"
		" {<func option>} {<func argument>}\n"+
		textwrap.fill("<func> is a unique prefix into {%s}"%(", ".join(sels)),
		initial_indent='', subsequent_indent='  '),
		description="Try %prog <func> --help for function-specific help")
	parser.disable_interspersed_args()
	parser.add_option("--traceback", help="print a traceback on all errors.",
		action="store_true", dest="alwaysTracebacks")
	parser.add_option("--hints", help="if there are hints on an error, display"
		" them", action="store_true", dest="showHints")
	parser.add_option("--enable-pdb", help="run pdb on all errors.",
		action="store_true", dest="enablePDB")
	parser.add_option("--disable-spew", help='Suppress silly "starting up".',
		action="store_true", dest="disableSpew")
	parser.add_option("--profile-to", metavar="PROFILEPATH",
		help="enable profiling and write a profile to PROFILEPATH",
		action="store", dest="profilePath", default=None)
	parser.add_option("--suppress-log", help="Do not log exceptions and such"
		" to the gavo-specific log files", action="store_true",
		dest="suppressLog")
	parser.add_option("--debug", help="Produce debug info as appropirate.",
		action="callback", callback=_enableDebug)

	opts, args = parser.parse_args()
	if len(args)<1:
		parser.print_help()
		sys.exit(2)

	module, funcName = common.getMatchingFunction(args[0], functions, parser)
	parser.destroy()
	args[0] = "gavo "+args[0]
	sys.argv = args
	return opts, module, funcName


def main():
	global api, errhandle

	if len(sys.argv)>1 and sys.argv[1]=="init":  
		# Special case: initial setup, no api working yet
		from gavo.user import initdachs
		sys.exit(initdachs.main())

	opts, module, funcName = _parseCLArgs()
	with _progressText(opts):
		from gavo import api
		from gavo import base
		from gavo.user import errhandle
		from gavo.user import logui
		if not opts.suppressLog:
			logui.LoggingUI(base.ui)
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
