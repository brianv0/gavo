"""
Helpers for morphing modules
"""

from gavo.adql import nodes
from gavo.adql.common import *

class MorphError(Error):
	pass


class State(object):
	"""is a scratchpad for morphers to communicate state among
	themselves.

	In general, add of delete attributes here, since it's just
	communication between children and ancestors.  
	
	We might need stacks at some point, too...

	Here's what attributes are taken; more can be used by individual morphers:

	killParentComparison -- used by contains to tell the comparison somewhere
	up the tree to replace the comparison by the simple function call.
	"""
	def __init__(self):
		self.warnings = []


def killGeoBooleanOperator(node, state):
	"""turns a comparison expression into a boolean function call
	if killParentOperator is in state.

	As a side effect, it resets killParentOperator.

	This is for the incredibly stupid geometric function of
	ADQL that return 0 or 1.  To cope with that, nodes can set a
	killParentOperator attribute.  If it's present in the arguments
	of a comparsion, the system checks if we're comparing against
	a 0 or a 1 and converts the whole thing into a boolean query or
	bombs out.

	The other operand must be a string, supposed to contain the boolean
	function.
	"""
	if not hasattr(state, "killParentOperator"):
		return node
	delattr(state, "killParentOperator")
	if isinstance(node.op1, basestring):
		fCall, opd = node.op1, node.op2
	else:
		fCall, opd = node.op2, node.op1
	opd = nodes.flatten(opd)
	if opd not in ['1', '0']:
		raise MorphError("Pseudo-Booleans in ADQL may only be compared"
			" against 0 or 1")
	if node.opr not in ["=", "!="]:
		raise MorphError("Pseudo-Booleans in ADQL may only be compared"
			" using = or !=")
	return "%s (%s)"%({("=", "1"): "", ("!=", "0"): "",
		("!=", "1"): "NOT", ("=", "0"): "NOT"}[node.opr, opd], fCall)



class Morpher(object):
	"""A class managing the process of morphing an ADQL expression.

	It is constructed with a a dictionary of morphers; the keys are node
	types, the values morphing functions.

	Morphing functions have the signature m(node, state) -> node.  They
	should return the node if they do not with to change it.
	state is a State instance.

	The main entry point is morph(origTree) -> state, tree.  origTree is not 
	modified, the return value can be flattened but can otherwise be severely 
	damaged.
	"""
	def __init__(self, morphers):
		self.morphers = morphers

	def _getChangedForSeq(self, value, state):
		newVal, changed = [], False
		for child in value:
			if isinstance(child, nodes.ADQLNode):
				newVal.append(self._traverse(child, state))
			else:
				newVal.append(child)
			if newVal[-1]!=child:
				changed = True
		if changed:
			return tuple(newVal)
	
	def _getChangedForNode(self, value, state):
		newVal = self._traverse(value, state)
		if not newVal is value:
			return newVal

	def _getChanges(self, name, value, state):
		"""iterates over key/value pairs changed by morphing value under
		the key name.
		"""
		if isinstance(value, (list, tuple)):
			meth = self._getChangedForSeq
		elif isinstance(value, nodes.ADQLNode):
			meth = self._getChangedForNode
		else:
			return
		newVal = meth(value, state)
		if newVal is not None:
			yield name, newVal

	def _traverse(self, node, state):
		changes = []
		for name, value in node.iterAttributes():
			changes.extend(self._getChanges(name, value, state))
		if changes:
			newNode = node.change(**dict(changes))
		else:
			newNode = node

		if node.type in self.morphers:
			handlerResult = self.morphers[node.type](newNode, state)
			assert handlerResult is not None, "ADQL morph handler returned None"
			return handlerResult
		return newNode

	def morph(self, tree):
		state = State()
		res = self._traverse(tree, state)
		return state, res
