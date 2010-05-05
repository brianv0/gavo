"""
Trees of ADQL expressions and operations on them.
"""

from gavo.adql import grammar
from gavo.adql import nodes
from gavo.adql.common import *

_grammarCache = None


_additionalNodes = []
def registerNode(node):
	"""registers a node class or a symbolAction from a module other than node.

	This is a bit of magic -- some module can call this to register a node
	class that is then bound to some parse action as if it were in nodes.

	I'd expect this to be messy in the presence of chaotic imports (when
	classes are not necessarily singletons and a single module can be
	imported more than once.  For now, I ignore this potential bomb.
	"""
	_additionalNodes.append(node)


def getTreeBuildingGrammar():
	"""returns a pyparsing symbol that can parse ADQL expressions into
	simple trees of ADQLNodes.

	This symbol is shared, so don't change anything on it.
	"""
# To do the bindings, we iterate over the names in the node module, look for
# all children classes derived from nodes.ADQLNode (but not ADQLNode itself) and
# first check for a bindings attribute and then their type attribute.  These
# are then used to add actions to the corresponding symbols.

	global _grammarCache
	if _grammarCache:
		return _grammarCache
	syms, root = grammar.getADQLGrammarCopy()

	def bind(symName, nodeClass):
		try:
			if getattr(nodeClass, "collapsible", False):
				syms[symName].addParseAction(lambda s, pos, toks: 
					nodes.autocollapse(nodeClass, toks))
			else:
				syms[symName].addParseAction(lambda s, pos, toks: 
					nodeClass.fromParseResult(toks))
		except KeyError:
			raise KeyError("%s asks for non-existing symbol %s"%(
				nodeClass.__name__ , symName))

	def bindObject(ob):
		if isinstance(ob, type) and issubclass(ob, nodes.ADQLNode):
			for binding in getattr(ob, "bindings", [ob.type]):
				if binding:
					bind(binding, ob)
		if hasattr(ob, "parseActionFor"):
			for sym in ob.parseActionFor:
				bind(sym, ob)

	for name in dir(nodes):
		bindObject(getattr(nodes, name))

	for ob in _additionalNodes:
		bindObject(ob)

	_grammarCache = syms, root
	return syms, root


if __name__=="__main__":
	getTreeBuildingGrammar()[1].parseString('select * from z join x')
