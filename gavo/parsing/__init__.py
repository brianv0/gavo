import gavo
import os

# This is probably obsoleted by the interfaces  module
xmlFragmentPath = os.path.join(gavo.inputsDir, "__common__")

verbose = False

class ParseError(gavo.Error):
	"""is an exception that should be raised by grammars if anything
	is wrong with them.
	"""
	pass
