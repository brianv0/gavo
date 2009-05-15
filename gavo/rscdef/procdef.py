"""
Basic handling for embedded procedures.

"""

import itertools

from gavo import base
from gavo import utils
from gavo.rscdef import common
from gavo.rscdef import rmkfuncs


class ProcPar(base.Structure):
	"""A parameter of a procedure definition.

	Bodies of ProcPars are interpreted as python expressions, in
	which macros are expanded in the context of the procedure application's
	parent.  If a body is empty, the parameter has no default and has
	to be filled by the procedure application.
	"""
	name_ = "par"
	_key = base.UnicodeAttribute("key", default=base.Undefined,
		description="The name of the parameter", copyable=True)
	_expr = base.DataContent(description="A python expression for"
		" the default of the parameter", copyable=True)

	def validate(self):
		self._validateNext(ProcPar)
		if not common.identifierPat.match(self.key):
			raise base.LiteralParseError("Bad key for procedure argument: '%s'"%
				self.key, "key", self.key)
		# Allow non-python syntax when things look like macro calls.
		if self.content_ and not "\\" in self.content_:
			utils.ensureExpression(self.content_, self.key)

	def isDefaulted(self):
		return self.content_!=""


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
	not provide them, an errror is raised.

	You can also add names by providing a code attribute containing
	a python function body in code.  Within, the parameters are
	available.  The procedure application's parent can be accessed
	as parent.  All names you define in the code are available as
	globals to the procedure body.
	"""
	_code = base.UnicodeAttribute("code", copyable=True, 
		description="A python function body setting globals for the function"
		" application.  Macros are expanded in the context"
		" of the procedure's parent.", default="")
	_pars = base.StructListAttribute("pars", ProcPar,
		description="Names to add to the procedure's global namespace.", 
		copyable=True)

	def getParCode(self):
		parCode = []
		for p in self.pars:
			if p.content_:
				parCode.append("%s = %s"%(p.key, p.content_))
		return "\n".join(parCode)
	
	def getBodyCode(self):
		return utils.fixIndentation(self.code, "", governingLine=1)

_emptySetup = ProcSetup(None, code="")


class ProcDef(base.Structure):
	"""An embedded procedure.

	Embedded procedures are code fragments that do fancy things in, e.g.,
	grammars (row generators) or rowmakers (call).

	They consist of the actual application and, optionally, definitions.

	Definitions have par elements that allow "configuration" of the applications.
	Par elements without defaults need to be filled out by applications.

	The applications themselves compile into python functions with special
	global namespaces.  The signatures of the functions are determined by
	the type attribute.

	ProcDefs are referred to by function applications using their id.
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
		validValues=["t_", "apply"], copyable=True)

	def getCode(self):
		if self.code is base.NotGiven:
			return ""
		else:
			return utils.fixIndentation(self.code, "  ", governingLine=1)


class ProcApp(ProcDef):
	"""An abstract base for procedure applications.

	Deriving classes need to provide:

	* a requiredType attribute specifying what ProcDefs can be applied.
	* a formalArgs attribute containing a (python) formal argument list
	* of course, a name_ for XML purposes.
	"""
	_procDef = base.ReferenceAttribute("procDef", forceType=ProcDef,
		default=base.NotGiven, description="Reference to the procedure"
		" definition to apply", copyable=True)
	_bindings = base.StructListAttribute("bindings", description=
		"Values for parameters of the procedure definition",
		childFactory=Binding, copyable=True)
	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="A name of the proc.  You are responsible to"
		" avoid name clashes.")

	compiled = None

	def _ensureParsBound(self):
		"""raises an error if non-defaulted pars of procDef are not filled
		by the bindings.
		"""
		if self.procDef is base.NotGiven:
			pdNames = []
		else:
			pdNames = self.procDef.setup.pars
		bindNames = set(b.key for b in self.bindings)
		for p in itertools.chain(pdNames, self.setup.pars):
			if not p.isDefaulted():
				if not p.key in bindNames:
					raise base.StructureError("Parameter %s is not defaulted in"
						" %s and thus must be bound."%(p.key, self.name))
			if p.key in bindNames:
				bindNames.remove(p.key)
		if bindNames:
			raise base.StructureError("May not bind non-existing parameter(s)"
				" %s."%(", ".join(bindNames)))

	def validate(self):
		self._validateNext(ProcApp)
		self._ensureParsBound()

	def getBindingCode(self):
		bindCode = []
		for b in self.bindings:
			if b.content_:
				bindCode.append("%s = %s"%(b.key, b.content_))
		return "\n".join(bindCode)

	def getSetupCode(self):
		# First, assign pars from procDef's procSetup, then our pars, then
		# our bindings.  Then execute procDef's procSetup code, and finally ours.
		setupLines = []
		if self.procDef is not base.NotGiven:
			setupLines.append(self.procDef.setup.getParCode())
		setupLines.append(self.setup.getParCode())
		setupLines.append(self.getBindingCode())
		if self.procDef is not base.NotGiven:
			setupLines.append(self.procDef.setup.getBodyCode())
		setupLines.append(self.setup.getBodyCode())
		return "\n".join(setupLines)

	def getFuncCode(self):
		if self.code is base.NotGiven:
			if self.procDef is base.NotGiven:
				body = ""
			else:
				body = self.procDef.getCode()
		else:
			body = self.getCode()
		if not body.strip():
			body = "  pass"
		return "def %s(%s):\n%s"%(self.name, self.formalArgs,
			body)

	def compile(self, parent):
		self.compiled = rmkfuncs.makeProc(
			self.name, parent.expand(self.getFuncCode()), 
			parent.expand(self.getSetupCode()), parent)
	
	def __call__(self, *args):
		if self.compiled is None:
			raise base.Error("Internal error: procedure application not compiled.")
		return self.compiled(*args)
