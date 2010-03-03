"""
Common definitions for the GAVO VOTable modules.
"""

from gavo import utils

class VOTableError(utils.Error):
	"""Various VOTable-related errors.
	"""

class BadVOTableLiteral(VOTableError):
	"""A literal in a VOTable was invalid.
	"""
	def __init__(self, type, literal, hint=None):
		VOTableError("Invalid literal for %s: '%s'"%(type, repr(literal)),
			hint=hint)
		self.type, self.literal = type, literal
	
	def __str__(self):
		return "Invalid literal for %s: %s"%(self.type, repr(self.literal))
