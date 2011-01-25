"""
Basic handling for embedded procedures.
"""

import itertools

from gavo import base
from gavo import utils
from gavo.rscdef import common
from gavo.rscdef import rmkfuncs


class RDParameter(base.Structure):
	"""A base class for parameters.
	"""
	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="The name of the parameter", copyable=True, strip=True,
		aliases=["key"])
	_descr = base.NWUnicodeAttribute("description", default=None,
		description="Some human-readable description of what the"
		" parameter is about", copyable=True, strip=True)
	_expr = base.DataContent(description="The default for the parameter.",
		copyable=True, strip=True)
	_late = base.BooleanAttribute("late", default=False,
		description="Bind the name not at setup time but while applying"
		" the procedure.  This allows you to refer to procedure arguments"
		" like vars or rowIter in the bindings.")

	def isDefaulted(self):
		return self.content_!=""

	def validate(self):
		self._validateNext(RDParameter)
		if not utils.identifierPattern.match(self.name):
			raise base.LiteralParseError("name", self.name, hint=
				"The name you supplied was not defined by any procedure definition.")


class ProcPar(RDParameter):
	"""A parameter of a procedure definition.

	Bodies of ProcPars are interpreted as python expressions, in
	which macros are expanded in the context of the procedure application's
	parent.  If a body is empty, the parameter has no default and has
	to be filled by the procedure application.
	"""
	name_ = "par"
	def validate(self):
		self._validateNext(ProcPar)
		# Allow non-python syntax when things look like macro calls.
		if self.content_ and not "\\" in self.content_:
			utils.ensureExpression(
				common.replaceRMKAt(self.content_), self.name)


class Binding(ProcPar):
	"""A binding of a procedure definition parameter to a concrete value.

	The value to set is contained in the binding body in the form of
	a python expression.  The body must not be empty.
	"""
	name_ = "bind"

	def validate(self):
		self._validateNext(Binding)
		if not self.content_ or not self.content_.strip():
			raise base.StructureError("Binding bodies must not be empty.")


class ProcSetup(base.Structure):
	"""Prescriptions for setting up a namespace for a procedure application.

	You can add names to this namespace you using par(ameter)s.
	If a parameter has no default and an procedure application does
	not provide them, an error is raised.

	You can also add names by providing a code attribute containing
	a python function body in code.  Within, the parameters are
	available.  The procedure application's parent can be accessed
	as parent.  All names you define in the code are available as
	globals to the procedure body.
	"""
	name_ = "setup"

	_code = base.ListOfAtomsAttribute("codeFrags",
		description="Python function bodies setting globals for the function"
		" application.  Macros are expanded in the context"
		" of the procedure's parent.", 
		itemAttD=base.UnicodeAttribute("code", description="Python function"
			" bodies setting globals for the function application.  Macros"
			" are expanded in the context of the procedure's parent.",
			copyable=True),
		copyable=True)
	_pars = base.StructListAttribute("pars", ProcPar,
		description="Names to add to the procedure's global namespace.", 
		copyable=True)
	_original = base.OriginalAttribute()

	def _getParSettingCode(self, useLate, indent, bindings):
		"""returns code that sets our parameters.

		If useLate is true, generate for late bindings.  Indent the
		code by indent.  Bindings is is a dictionary overriding
		the defaults or setting parameter values.
		"""
		parCode = []
		for p in self.pars:
			if p.late==useLate:
				val = bindings.get(p.name, base.NotGiven)
				if val is base.NotGiven:
					val = p.content_
				parCode.append("%s%s = %s"%(indent, p.name, val))
		return "\n".join(parCode)

	def getParCode(self, bindings):
		"""returns code doing setup bindings un-indented.
		"""
		return self._getParSettingCode(False, "", bindings)

	def getLateCode(self, bindings):
		"""returns code doing late (in-function) bindings indented with two
		spaces.
		"""
		return self._getParSettingCode(True, "  ", bindings)

	def getBodyCode(self):
		"""returns the body code un-indented.
		"""
		collectedCode = []
		for frag in self.codeFrags:
			collectedCode.append(
				utils.fixIndentation(frag, "", governingLine=1))
		return "\n".join(collectedCode)

_emptySetup = ProcSetup(None, code="")


class ProcDef(base.Structure, base.RestrictionMixin):
	"""An embedded procedure.

	Embedded procedures are python code fragments with some interface defined
	by their type.  They can occur at various places (which is called procedure
	application generically), e.g., as row generators in grammars, as applys in
	rowmakers, or as SQL phrase makers in condDescs.

	They consist of the actual actual code and, optionally, definitions like
	the namespace setup, configuration parameters, or a documentation.

	The procedure applications compile into python functions with special
	global namespaces.  The signatures of the functions are determined by
	the type attribute.

	ProcDefs are referred to by procedure applications using their id.
	"""
	name_ = "procDef"

	_code = base.UnicodeAttribute("code", default=base.NotGiven,
		copyable=True, description="A python function body.")
	_setup = base.StructAttribute("setup", ProcSetup, default=_emptySetup,
		description="Setup of the namespace the function will run in", 
		copyable=True)
	_doc = base.UnicodeAttribute("doc", default="", description=
		"Human-readable docs for this proc (may be interpreted as restructured"
		" text).", copyable=True)
	_type = base.EnumeratedUnicodeAttribute("type", default=None, description=
		"The type of the procedure definition.  The procedure applications"
		" will in general require certain types of definitions.",
		validValues=["t_t", "apply", "rowfilter", "sourceFields", "mixinProc",
			"phraseMaker"], 
			copyable=True,
		strip=True)
	_original = base.OriginalAttribute()

	def getCode(self):
		"""returns the body code indented with two spaces.
		"""
		if self.code is base.NotGiven:
			return ""
		else:
			return utils.fixIndentation(self.code, "  ", governingLine=1)


class ProcApp(ProcDef):
	"""An abstract base for procedure applications.

	Deriving classes need to provide:

		- a requiredType attribute specifying what ProcDefs can be applied.
		- a formalArgs attribute containing a (python) formal argument list
		- of course, a name_ for XML purposes.
	"""
	_procDef = base.ReferenceAttribute("procDef", forceType=ProcDef,
		default=base.NotGiven, description="Reference to the procedure"
		" definition to apply", copyable=True)
	_bindings = base.StructListAttribute("bindings", description=
		"Values for parameters of the procedure definition",
		childFactory=Binding, copyable=True)
	_name = base.UnicodeAttribute("name", default=base.NotGiven,
		description="A name of the proc.  ProcApps compute their (python)"
		" names to be somwhat random strings.  Set a name manually to"
		" receive easier decipherable error messages.  If you do that,"
		" you have to care about name clashes yourself, though.", strip=True)

	requiredType = None

	def completeElement(self, ctx):
		self._completeElementNext(ProcApp, ctx)
		if self.name is base.NotGiven:  # make up a name from self's id
			self.name = ("proc%x"%id(self)).replace("-", "")

	def _ensureParsBound(self):
		"""raises an error if non-defaulted pars of procDef are not filled
		by the bindings.
		"""
		if self.procDef is base.NotGiven:
			pdNames = []
		else:
			pdNames = self.procDef.setup.pars
		bindNames = set(b.name for b in self.bindings)
		for p in itertools.chain(pdNames, self.setup.pars):
			if not p.isDefaulted():
				if not p.name in bindNames:
					raise base.StructureError("Parameter %s is not defaulted in"
						" %s and thus must be bound."%(p.name, self.name))
			if p.name in bindNames:
				bindNames.remove(p.name)
		if bindNames:
			raise base.StructureError("May not bind non-existing parameter(s)"
				" %s."%(", ".join(bindNames)))

	def validate(self):
		self._validateNext(ProcApp)
		self._ensureParsBound()

	def onElementComplete(self):
		self._onElementCompleteNext(ProcApp)
		self._boundNames = dict((b.name, b.content_) for b in self.bindings)

	def getSetupCode(self):
		setupLines = []
		if self.procDef is not base.NotGiven:
			setupLines.append(self.procDef.setup.getParCode(self._boundNames))
		setupLines.append(self.setup.getParCode(self._boundNames))
		if self.procDef is not base.NotGiven:
			setupLines.append(self.procDef.setup.getBodyCode())
		setupLines.append(self.setup.getBodyCode())
		code = "\n".join(setupLines)
		if "\\" in code:
			code = self.parent.expand(code)
		return code

	def _getFunctionDefinition(self, mainSource):
		"""returns mainSource in a function definition with proper 
		signature including setup of late code.
		"""
		parts = []

		# "late" code from the procDef's and own setup code is executed
		# on each invocation.
		if self.procDef is not base.NotGiven:
			parts.append(self.procDef.setup.getLateCode(self._boundNames))
		parts.append(self.setup.getLateCode(self._boundNames))
		parts.append(mainSource)
		body = "\n".join(parts)
		if not body.strip():
			body = "  pass"
		return "def %s(%s):\n%s"%(self.name, self.formalArgs,
			body)

	def getFuncCode(self):
		"""returns a function definition for this proc application.

		This includes bindings of late parameters.

		Locally defined code overrides code defined in a procDef.
		"""
		mainCode = ""
		if self.code is base.NotGiven:
			if self.procDef is not base.NotGiven:
				mainCode = self.procDef.getCode()
		else:
			mainCode = self.getCode()
		code = self._getFunctionDefinition(mainCode)
		if "\\" in code:
			code = self.parent.expand(code)
		return code

	def _compileForParent(self, parent):
		"""helps compile.
		"""
		return rmkfuncs.makeProc(
				self.name, self.getFuncCode(),
				self.getSetupCode(), parent)

	def compile(self, parent=None):
		"""returns a callable for this procedure application.

		You can pass a different parent; it will then be used to
		expand macros.  If you do not give it, the embedding structure will
		be used.
		"""
		if parent is None:
			parent = self.parent
		return utils.memoizeOn(parent, self, self._compileForParent, parent)
