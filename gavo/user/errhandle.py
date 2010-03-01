"""
Common error handling facilities for user interface components.
"""

import sys
import textwrap
import traceback

from gavo import base
from gavo import grammars


def raiseAndCatch(opts):
	"""raises the current exception and tries to come up with a good
	error message for it.

	This probably is just useful as a helper to user.cli.
	"""
	retval = 1
	try:
		raise
	except SystemExit, msg:
		retval = msg.code
	except grammars.ParseError, msg:
		errTx = unicode(msg)
		if msg.location:
			errTx = "Parse error at %s: %s"%(msg.location, errTx)
		else:
			errTx = "Parse error: %s"%errTx
		sys.stderr.write(textwrap.fill(errTx, break_long_words=False)+"\n\n")
		if msg.record:
			sys.stderr.write("Offending input was:\n")
			sys.stderr.write(repr(msg.record)+"\n")
	except (base.ValidationError, base.ReportableError), msg:
		errTx = unicode(msg).encode(base.getConfig("ui", "outputEncoding"))
		sys.stderr.write(textwrap.fill(errTx, break_long_words=False)+"\n\n")
	except base.LiteralParseError, msg:
		sys.stderr.write("While trying to parse literal %s for attribute %s:"
			" %s"%(repr(msg.attVal), msg.attName, str(msg)))
	except Exception, msg:
		if hasattr(msg, "excRow"):
			sys.stderr.write("Snafu in %s, %s\n"%(msg.excRow, msg.excCol))
		sys.stderr.write("Oops.  Unhandled exception.  Here's the traceback:\n")
		if opts.enablePDB:
			raise
		else:
			if not opts.alwaysTracebacks:
				traceback.print_exc()
	sys.exit(retval)


def bailOut():
	"""is a fake cli operation just raising exceptions.

	This is mainly for testing and development.
	"""
	if len(sys.argv)<2:
		raise ValueError("Too short")
	arg = sys.argv[0]
	if arg=="--help":
		raise base.Error("Hands off this.  For Developers only")
