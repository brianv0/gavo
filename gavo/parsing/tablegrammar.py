"""
A grammar that takes tables as inputs.
"""

import gavo
from gavo.parsing import grammar


class TableGrammar(grammar.Grammar):
	"""is a Grammar that reads its data from dataSets

	The ParseContext for these objects must have a dataSet
	instance as inputFile.

	As long as we don't have a clear idea of what to do with multi-table
	dataSets, only the first table in a dataSet is handled.
	"""
	def _getDocdict(self, parseContext):
		return parseContext.sourceFile.getDocRec()
	
	def _iterRows(self, parseContext):
		for row in parseContext.sourceFile.getTables()[0]:
			yield row
