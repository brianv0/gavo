"""
Writing tabular data within VOTables.
"""

from cStringIO import StringIO

from gavo.utils import stanxml
from gavo.votable import coding
from gavo.votable import common
from gavo.votable import enc_binary
from gavo.votable import enc_tabledata
from gavo.votable.model import VOTable

_encoders = {
	VOTable.TABLEDATA: enc_tabledata,
	VOTable.BINARY: enc_binary,
}


def write(root, outputFile, xmlDecl=True):
	"""writes a VOTable to outputFile.

	This is a compatiblity function that's here mainly for historical reasons.
	It's basically stanxml.write, except that the prefix of the root element
	will be the empty prefix.
	"""
	return stanxml.write(root, outputFile, xmlDecl=xmlDecl,
		prefixForEmpty=root._prefix)


def asString(root, xmlDecl=False):
	"""returns the V.VOTABLE root as a string.
	"""
	res = StringIO()
	write(root, res, xmlDecl=xmlDecl)
	return res.getvalue()


class OverflowElement(stanxml.Stub):
	"""A container for VOTable elements that are written when it is
	likely that a query has overflowed the limit.

	This is for use with DelayedTable.  Instances of this can be
	passed into overflowElement.

	OverflowElements are constructed with the row limit and VOTable
	material to be inserted when exactly row limit (or more) rows
	have been written to the table.

	This will not work with stanxml serialization (could be fixed).
	"""
	def __init__(self, rowLimit, overflowStan):
		self.rowLimit, self.overflowStan = rowLimit, overflowStan
		self.rowsDelivered = None

	def __repr__(self):
		return "<Uninstanciated Overflow Warning>"

	def setRowsDelivered(self, numRows):
		self.rowsDelivered = numRows
	
	def write(self, outputFile):
		if self.rowLimit<=self.rowsDelivered:
			write(self.overflowStan, outputFile, xmlDecl=False)


def DelayedTable(tableDefinition, rowIterator, contentElement,
		overflowElement=None, **attrs):
	"""returns tableDefinition such that when serialized, it contains
	the data from rowIterator 

	rowIterator is an iterator yielding all rows from the table to be encoded,
	tableDefinition is the TABLE element, and ContentElement is one of the
	permitted DATA children from VOTable.

	See the OverflowElement class for overflowElement.

	attrs are optional attributes to the content element.
	"""
	if contentElement not in _encoders:
		raise common.VOTableError("Unsupported content element %s"%contentElement,
			hint="Try something like TABLEDATA or BINARY")
	encodeRow = coding.buildEncoder(tableDefinition, _encoders[contentElement])

	def iterSerialized():
		numRows = 0
		for row in rowIterator:
			numRows += 1
			yield encodeRow(row)
		if overflowElement is not None:
			overflowElement.setRowsDelivered(numRows)
	
	content = contentElement(**attrs)
	content.text_ = "Placeholder for real data"
	content.iterSerialized = iterSerialized

	return tableDefinition[
		VOTable.DATA[content]]
# In a way, we'd like to have an overflow element here, assuming that
# the table comes from a db query.  We could have that writing:
#		overflowElement]
# -- but TAP wants the overflow at the resource level.  So, we
# put it there.  It will reflect the state of affairs for the last
# table (which is probably as good as anything else).
