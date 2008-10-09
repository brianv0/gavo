"""
A macro mechanism primarily for string replacement in resource descriptors.
"""

from pyparsing import Word, OneOrMore, ZeroOrMore, QuotedString, Forward,\
	SkipTo, Optional, StringEnd, Regex, LineEnd, Suppress, ParserElement,\
	Literal, White, ParseException, dblQuotedString


import gavo
from gavo import config

class Error(gavo.Error):
	pass


class MacroExpander(object):
	"""is a generic "macro" expander for scripts of all kinds.

	It is loosely inspired by TeX, but of course much simpler.  See the
	syntax below.

	The macros themselves come from a MacroPackage object.  There are
	a few of the around, implementing different functionality depending
	on the script context (i.e., whether it belongs to an RD, a DD, or
	a Table.

	All macros are just functions receiving and returning strings.  Strings
	in Arguments must be quoted, the results of macro calls will not be
	quoted.

	The main entry point to the class is the expand function below,
	taking a string possibly containing macro calls and returning

	The construction of such a macro expander is relatively expensive,
	so it would pay to cache them.  MacroPackage below has a getExpander
	method that does the caching for you.
	"""
	def __init__(self, package):
		self.package = package
		self.grammar = self.getGrammar()

	def _execMacro(self, s, loc, toks):
		toks = toks.asList()
		macName, args = toks[0], toks[1:]
		return self.package.execMacro(macName, args)

	def expand(self, aString):
		return self.grammar.transformString(aString)

	def getGrammar(self, debug=False):
		macro = Forward()
		argument = QuotedString(quoteChar='"', escChar="\\", unquoteResults=True
			) | macro
		arguments = (Suppress( "{" ) + Optional( argument ) + 
			ZeroOrMore( Suppress(',') + argument) + Suppress( "}" ))
		macroName = Regex("[A-Za-z_][A-Za-z_0-9]+")
		macroName.setWhitespaceChars("")
		macro << Suppress( "\\" ) + macroName + Optional( arguments )
		macro.setParseAction(self._execMacro)
		literalBackslash = Literal("\\\\")
		literalBackslash.setParseAction(lambda *args: "\\")
		suppressedLF = Literal("\\\n")
		suppressedLF.setParseAction(lambda *args: " ")
		if debug:
			macro.setDebug(True)
			macro.setName("macro")
			argument.setDebug(True)
			argument.setName("arg")
			arguments.setDebug(True)
			arguments.setName("args")
			macroName.setDebug(True)
			macroName.setName("macname")
		return literalBackslash | suppressedLF | macro


class MacroPackage(object):
	r"""is a function dispatcher for MacroExpander.

	Basically, you inherit from this class and define macro_xxx functions.
	MacroExpander can then call \xxx, possibly with arguments.
	"""
	def execMacro(self, macName, args):
		fun = getattr(self, "macro_"+macName, None)
		if fun is None:
			raise Error("No such macro available in this context: \\%s"%macName)
		try:
			return fun(*args)
		except TypeError:
			raise Error("Invalid Arguments to \\%s: %s"%(macName, args))

	def getExpander(self):
		try:
			return self.__macroExpander
		except AttributeError:
			self.__macroExpander = MacroExpander(self)
			return self.getExpander()

	def macro_quote(self, arg):
		return '"%s"'%(arg.replace('"', '\\"'))


class StandardMacroMixin(MacroPackage):
	"""is  a mixin providing some macros for scripting's MacroExpander.

	The class mixing in needs to provide its resource descriptor in the
	rd attribute.
	"""
	def macro_schema(self):
		return self.rd.get_schema()
	
	def macro_RSTservicelink(self, serviceId, title=None):
		if title is None:
			title = serviceId
		return "`%s <%s>`_"%(title, makeSitePath(serviceId))

	def macro_servicelink(self, serviceId):
		return makeSitePath(serviceId)
	
	def macro_internallink(self, relPath):
		return makeSitePath(relPath)


######## misc functions used by macros, not necessarily in a good place,
######## but we want to keep internal imports at a minimum here.

def makeSitePath(uri):
	"""adapts uri for use in an off-root environment.

	uri itself needs to be server-absolute (i.e., start with a slash).
	"""
	if uri[0]!="/":
		uri = "/"+uri
	return config.get("web", "nevowRoot")+uri
