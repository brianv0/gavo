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
	data.  It gets it from a sequence of DataFields in dbFields.
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
		# This defaults processing sucks -- we'd really want to use getValueIn,
		# but then we'd first have to build the dict and still do nothing more
		# than with this most of the time.  Hm.
		defaults = [(f.get_dest(), f.get_default())
			for f in self.get_dbFields() if f.get_default() is not None]
		for row in parseContext.sourceFile:
			res = dict(itertools.izip(colNames, row))
			for name, default in defaults:
				if res.get(name) is None:
					res[name] = default
			yield res
