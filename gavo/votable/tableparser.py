"""
Parsing various forms of tabular data embedded in VOTables.
"""

from gavo.votable import coding
from gavo.votable import common
from gavo.votable import dec_tabledata


class TableDataIterator(object):
	def __init__(self, tableDefinition, nodeIterator):
		self.nodeIterator = nodeIterator
		self._decodeRawRow = coding.makeRowDecoder(tableDefinition,
			dec_tabledata.getDecoderLines, dec_tabledata.getGlobals())

	def __iter__(self):
		while True:
			rawRow = self._getRawRow()
			if rawRow is None:
				break
			yield self._decodeRawRow(rawRow)

	def _getRawRow(self):
		"""returns a row in strings or None.
		"""
		ev, node = self.nodeIterator.next()
		if ev=="end":  # end of TABLEDATA element
			return None
		assert node.tag=="TR"

		rawRow = []
		for ev, node in self.nodeIterator:
			if ev=="start":
				continue
			if node.tag=='TD':
				rawRow.append(node.text)
			else:
				assert node.tag=="TR"
				return rawRow


def _makeTableIterator(node, tableDefinition, nodeIterator):
	"""returns an iterator for the rows contained within node.
	"""
	if node.tag=='TABLEDATA':
		return iter(TableDataIterator(tableDefinition, nodeIterator))
	else:
		raise common.VOTableError("Unknown table serialization: %s"%
			node.tag, hint="We only support TABLEDATA and BINARY coding")


class Rows(object):
	"""a wrapper for data within a VOTable.

	Tabledatas are constructed with a model.VOTable.TABLE instance and
	the iterator maintained by parser.parse.  They yield individual
	table lines.

	In reality, __iter__ just dispatches to the various deserializers.
	"""
	def __init__(self, tableDefinition, nodeIterator):
		self.tableDefinition, self.nodeIterator = tableDefinition, nodeIterator
	
	def __iter__(self):
		for ev, node in self.nodeIterator:
			if node.tag=="INFO":
				pass   # XXX TODO: What to do with those INFOs?
			else:
				return _makeTableIterator(node, 
					self.tableDefinition, self.nodeIterator)
