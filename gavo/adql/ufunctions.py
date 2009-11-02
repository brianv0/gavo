"""
"User" defined functions, i.e., ADQL functions defined only on this
system.

The functions are really python functions, receiving their arguments in a 
list children; these are whatever the rest of nodes.py does with what comes
in from the parser.

The functions have to return an ADQL node that must be structured like
it would be structured if it had been parsed out from the start.

The module has to be imported by the glue code and registers itself
in nodes.py.  This way, you can have more than one set of ufunctions.
"""


import warnings

from gavo.adql import grammar
from gavo.adql import nodes
from gavo.adql import tree
from gavo.adql.common import *


_funPrefix = grammar.userFunctionPrefix


def gavo_resolve(args):
	warnings.warn("Not resolving %s"%repr(args))


class UserFunction(nodes.FunctionNode):
	"""is a node processing user functions.

	All user functions must be declared lexically above this class
	definition.  Since SQL is case insensitive, no function names must
	clash when uppercased.  Names suitable as user functions
	start with adql.grammar.userFunctionPrefix.
	"""
	type = "userDefinedFunction"

	userFunctions = dict((name.upper(), ob) for name, ob in globals().iteritems()
		if name.startswith(_funPrefix))

	def _polish(self):
		if (self.funName.startswith(_funPrefix) and 
				self.funName in self.userFunctions):
			self.funName, self.args = self.userFunctions[self.funName](
				self.args)
		else:
			raise UfuncError("No such function: %s"%self.funName)


tree.registerNode(UserFunction)
