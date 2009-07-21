"""
Common error handling facilities for user interface components.
"""

import sys
import textwrap
import traceback

from gavo import base
from gavo import grammars

reraise = False

def runAndCatch(func):
	"""returns func(), catching and processing any exceptions
	that might occur.
	"""
	try:
		return func()
	except SystemExit, msg:
		sys.exit(msg.code)
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
		sys.exit(1)
	except (base.ValidationError, base.ReportableError), msg:
		errTx = unicode(msg).encode(base.getConfig("ui", "outputEncoding"))
		sys.stderr.write(textwrap.fill(errTx, break_long_words=False)+"\n\n")
		sys.exit(1)
	except base.RDNotFound, msg:
		sys.stderr.write("%s\n"%msg)
		sys.exit(1)
	except base.LiteralParseError, msg:
		sys.stderr.write("While trying to parse literal %s for attribute %s:"
			" %s"%(repr(msg.attVal), msg.attName, str(msg)))
		sys.exit(1)
	except Exception, msg:
		sys.stderr.write("Oops.  Unhandled exception.  Here's the traceback:\n")
		if reraise:
			raise
		else:
			traceback.print_exc()
			sys.exit(1)
