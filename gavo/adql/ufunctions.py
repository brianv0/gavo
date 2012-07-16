"""
"User" defined functions, i.e., ADQL functions defined only on this
system.

See the userFunction docstring on how to use these.
"""


import warnings

from gavo import utils
from gavo.adql import common
from gavo.adql import grammar
from gavo.adql import fieldinfo
from gavo.adql import nodes
from gavo.adql import tree


UFUNC_REGISTRY = {}


def userFunction(name, signature, doc, returntype="double precision", 
		unit="", ucd=""):
	"""a decorator adding some metadata to python functions to make
	them suitable as ADQL user defined functions.

	name is the name the function will be visible under in ADQL; signature is a
	signature not including the name of the form '(parName1 type1, parName1
	type2) -> resulttype'; doc is preformatted ASCII documentation.  The
	indentation of the second line will be removed from all lines.

	returntype is the SQL return type, which defaults to double
	precision.  With current ADQL, you could specialize to INTEGER
	if you like, but there's little in the way of variation on top
	of that since user defined functions must be numeric.  unit and
	ucd are optional for when you actually have a good guess what's
	coming back from your ufunc.

	The python function receives an array of arguments; this will in
	general be ADQL expression trees.  It must return either a string that
	will go literally into the SQL string (so take care to quote;
	in general, you will use nodes.flatten(arg) to flatten individual
	args); or they may return None, in which case the expression tree
	remains unchanged.  This is for when the actual implementation is
	in the database.

	If you receive bad arguments or something else goes awry, raise
	a UfuncError.
	"""
	def deco(f):
		f.adqlUDF_name = name
		f.adqlUDF_signature = f.adqlUDF_name+signature.strip()
		f.adqlUDF_doc = utils.fixIndentation(doc, "", 1).strip()
		f.adqlUDF_returntype = returntype
		f.adqlUDF_unit = unit
		f.adqlUDF_ucd = ucd
		UFUNC_REGISTRY[f.adqlUDF_name.upper()] = f
		return f
	return deco


@userFunction("gavo_match",
	"(pattern TEXT, string TEXT) -> INTEGER",
	"""
	gavo_match returns 1 if the POSIX regular expression pattern
	matches anything in string, 0 otherwise.
	""",
	"integer")
def _match(args):
	if len(args)!=2:
		raise UfuncError("gavo_match takes exactly two arguments")
	return "(CASE WHEN %s ~ %s THEN 1 ELSE 0 END)"%(
		nodes.flatten(args[1]), nodes.flatten(args[0]))


@userFunction("ivo_hasword",
	"(haystack TEXT, needle TEXT) -> INTEGER",
	"""
	gavo_hasword returns 1 if needle shows up in haystack, 0 otherwise.  This
	is for "google-like"-searches in text-like fields.  In word, you can
	actually employ a fairly complex query language; see
	http://www.postgresql.org/docs/8.3/static/textsearch.html
	for details.
	""",
	"integer")
def _hasword(args):
	if len(args)!=2:
		raise UfuncError("ivo_hasword takes exactly two arguments")
	return None


@userFunction("ivo_nocasecmp",
	"(arg1 TEXT, arg2 TEXT) -> INTEGER",
	"""
	gavo_nocasecmp returns 1 if arg1 and arg2 compare equal after normalizing
	case.   The behaviour with non-ASCII characters depends on the
	server locale and is thus not well predictable.
	""",
	"integer")
def _nocasecmp(args):
	if len(args)!=2:
		raise UfuncError("ivo_nocasecmp takes exactly two arguments")
	return None


@userFunction("ivo_hashlist_has",
	"(hashlist TEXT, item TEXT) -> INTEGER",
	"""
	The function takes two strings; the first is a list of words not
	containing the hash sign (#), concatenated by hash signs, the second is
	a word not containing the hash sign.  It returns 1 if, compared
	case-insensitively, the second argument is in the list of words coded in
	the first argument.  The behaviour in case the the second
	argument contains a hash sign is unspecified.
	""",
	"integer")
def _hashlist_has(args):
	if len(args)!=2:
		raise UfuncError("ivo_nocasecmp takes exactly two arguments")
	return None


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
		if self.processedExpression is None:
			return nodes.FunctionNode.flatten(self)
		else:
			return self.processedExpression

	def addFieldInfo(self, context):
		try:
			ufunc = UFUNC_REGISTRY[self.funName.upper()]
		except KeyError:
			raise common.UfuncError("No such function: %s"%self.funName)
		self.fieldInfo = fieldinfo.FieldInfo(ufunc.adqlUDF_returntype, 
			ufunc.adqlUDF_unit, ufunc.adqlUDF_ucd)


tree.registerNode(UserFunction)
