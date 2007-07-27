import gavo
import os

verbose = False

class ParseError(gavo.Error):
	"""is an exception that should be raised by grammars if anything
	is wrong with them.
	"""
	pass
