"""
"User" defined functions, i.e., ADQL functions defined only on this
system.

See the userFunction docstring on how to use these.
"""


import warnings

from gavo import utils
from gavo.adql import common
from gavo.adql import grammar
from gavo.adql import nodes
from gavo.adql import tree


UFUNC_REGISTRY = {}


def userFunction(name, signature, doc):
	"""a decorator adding some metadata to python functions to make them
	suitable as ADQL user defined functions.

	name is the name the function will be visible under in ADQL, *without*
	the _funPrefix; signature is a signature not including the name of
	the form '(parName1 type1, parName1 type2) -> resulttype'; doc
	is preformatted ASCII documentation.  The indentation of the second
	line will be removed from all lines.

	The python function receives an array of arguments; this will in general
	be ADQL expression trees.  It must return a string that will go
	literally into the SQL string, so beware quoting.  In general,
	you will use nodes.flatten(arg) to flatten individual args.

	If you receive bad arguments or something else goes awry, raise
	a UfuncError.
	"""
	def deco(f):
		f.adqlUDF_name = grammar.userFunctionPrefix+name
		f.adqlUDF_signature = f.adqlUDF_name+signature.strip()
		f.adqlUDF_doc = utils.fixIndentation(doc, "", 1).strip()
		UFUNC_REGISTRY[f.adqlUDF_name.upper()] = f
		return f
	return deco


@userFunction("match",
	"(pattern TEXT, string TEXT) -> INTEGER",
	"""
	gavo_match returns 1 if the POSIX regular expression pattern
	matches anything in string, 0 otherwise.
	""")
def _match(args):
	if len(args)!=2:
		raise UfuncError("match takes exactly two arguments")
	return "(CASE WHEN %s ~ %s THEN 1 ELSE 0)"%(
		nodes.flatten(args[1]), nodes.flatten(args[0]))


class UserFunction(nodes.FunctionNode):
	"""A node processing user defined functions.

	See the userFunction docstring for how ADQL user defined functions
	are defined.
	"""
	type = "userDefinedFunction"

	def _polish(self):
		try:
			self.processedExpression = UFUNC_REGISTRY[self.funName.upper()](
				self.args)
		except KeyError:
			raise common.UfuncError("No such function: %s"%self.funName)

	def flatten(self):
		return self.processedExpression

tree.registerNode(UserFunction)
