from gavo.parsing import grammar

class NullGrammar(grammar.Grammar):
	"""is a grammar that does nothing.

	This is useful for "pseudo resources" that just define views and such.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {})
