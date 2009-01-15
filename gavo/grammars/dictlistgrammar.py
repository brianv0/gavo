"""
A (quite trivial) grammar that iterates over lists of dicts.
"""

from gavo import base
from gavo import rscdef
from gavo.grammars.common import Grammar, RowIterator


class ListIterator(RowIterator):
	def __init__(self, *args, **kwargs):
		RowIterator.__init__(self, *args, **kwargs)
		self.recNo = 0

	def _iterRows(self):
		self.recNo = 1
		for rec in self.sourceToken:
			res = rec.copy()
			res["parser_"] = self
			yield res
			self.recNo += 1
	
	def getLocator(self):
		return "List, index=%d"%self.recNo


class DictlistGrammar(Grammar):
	"""is a grammar that "parses" from lists of dicts.
	"""
	name_ = "dictlistGrammar"
	rowIterator = ListIterator


rscdef.registerGrammar(DictlistGrammar)
