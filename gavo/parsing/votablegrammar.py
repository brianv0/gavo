"""
A grammar taking its rows from a VOTable.
"""

# XXX TODO: return PARAMs as the docrow

from itertools import *

from gavo.imp import VOTable
from gavo.parsing import grammar
from gavo.parsing import mkrd

class VOTableGrammar(grammar.Grammar):
	def _getDocdict(self, parseContext):
		parseContext.vot = VOTable.parse(parseContext.sourceFile)
		return {}

	def _iterRows(self, parseContext):
		srcTable = parseContext.vot.resources[0].tables[0]
		fieldNames = [mkrd.makeVOTableFieldName(f, ind)
			for ind, f in enumerate(srcTable.fields)]
		for row in srcTable.data:
			yield dict(izip(fieldNames, row))
