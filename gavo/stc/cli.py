"""
A small user interface for testing STC.
"""

import sys
import textwrap

from gavo import stc


def cmd_resprof(opts, srcSTCS):
	"""<srcSTCS> -- make a resource profile for srcSTCS.
	"""
	ast0 = stc.parseSTCS(srcSTCS)
	print stc.getSTCXProfile(ast0)


def cmd_parseX(opts, srcFile):
	"""<srcFile> -- read STC-X from srcFile and output it as STC-S.
	"""
	asf = stc.parseSTCX(open(srcFile).read())
	print "\n\n====================\n\n".join(stc.getSTCS(ast)
		for ast in asf)
		


def cmd_conform(opts, srcSTCS, dstSTCS):
	"""<srcSTCS>. <dstSTCS>  -- prints srcSTCS in the system of dstSTCS.
	"""
	ast0, ast1 = stc.parseSTCS(srcSTCS), stc.parseSTCS(dstSTCS)
	res = stc.conformTo(ast0, ast1)
	print stc.getSTCS(res)

def makeParser():
	from optparse import OptionParser
	parser = OptionParser(usage="%prog [options] <command> {<command-args}\n"
		"  Use command 'help' to see commands available.")
	parser.add_option("-e", "--dump-exception", help="Dump exceptions.",
		dest="dumpExc", default=False, action="store_true")
	return parser

_cmdArgParser = makeParser()


def cmd_help(opts):
	""" -- outputs help to stdout.
	"""
	_cmdArgParser.print_help(file=sys.stderr)
	sys.stderr.write("\nCommands include:\n")
	for name in globals():
		if name.startswith("cmd_"):
			sys.stderr.write("%s %s\n"%(name[4:], 
				globals()[name].__doc__.strip()))
	

def parseArgs():
	opts, args = _cmdArgParser.parse_args()
	if not args:
		cmd_help(opts)
		sys.exit(1)
	return opts, args[0], args[1:]


def bailOnExc(opts, msg):
	import traceback
	if opts.dumpExc:
		traceback.print_exc()
	sys.stderr.write(textwrap.fill(msg, replace_whitespace=True,
		initial_indent='', subsequent_indent="  ")+"\n")
	sys.exit(1)


def main():
	opts, cmd, args = parseArgs()
	errmsg = None
	try:
		globals()["cmd_"+cmd](opts, *args)
	except KeyError:
		bailOnExc(opts, "Unknown command: %s."%cmd)
	except TypeError:
		bailOnExc(opts, "Invalid arguments for %s: %s."%(cmd, args))
	except stc.STCSParseError, ex:
		bailOnExc(opts, "STCS expression '%s' bad somewhere after %s (%s)"%(
			ex.expr, ex.pos, ex.message))
	except stc.STCNotImplementedError, ex:
		bailOnExc(opts, "Feature not yet supported: %s."%ex)
	except stc.STCValueError, ex:
		bailOnExc(opts, "Bad value in STC input: %s."%ex)
