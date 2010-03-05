"""
Common definitions for the GAVO VOTable modules.
"""

from gavo import utils


# Values we accept as meaning "single value" in a FIELD's arraysize
SINGLEVALUES = set([None, '', '1'])


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
		return "Field '%s', value %s: %s"%(self.fieldName, self.val, self.msg)



def escapeCDATA(val):
	return val.encode("utf-8"
		).replace("&", "&amp;"
		).replace('<', '&lt;'
		).replace('>', '&gt;')


def validateTDComplex(val):
	re, im = map(float, val.split())

def validateVOTInt(val):
	"""raise an error if val is not a legal int for VOTables.
	"""
	try:
		int(val)
	except ValueError:
		int(val[2:], 16)
