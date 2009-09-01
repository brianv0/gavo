"""
A macro mechanism primarily for string replacement in resource descriptors.
"""

import datetime

from pyparsing import Word, OneOrMore, ZeroOrMore, QuotedString, Forward,\
	SkipTo, Optional, StringEnd, Regex, LineEnd, Suppress, ParserElement,\
	Literal, White, ParseException, dblQuotedString


from gavo import base


class MacroExpander(object):
	"""is a generic "macro" expander for scripts of all kinds.

	It is loosely inspired by TeX, but of course much simpler.  See the
	syntax below.

	The macros themselves come from a MacroPackage object.  There are
	a few of the around, implementing different functionality depending
	on the script context (i.e., whether it belongs to an RD, a DD, or
	a Table.

	All macros are just functions receiving and returning strings.  The
	arguments are written as {arg1}{arg2}, where you can escape curly
	braces with a backslash.  There must be no whitespace between
	a macro and its first argument.

	If you need to glue together a macro expansion and text following,
	use the glue sequence \\+

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
		quoteEscape = (Literal("\\{").addParseAction(lambda *args: "{") | 
			Literal("\\}").addParseAction(lambda *args: "}"))
		charRun = Regex(r"[^}\\]+")
		argElement = macro | quoteEscape | charRun
		argument = Suppress("{") + ZeroOrMore(argElement) + Suppress("}")
		argument.addParseAction(lambda s, pos, toks: "".join(toks))
		arguments = ZeroOrMore(argument)
		arguments.setWhitespaceChars("")
		macroName = Regex("[A-Za-z_][A-Za-z_0-9]+")
		macroName.setWhitespaceChars("")
		macro << Suppress( "\\" ) + macroName + arguments
		macro.addParseAction(self._execMacro)
		literalBackslash = Literal("\\\\")
		literalBackslash.addParseAction(lambda *args: "\\")
		suppressedLF = Literal("\\\n")
		suppressedLF.addParseAction(lambda *args: " ")
		glue = Literal("\\+")
		glue.addParseAction(lambda *args: "")
		if debug:
			macro.setDebug(True)
			macro.setName("macro")
			argument.setDebug(True)
			argument.setName("arg")
			arguments.setDebug(True)
			arguments.setName("args")
			macroName.setDebug(True)
			macroName.setName("macname")
		return literalBackslash | suppressedLF | glue | macro


class MacroPackage(object):
	r"""is a function dispatcher for MacroExpander.

	Basically, you inherit from this class and define macro_xxx functions.
	MacroExpander can then call \xxx, possibly with arguments.
	"""
	def __findMacro(self, macName):
		fun = getattr(self, "macro_"+macName, None)
		if fun is not None:
			return fun
		if hasattr(self, "rd"):
			fun = getattr(self.rd, "macro_"+macName, None)
		if fun is not None:
			return fun
		raise base.LiteralParseError(
			"No such macro available in this context: \\%s"%macName,
			"macro", macName)

	def execMacro(self, macName, args):
		fun = self.__findMacro(macName)
		try:
			return fun(*args)
		except TypeError:
			raise base.LiteralParseError(
				"Invalid Arguments to \\%s: %s"%(macName, args), "macro",
					"%s/%s"%(macName, args))

	def getExpander(self):
		try:
			return self.__macroExpander
		except AttributeError:
			self.__macroExpander = MacroExpander(self)
			return self.getExpander()

	def expand(self, stuff):
		return self.getExpander().expand(stuff)

	def macro_quote(self, arg):
		return '"%s"'%(arg.replace('"', '\\"'))


class StandardMacroMixin(MacroPackage):
	"""is  a mixin providing some macros for scripting's MacroExpander.

	The class mixing in needs to provide its resource descriptor in the
	rd attribute.
	"""
	def macro_rdId(self):
		return self.rd.sourceId

	def macro_schema(self):
		return self.rd.schema
	
	def macro_RSTservicelink(self, serviceId, title=None):
		if title is None:
			title = serviceId
		return "`%s <%s>`_"%(title, base.makeSitePath(serviceId))

	def macro_servicelink(self, serviceId):
		return base.makeSitePath(serviceId)
	
	def macro_internallink(self, relPath):
		return base.makeSitePath(relPath)

	def macro_today(self):
		return str(datetime.date.today())

	def macro_getConfig(self, section, name=None):
		"""returns the current value of configuration item {section}{name}.

		You can also only give one argument to access settings from the
		general section.
		"""
		if name is None:
			section, name = "general", section
		return str(base.getConfig(section, name))

	def macro_test(self, *args):
		"""always replaces macro call with "test macro expansion"

		For testing purposes.
		"""
		return "test macro expansion"


class MacDef(base.Structure):
	"""A macro definition within an RD.

	The macro defined is available on the parent.
	"""
	name_ = "macDef"

	_name = base.UnicodeAttribute("name", description="Name the macro"
		" will be available as", copyable=True, default=base.Undefined)
	_content = base.DataContent(description="Replacement text of the"
		" macro")

	def onElementComplete(self):
		self._onElementCompleteNext(MacDef)
		def mac():
			return self.content_
		setattr(self.parent, "macro_"+self.name, mac)


def MacDefAttribute(**kwargs):
	return base.StructListAttribute("macDefs", childFactory=MacDef,
		**kwargs)
