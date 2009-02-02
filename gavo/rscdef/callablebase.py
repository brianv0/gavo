"""
Base classes for callable RD items (rowgens, rowmaker procs, etc.)
"""

import traceback

from gavo import base
from gavo.base import codetricks
from gavo.rscdef import common
from gavo.rscdef import rmkfuncs


class FuncArg(base.Structure):
	"""An argument for a rowmaker, a rowgen, or similar code fragments.
	"""
	name_ = "arg"
	_key = base.UnicodeAttribute("key", default=base.Undefined,
		description="The name of the argument", copyable=True)
	_default = base.UnicodeAttribute("default", description=
		"A python expression (macros are expanded) getting assigned to"
		" the argument when it is is undefined at entering the function"
		" body", copyable=True)
	_code = base.DataContent(description="A python expression for"
		" the value of the argument in the actual parameter list",
		copyable=True)

	def validate(self):
		self._validateNext(FuncArg)
		if not common.identifierPat.match(self.key):
			raise base.LiteralParseError("Bad key for procedure argument: %s"%
				self.key)
		# Allow non-python syntax when things look like macro calls.
		if self.content_ and not "\\" in self.content_:
			codetricks.ensureExpression(self.content_, self.key)
		if self.default and not "\\" in self.default:
				codetricks.ensureExpression(self.default, self.key)


class CodeFrag(base.Structure):
	"""defines a code fragment (a proc or a rowgen).

	A codefrag contains source code and argument definitions.

	Source code provided is handed over the the compileContent method,
	to be defined by subclasses.

	See RDFunction or ConstComputer for sample subclasses.

	The functions returned receive a certain set of fixed arguments defined by
	the subclasses, plus defined arguments.  These are filled from <arg key="xy"
	default="zz">expr</arg> elements.  The content of these are python
	expressions or macro calls to be satisfied by the CodeFrag parents, similar
	for default.  Defaults become default arguments in the formal parameter
	list, the content ends up in the actual parameter list.

	Clients call two methods: getDefinition() returns a pair of 
	(name, callable) for insertion into namespaces, getCall() returns
	source code for a call for the procedure in a namespace reflecting
	getDefinition()
	"""
	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="A python identifier for the defined procedure",
		copyable=True)
	_args = base.StructListAttribute("args", description="Arguments for"
		" this proc", childFactory=FuncArg, copyable=True)
	_code = base.DataContent(copyable=True)
	_doc = base.UnicodeAttribute("doc", default="", description=
		"Human-readable docs for this proc (may be interpreted as restructured"
		" text)", copyable=True)
	_original = base.OriginalAttribute()

	def _getMoreGlobals(self):
		return None

	def _makeActualArgString(self):
		args = []
		for arg in self.args:
			if arg.content_:
				args.append("%s=%s"%(arg.key, arg.content_))
			else:
				args.append("%s=%s"%(arg.key, arg.key))
		self.actualArgString = ", ".join(args)

	def _getDefaultingFormalArgs(self):
		args = []
		for arg in self.args:
			if arg.default:
				args.append("%s=base.Undefined"%arg.key)
			else:
				args.append("%s"%arg.key)
		formalArgs = ", ".join(args)
		if "\\" in formalArgs:
			formalArgs = self.parent.expand(formalArgs)
		return formalArgs

	def _getDefaultingCode(self):
		# All lines must be indented with two spaces
		code = []
		for arg in self.args:
			if arg.default:
				code.append("  if %s is base.Undefined: %s = %s"%(
					arg.key, arg.key, arg.default))
		return "\n".join(code)
	
	def _sortArgs(self):
		withDefault, withoutDefault = [], []
		for arg in self.args:
			if arg.default:
				withDefault.append(arg)
			else:
				withoutDefault.append(arg)
		self.args = withoutDefault+withDefault

	def onElementComplete(self):
		self._sortArgs()
		self._makeActualArgString()
		self.defaultedNames = [a.key for a in self.args if a.default]
		self.funcBody = "%s\n%s"%(self._getDefaultingCode(),
			base.fixIndentation(self.content_, "  ", governingLine=1))
		self._onElementCompleteNext(CodeFrag)

	def getSource(self):
		args = self._getFormalArgs()
		code = self.funcBody
		if "\\" in code:
			code = self.parent.expand(code)
		return "def %s(%s):\n%s"%(self.name_, args, code)

	def getDefinition(self):
		"""returns a pair (name, function object) that defines the
		function.

		You will need this in the namespace in which the result of
		getCall is executed.
		"""
		try:
			return self.name, rmkfuncs.makeCallable(self.name_, self.getSource(),
				self._getMoreGlobals())
		except Exception, msg:
			traceback.print_exc() # XXX TODO: make this available to user somehow
			raise base.LiteralParseError("Invalid code in %s\n"
				"Diagnosis: %s\n"%(self.name, str(msg)), self.name, self.content_)

	def getCall(self):
		"""returns python code to call the function defined.
		"""
		actArgs = self.actualArgString
		if "\\" in actArgs:
			actArgs = self.parent.expand(actArgs)
		return self._completeCall(actArgs)
	
	def runWithArgs(self, argsDef, nsp):
		"""returns the result of running the function within nsp, with
		values from argsDef in nsp.

		argsDef is a sequence of FuncArg objects, nsp is some dictionary.
		nsp will be changed by this call.

		This method is used when instanciating predefined RDFunctions; you
		probably should not otherwise use it since it will compile self
		on each invocation and thus is slow.
		"""
		name, func = self.getDefinition()
		nsp[name] = func
		code = "\n".join("%s = %s"%(a.key, a.default) for a in self.args
			if a.default)+"\n"
		code += "\n".join("%s = %s"%(a.key, a.content_) for a in argsDef)
		try:
			exec code in nsp
		except NameError, msg:
			raise base.LiteralParseError("%s while trying to run %s.  This probably"
				" means that a variable you used in the arguments is not defined"
				" or you simply forgot to quote a value."%(msg, name), name,
					code)
		return eval(self.getCall(), nsp)
