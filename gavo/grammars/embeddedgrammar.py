"""
Grammars defined by code embedded in the RD.
"""

from gavo import base
from gavo import rscdef
from gavo.grammars import common


class EmbeddedIterator(rscdef.ProcApp):
	"""A definition of an iterator of a grammar.

	The code defined here becomes the _iterRows method of a 
	grammar.common.RowIterator class.  This means that you can
	access self.grammar (the parent grammar; you can use this to transmit
	properties from the RD to your function) and self.sourceToken (whatever
	gets passed to parse()).
	"""
	name_ = "iterator"
	requiredType = "iterator"
	formalArgs = "self"


class EmbeddedGrammar(common.Grammar):
	"""A Grammar defined by a code application.

	To define this grammar, write a ProcApp leading to code yielding
	row dictionaries.
	"""
	name_ = "embeddedGrammar"
	_iterator = base.StructAttribute("iterator", default=base.Undefined,
		childFactory=EmbeddedIterator,
		description="Code yielding row dictionaries", copyable=True)

	def onElementComplete(self):
		self._onElementCompleteNext(EmbeddedGrammar)
		class RowIterator(common.RowIterator):
			_iterRows = self.iterator.compile()
			notify = False
		self.rowIterator = RowIterator

rscdef.registerGrammar(EmbeddedGrammar)
