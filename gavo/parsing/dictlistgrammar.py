"""
A grammar that just hands through dicts as rowdicts
"""

import gavo
from gavo import record
from gavo.parsing import grammar

class DictlistGrammar(grammar.Grammar):
	def _getDocdict(self, parseContext):
		return {}

	def _iterRows(self, parseContext):
		for rowDict in parseContext.sourceFile:
			yield rowDict
