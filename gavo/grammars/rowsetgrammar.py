"""
A grammar that takes standard tuples as input and turns them into rows
of a table.
"""

import itertools

from gavo import base
from gavo import rscdef
from gavo.grammars import common

class RowsetIterator(common.RowIterator):
	"""is a row iterator over a sequence of tuples.
	"""
	def _decodeRow(self, row):
# a bit crazy to avoid having to rebuild every row in the "normal" case
# of ASCII input
		newFields = {}
		for ind, r in enumerate(row):
			if isinstance(r, str) and max(r)>'~':
				newFields[ind] = r.decode(self.grammar.enc)
		newRow = []
		if newFields:
			for ind, v in enumerate(row):
				if ind in newFields:
					newRow.append(newFields[ind])
				else:
					newRow.append(v)
			return tuple(newRow)
		else:
			return row

	def _iterRows(self):
		colNames = self.grammar.names
		for row in self.sourceToken:
			if self.grammar.enc:
				row = self._decodeRow(row)
			yield dict(itertools.izip(colNames, row))
		self.grammar = None


class RowsetGrammar(common.Grammar):
	"""is a grammar handling sequences of tuples.

	To add semantics to the field, it must know the "schema" of the
	data.  This is defined via the table it is supposed to get the input
	from.
	"""
	name_ = "rowsetGrammar"
	rowIterator = RowsetIterator

	_fieldsFrom = base.ReferenceAttribute("fieldsFrom", 
		description="Table to fetch fields from", copyable=True)

	def onElementComplete(self):
		self._onElementCompleteNext(RowsetGrammar)
		self.names = [c.name for c in self.fieldsFrom]

rscdef.registerGrammar(RowsetGrammar)
