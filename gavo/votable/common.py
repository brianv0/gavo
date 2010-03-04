"""
Common definitions for the GAVO VOTable modules.
"""

from gavo import utils

class VOTableError(utils.Error):
	"""Various VOTable-related errors.
	"""

class BadVOTableLiteral(VOTableError):
	"""Raised when a literal in a VOTable is invalid.
	"""
	def __init__(self, type, literal, hint=None):
		VOTableError.__init__(self, 
			"Invalid literal for %s: '%s'"%(type, repr(literal)),
			hint=hint)
		self.type, self.literal = type, literal
	
	def __str__(self):
		return "Invalid literal for %s: %s"%(self.type, repr(self.literal))

class BadVOTableData(VOTableError):
	"""Raised when something is wrong with a value being inserted into
	a VOTable.
	"""
	def __init__(self, msg, val, fieldName, hint=None):
		VOTableError.__init__(self, msg, hint=hint)
		self.fieldName, self.val = fieldName, val
	
	def __str__(self):
		return "Field %s, value %s: %s"%(self.fieldName, self.val, self.msg)
