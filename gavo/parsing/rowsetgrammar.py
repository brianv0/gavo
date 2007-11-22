"""
A grammar that takes standard dbapi2 rowsets (as from fetchall) as input.
"""

import itertools

import gavo
from gavo import record
from gavo.parsing import grammar

class RowsetGrammar(grammar.Grammar):
	"""is a grammar that receives data from a dbapi2 fetchall() result.

	To add semantics to the field, it must know the "schema" of the
	data.  It gets it from a RecordDef instance it receives during 
	construction.
	"""
	def __init__(self, initvals={}):
		grammar.Grammar.__init__(self, additionalFields={
			"dbFields": record.ListField,
			}, initvals=initvals)

	# make this work with the fieldsfrom attribute of Record elements
	def get_items(self):
		return self.get_dbFields()

	def _getDocdict(self, parseContext):
		return {}

	def _iterRows(self, parseContext):
		colNames = [f.get_dest() for f in self.get_dbFields()]
		for row in parseContext.sourceFile:
			yield dict(itertools.izip(colNames, row))
