"""
Common definitions for the GAVO VOTable modules.
"""

from gavo import utils


NaN = float("NaN")

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
		self.fieldName, self.val = fieldName, repr(val)

	def __getstate__(self):
		return {"msg": self.msg, "val": self.val, "fieldName": self.fieldName}

	def __str__(self):
		return "Field '%s', value %s: %s"%(self.fieldName, self.val, self.msg)

class VOTableParseError(VOTableError):
	"""Raised when something is grossly wrong with the document structure.

	Note that the message passed already contains line and position.  I'd
	like to have them in separate attributes, but the expat library mashes
	them up.  iterparse.getParseError is the canonical way of obtaining these
	when you have no positional information.
	"""


def escapePCDATA(val):
	return (val
		).replace("&", "&amp;"
		).replace('<', '&lt;'
		).replace('>', '&gt;'
		).replace("\0", "&x00;")


def escapeAttrVal(val):
	return '"%s"'%(escapePCDATA(val).replace('"', '&quot;').encode("utf-8"))


def validateTDComplex(val):
	re, im = map(float, val.split())


def validateVOTInt(val):
	"""raise an error if val is not a legal int for VOTables.
	"""
	try:
		int(val[2:], 16)
	except ValueError:
		int(val)


def iterflattened(arr):
	"""iterates over all "atomic" values in arr.

	"atomic" means "not list, not tuple".

	TODO: Check if this sequence is compatible with VOTable spec (as it is)
	"""
	for val in arr:
		if isinstance(val, (list, tuple)):
			for subval in val:
				yield subval
		else:
			yield val
