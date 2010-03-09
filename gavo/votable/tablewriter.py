"""
Writing tabular data within VOTables.
"""

from cStringIO import StringIO

from gavo.votable import coding
from gavo.votable import common
from gavo.votable import enc_binary
from gavo.votable import enc_tabledata
from gavo.votable.model import VOTable

_encoders = {
	VOTable.TABLEDATA: enc_tabledata,
	VOTable.BINARY: enc_binary,
}


def _escapeAttrVal(val):
	return '"%s"'%(common.escapeCDATA(val).replace('"', '&quot;'
		).encode("utf-8"))


def write(root, outputFile):
	"""writes the VOTable below row to outputFile.

	stanxml has a render method that could do the same thing; however,
	that uses ElementTree, and there is no way we can support streaming
	rendering using that mechanism.

	This function is more or less a subset of ElementTree.write (in particular:
	No namespaces, not processing instructions since we don't need them for
	VOTables yet, fixed encoding utf-8), with the extension that xmlstan nodes 
	can define a write(file, encoding) method that, if defined, will be used 
	instead of the standard serialization.
	"""
# This should be in a different module, really.  It's too specialized
# for xmlstan itself, though.
	def visit(name, text, attrs, childIter):
		attrRepr = " ".join("%s=%s"%(k, _escapeAttrVal(v))
			for k, v in attrs.iteritems())
		if attrRepr:
			attrRepr = " "+attrRepr
		outputFile.write("<%s%s>"%(name, attrRepr))
		if text:
			outputFile.write(common.escapeCDATA(text).encode("utf-8"))
		for c in childIter:
			if hasattr(c, "write"):
				c.write(outputFile)
			else:
				c.traverse(visit)
		outputFile.write("</%s>"%name)

	outputFile.write("<?xml version='1.0' encoding='utf-8'?>\n")
	root.traverse(visit)
	

def asString(root):
	"""returns the V.VOTABLE as a string.
	"""
	res = StringIO()
	write(root, res)
	return res.getvalue()


def DelayedTable(tableDefinition, rowIterator, contentElement, **attrs):
	"""returns tableDefinition such that when serialized, it contains
	the data from rowIterator 

	rowIterator is an iterator yielding all rows from the table to be encoded,
	tableDefinition is the TABLE element, and ContentElement is one of the
	permitted DATA children from VOTable.

	attrs are optional attributes to the content element.
	"""
	if contentElement not in _encoders:
		raise common.VOTableError("Unsupported content element %s"%contentElement,
			hint="Try something like TABLEDATA or BINARY")
	encodeRow = coding.buildEncoder(tableDefinition, _encoders[contentElement])

	def iterSerialized():
		for row in rowIterator:
			yield encodeRow(row)
	
	content = contentElement(**attrs)
	content.text = "Placeholder for real data"
	content.iterSerialized = iterSerialized

	return tableDefinition[VOTable.DATA[
		content]]
		
