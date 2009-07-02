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
	arg1, opr, arg2 = node.children
	if isinstance(arg1, basestring):
		fCall, opd = arg1, arg2
	else:
		fCall, opd = arg2, arg1
	opd = nodes.flatten(opd)
	if opd not in ['1', '0']:
		raise MorphError("Pseudo-Booleans in ADQL may only be compared"
			" against 0 or 1")
	if opr not in ["=", "!="]:
		raise MorphError("Pseudo-Booleans in ADQL may only be compared"
			" using = or !=")
	node.children = [{("=", "1"): "", ("!=", "0"): "",
		("!=", "1"): "NOT", ("=", "0"): "NOT"}[opr, opd], fCall]
	return node


def morphTreeWithHandlers(tree, handlers):
	"""traverses tree in postorder, calling handlers on the nodes.

	handlers is a dictionary mapping node types to functions taking a node
	and a state.  These functions must return the node that will replace
	the one they got passed.  To make a parent reprocess its children,
	old is new should be false.

	If you need to flatten things differently from the ADQL default,
	you can use a custom flattener in your handler.  Since we traverse
	postorder, all lower-level morphing has been done at this point.
	You may want to employ nodes.flattenKWs if you need to do this.
	"""
	state = State()
	def traverse(node):
		childrenChanged = False
		newChildren = []
		for child in node:
			if isinstance(child, nodes.ADQLNode):
				newChild = traverse(child)
				childrenChanged = childrenChanged or (newChild is not child)
				newChildren.append(newChild)
			else:
				newChildren.append(child)
		if childrenChanged:
			node.children = newChildren
			node._processChildren()
		if node.type in handlers:
			return handlers[node.type](node, state)
		return node
	return traverse(tree)
