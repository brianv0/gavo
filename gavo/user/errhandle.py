"""
Common error handling facilities for user interface components.
"""

import re
import sys
import textwrap
import traceback

from gavo import base
from gavo import grammars


class _Reformatter(object):
	"""A helper class for reformatMessage.
	"""
	verbatimRE = re.compile("\s")

	def __init__(self):
		self.inBuffer, self.outBuffer = [], []

	def flush(self):
		if self.inBuffer:
			self.outBuffer.append(textwrap.fill("\n".join(self.inBuffer), 
				break_long_words=False))
			self.inBuffer = []

	def feed(self, line):
		if self.verbatimRE.match(line):
			self.flush()
			self.outBuffer.append(line)
		elif not line.strip():
			self.flush()
			self.outBuffer.append("")
		else:
			self.inBuffer.append(line)
	
	def get(self):
		self.flush()
		return "\n".join(self.outBuffer)

	def feedLines(self, lines):
		for l in lines:
			self.feed(l)


def reformatMessage(msg):
	"""reflows message using textwrap.fill.

	Lines starting with whitespace will not be wrapped.
	"""
	r = _Reformatter()
	r.feedLines(msg.split("\n"))
	return r.get()


def raiseAndCatch(opts):
	"""raises the current exception and tries to come up with a good
	error message for it.

	This probably is just useful as a helper to user.cli.
	"""
# Messages are reformatted by reformatMessage (though it's probably ok
# to just call output(someString) to write to the user directly.
#
# To write messages, append strings to the messages list.  An empty string
# would produce a paragraph.  Append unicode or ASCII.
	retval = 1
	messages = []
	output = lambda tx: sys.stderr.write(tx.encode(
			base.getConfig("ui", "outputEncoding"), "replace"))
	try:
		raise
	except SystemExit, msg:
		retval = msg.code
	except grammars.ParseError, msg:
		if msg.location:
			messages.append("Parse error at %s: %s"%(msg.location, unicode(msg)))
		else:
			messages.append("Parse error: %s"%unicode(msg))
		if msg.record:
			messsages.append("")
			messages.append("Offending input was:\n")
			messages.append(repr(msg.record)+"\n")
	except (base.ValidationError, base.ReportableError, 
			base.LiteralParseError, base.StructureError, base.RDNotFound), msg:
		messages.append(unicode(msg))
	except Exception, msg:
		if hasattr(msg, "excRow"):
			messages.append("Snafu in %s, %s\n"%(msg.excRow, msg.excCol))
			messages.append("")
		messages.append("Oops.  Unhandled exception %s.\n"%unicode(msg))
		if opts.enablePDB:
			raise
		else:
			if not opts.alwaysTracebacks:
				traceback.print_exc()
	if messages:
		errTx = unicode("*** Error: "+"\n".join(messages))
		output(reformatMessage(errTx)+"\n")
	if opts.showHints and getattr(msg, "hint", None):
		output(reformatMessage("Hint: "+msg.hint)+"\n")

	sys.exit(retval)


def bailOut():
	"""A fake cli operation just raising exceptions.

	This is mainly for testing and development.
	"""
	if len(sys.argv)<2:
		raise ValueError("Too short")
	arg = sys.argv[0]
	if arg=="--help":
		raise base.Error("Hands off this.  For Developers only")
