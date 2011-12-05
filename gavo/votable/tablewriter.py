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
	"""writes the VOTable below row to outputFile.

	stanxml has a render method that could do the same thing; however,
	that uses ElementTree, and there is no way we can support streaming
	rendering using that mechanism.

	This function is more or less a subset of ElementTree.write (in particular:
	No namespaces, no processing instructions since we don't need them for
	VOTables yet, fixed encoding utf-8), with the extension that xmlstan nodes 
	can define a write(file, encoding) method that, if defined, will be used 
	instead of the standard serialization.
	"""
# This should be in a different module, really.  It's too specialized
# for xmlstan itself, though.
	def visit(node, text, attrs, childIter):
		attrRepr = " ".join("%s=%s"%(k, common.escapeAttrVal(v))
			for k, v in attrs.iteritems())
		if attrRepr:
			attrRepr = " "+attrRepr
		if getattr(node, "_fixedTagMaterial", None):
			attrRepr = attrRepr+" "+node._fixedTagMaterial
		outputFile.write("<%s%s>"%(node.name_, attrRepr))
		if text:
			outputFile.write(common.escapePCDATA(text).encode("utf-8"))
		for c in childIter:
			if hasattr(c, "write"):
				c.write(outputFile)
			else:
				c.apply(visit)
		outputFile.write("</%s>"%node.name_)
	
	if xmlDecl:
		outputFile.write("<?xml version='1.0' encoding='utf-8'?>\n")
	root.apply(visit)
	

def asString(root):
	"""returns the V.VOTABLE root as a string.
	"""
	res = StringIO()
	write(root, res)
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
