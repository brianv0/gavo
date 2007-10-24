"""
A grammar that takes standard dbapi2 rowsets (as from fetchall) as input.
"""

import itertools

import gavo
from gavo.parsing import grammar

class RowsetGrammar(grammar.Grammar):
	"""is a grammar that receives data from a dbapi2 fetchall() result.

	To add semantics to the field, it must know the "schema" of the
	data.  It gets it from a RecordDef instance it receives during 
	construction.
	"""
	def __init__(self, dbFields):
		self.colNames = [f.get_dest() for f in dbFields]
		grammar.Grammar.__init__(self)

	def _getDocdict(self, parseContext):
		return {}

	def _iterRows(self, parseContext):
		for row in parseContext.sourceFile:
			yield dict(itertools.izip(self.colNames, row))
