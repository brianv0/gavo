"""
Parsing various forms of tabular data embedded in VOTables.

WARNING: This will fail if the parser exposes namespaces in its
events (votable.iterparse doesn't).
"""

from gavo.votable import coding
from gavo.votable import common
from gavo.votable import dec_binary
from gavo.votable import dec_tabledata


class DataIterator(object):
	"""A base for the classes actually doing the iteration.

	You need to give a decoderModule attribute and implement _getRawRow.
	"""
	def __init__(self, tableDefinition, nodeIterator):
		self.nodeIterator = nodeIterator
		self._decodeRawRow = coding.buildCodec(
			coding.getRowDecoderSource(
				tableDefinition,
				self.decoderModule),
			self.decoderModule.getGlobals())

	def __iter__(self):
		while True:
			rawRow = self._getRawRow()
			if rawRow is None:
				break
			yield self._decodeRawRow(rawRow)


class TableDataIterator(DataIterator):
	"""An internal class used by Rows to actually iterate over rows
	in TABLEDATA serialization.
	"""
	decoderModule = dec_tabledata

	def _getRawRow(self):
		"""returns a row in strings or None.
		"""
		# Wait for TR open
		for ev in self.nodeIterator:
			if ev==("end", "TABLEDATA"):
				return None
			elif ev[0]=="start":
				if ev[1]=="TR":
					break
				else:
					raise common.VOTableParseError("Unexpected element %s"%ev[1])
			# ignore everything else; we're not validating, and sensible stuff
			# might yet follow (usually, it's whitespace data anyway)

		rawRow = []
		for ev in self.nodeIterator:
			if ev[0]=="start":   # new TD
				if ev[1]=="TD":
					cur = []
				else:
					raise self.nodeIterator.raiseParseError(
						"Unexpected element %s"%ev[1],)
			elif ev[0]=="data":  # TD content
				cur.append(ev[1])
			elif ev[0]=="end":
				if ev[1]=="TR":
					break
				elif ev[1]=="TD":
					rawRow.append("".join(cur))
				else:
					assert False
			else:
				assert False
		return rawRow



class BinaryIterator(DataIterator):
	"""An internal class used by Rows to actually iterate over rows
	in BINARY serialization.
	"""
	decoderModule = dec_binary

	# I need to override __iter__ since we're not actually doing XML parsing
	# there; almost all of our work is done within the stream element.
	def __iter__(self):
		ev, node = self.nodeIterator.next()
		if not (ev=="start" 
				and node.tag=="STREAM"
				and node.get("encoding")=="base64"):
			raise common.VOTableError("Can only read BINARY data from base64"
				" encoded streams")


def _makeTableIterator(elementName, tableDefinition, nodeIterator):
	"""returns an iterator for the rows contained within node.
	"""
	if elementName=='TABLEDATA':
		return iter(TableDataIterator(tableDefinition, nodeIterator))
	elif elementName=='BINARY':
		return iter(BinaryIterator(tableDefinition, nodeIterator))
	else:
		raise common.VOTableError("Unknown table serialization: %s"%
			elementName, hint="We only support TABLEDATA and BINARY coding")


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
		for ev in self.nodeIterator:
			if ev[1]=="INFO":
				pass   # XXX TODO: What to do with those INFOs?
			else:
				return _makeTableIterator(ev[1], 
					self.tableDefinition, self.nodeIterator)
