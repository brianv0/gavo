"""
Definition of rowmakers.

rowmakers are objects that take a dictionary of some kind and emit
a row suitable for inclusion into a table.
"""

import bisect
import fnmatch
import os
import sys
import traceback

from gavo import base
from gavo import utils
from gavo.base import structure
from gavo.rscdef import callablebase
from gavo.rscdef import common
from gavo.rscdef import macros
from gavo.rscdef import procdef
from gavo.rscdef import rmkfuncs
from gavo.rscdef import rmkprocs
from gavo.rscdef import tabledef


class Error(base.Error):
	pass


class _NotGiven(object):
	"""is a sentinel for MapRule defaults.
	"""


class MapRule(base.Structure):
	"""A mapping rule.

	To specify the source of a mapping, you can either
	
	* use a key emitted by the grammar or defined using var.  The value of 
	  of the key is converted to a python value and stored.
	* or give a python expression in the body.  In that case, no further
	  type conversion will be attempted.

	If src is not given, it defaults to dest.
	"""
	name_ = "map"

	_dest = base.UnicodeAttribute("dest", default=base.Undefined, 
		description="Name of the column the value is to end up in.",
		copyable=True)
	_src = base.UnicodeAttribute("src", default=None,
		description="Source key name to convert to column value (either a grammar"
		" key or a var).", copyable=True)
	_nullExcs = base.UnicodeAttribute("nullExcs", default=base.NotGiven,
		description="A python tuple of exceptions that should be caught and"
		" cause the value to be NULL.")
	_expr = base.DataContent(copyable=True, description="A python"
		" expression giving the value to end up in dest")


	def completeElement(self):
		if not self.content_ and not self.src:
			self.src = self.dest
		if self.content_ and "\\" in self.content_:
			self.content_ = self.parent.expand(self.content_)

	def validate(self):
		"""checks that code content is a parseable python expression and that
		the destination exists in the tableDef
		"""
		self._validateNext(MapRule)
		if (self.content_ and self.src) or not (self.content_ or self.src):
			raise base.StructureError("Map must have exactly one of src attribute"
				" or element content")
		if self.content_:
			utils.ensureExpression(self.content_, self.name_)
		if self.nullExcs is not base.NotGiven:
			utils.ensureExpression(self.nullExcs, "%s.nullExcs"%(self.name_))

	def getCode(self, tableDef):
		"""returns python source code for this map.
		"""
		code = []
		if self.content_:
			code.append('_result["%s"] = %s'%(self.dest, self.content_))
			if self.nullExcs is not base.NotGiven:
				code = ["try:\n  ", code[0], 
					'\nexcept (%s): _result["%s"] = None'%(self.nullExcs, self.dest)]
		else:
			colDef = tableDef.getColumnByName(self.dest)
			if colDef.values and colDef.values.nullLiteral is not None:
				code.append("if %s=='%s':\n  _result['%s'] = None\nelse:"%(self.src,
					colDef.values.nullLiteral, self.dest))
			try:
				code.append('_result["%s"] = %s'%(self.dest, 
					base.sqltypeToPythonCode(colDef.type)%self.src))
			except base.ConversionError:
				raise base.LiteralParseError("Auto-mapping to %s is impossible since"
					" no default map for %s is known"%(self.dest, colDef.type),
					"map", colDef.type)
		return "".join(code)


class VarDef(base.Structure):
	"""A definition of a rowmaker variable.

	It consists of a name and a python expression, including function
	calls.  The variables are entered into the input row coming from
	the grammar.
	"""
	name_ = "var"
	
	_name = base.UnicodeAttribute("name", default=base.Undefined, 
		description="Name of the variable (under which it can later be"
			" referred to", copyable=True)
	_expr = base.DataContent(copyable=True, description="A python expression."
		" Its value is accessible under the key name in the input row.")

	def completeElement(self):
		if self.content_ and "\\" in self.content_:
			self.content_ = self.parent.expand(self.content_)

	def validate(self):
		"""checks that code content is a parseable python expression and that
		name is a valid python identifier.
		"""
		self._validateNext(VarDef)
		if self.content_:
			utils.ensureExpression(self.content_, self.name_)
		if not common.identifierPat.match(self.name):
			raise base.LiteralParseError("Var names must be valid python"
				" identifiers, and %s is not"%self.name, "name", self.name)

	def getCode(self):
		return "%s = %s"%(self.name, self.parent.expand(self.content_))

############# Start DEPRECATED
class ConsComputer(callablebase.CodeFrag):
	"""A code fragment for the computation of locals rowmaker procs, rowgens,
	and similar constructs.

	ConsComputers have python code in their bodies.  The python code must
	return a dictionary.  The keys in this dictionary are available as
	variables in the respective function.

	You can use this to precompute values that are identical for all items
	a given callable returns.
	"""
	name_ = "consComp"

	def _getFormalArgs(self):
		return self._getDefaultingFormalArgs()

	def completeElement(self):
		if self.name is base.Undefined:
			self.name = "consComp"
		self._completeElementNext(ConsComputer)

	def _completeCall(self, actualArgs):
		return "%s(%s)"%(self.name, actualArgs)


class ConsArg(callablebase.FuncArg):
	"""An argument to a rowmaker constructor.

	See `Element rowmaker`_
	"""
	name_ = "consArg"


class RDFunction(callablebase.CodeFrag):
	"""is a CodeFrag that has an embedded code frag to compute locals
	for the compilation of the actual function body.

	These are used for functions defined in resource descriptors like
	rowmaker procs or grammar rowgens.

	RDfunctions do not necessarily contain code but can locate
	predefined functions registered in something accessible through the
	getPredefined method.  Registration is done via the registerPredefined
	method.  Both methods have to be defined by subclasses.
	"""
	_consComp = base.StructAttribute("consComp", default=None,
		childFactory=ConsComputer, copyable=True, description="A callable"
		" returning a dictionary with additional names available to the callable"
		" defined.")
	_consArgs =  base.StructListAttribute("consArgs", 
		description="Arguments for this callable's constructor.", 
		childFactory=ConsArg)
	_predefined = base.UnicodeAttribute("predefined", default=None,
		description="Name of a predefined procedure to base this one on.")
	_isGlobal = base.BooleanAttribute("isGlobal", default=False,
		description="Register this procedure globally under its name.")

	def validate(self):
		"""checks that there's not both code and predefined given.
		"""
		self._validateNext(RDFunction)
		if (self.content_.strip() and self.predefined) or not (
				self.content_.strip() or self.predefined):
			raise base.StructureError(
				"%s must have exactly one of predefined attribute"
				" or element content"%self.name_)

	def onElementComplete(self):
		self._onElementCompleteNext(RDFunction)
		if self.isGlobal:
			self.registerPredefined()
	
	def completeElement(self):
		self._completeElementNext(RDFunction)
		if self.predefined:
			self._getFromPredefined()
	
	def _getFromPredefined(self):
		orig = self.getPredefined(self.predefined)
		self.predefined = None
		self.content_ = orig.content_
		if self.consComp is None:
			self.consComp = orig.consComp
		if self.name is base.Undefined:
			self.name = orig.name
		localArgs = set(a.key for a in self.args)
		for a in orig.args:
			if not a.key in localArgs:
				self._args.feedObject(self, a.copy(self))

	def _getMoreGlobals(self):
		"""returns a dictionary containing additional names got from consComp.

		If no consComp is defined, it returns and empty dictionary.

		It does some basic validation making sure what's returned behaves
		roughly like a dictionary.
		"""
		if not self.consComp:
			return {}
		moreLocals = self.consComp.runWithArgs(self.consArgs, {})
		try:
			moreLocals["some improbable key_"]
		except KeyError: # looks like a dict, ok
			pass
		except TypeError:
			raise base.LiteralParseError("consComp on %s does not return a"
				" dict"%self.name, "consComp", self.consComp)
		return moreLocals


class ProcDef(RDFunction):
	"""A procedure within a row maker.

	Procedures contain python code that manipulates the grammar output (as vars)
	and the row to be shipped out (as _result).  The code also has access
	to the tableDef (e.g., to retrieve properties).
	"""
	name_ = "proc"

	def registerPredefined(self):
		rmkprocs.registerProcedure(self.name, self)

	def getPredefined(self, name):
		return rmkprocs.getProcedure(name)

	def _getFormalArgs(self):
		return "result, vars, tableDef, "+self._getDefaultingFormalArgs()

	def _completeCall(self, actualArgs):
		"""returns a function call for to this procedure with actual arguments
		inserted.
		"""
		return "%s(_result, rowdict_, tableDef_, %s)"%(self.name, actualArgs)

############# End DEPRECATED

class ApplyDef(procdef.ProcApp):
	"""A code fragment to manipulate the result row (and possibly more).

	Apply elements yaddayadda.

	The current input fields from the grammar (including the rowmaker's vars) 
	are available in the vars dictionary and can be changed there.  You can 
	also add new keys.

	You can add new keys for shipping out in the result dictionary.

	The active rowmaker is available as parent.  It is also used to
	expand macros.

	The data that is built can be manipulated as targetData.  You probably
	only want to change meta information here (e.g., warnings or infos).
	"""
	name_ = "apply"
	requiredType = "apply"
	formalArgs = "vars, result, targetTable"


class RowmakerMacroMixin(macros.StandardMacroMixin):
	"""is a collection of macros available to rowmakers.

	NOTE: All macros should return only one single physical python line,
	or they will mess up the calculation of what constructs caused errors.
	"""
	def macro_inputRelativePath(self):
		"""returns an expression giving the current source's path 
		relative to inputsDir
		"""
		return ('utils.getRelativePath(parser_.sourceToken,'
			' base.getConfig("inputsDir"))')
	
	def macro_rowsProcessed(self):
		"""returns an expression giving the number of records already 
		ingested for this source.
		"""
		return 'raise NotImplementedError("Cannot compute #rows yet")'

	def macro_property(self, property):
		"""returns an expression giving the property on the current DD.
		"""
		return 'curDD_.getProperty("%s")'%property

	def macro_sourceDate(self):
		"""returns an expression giving the timestamp of the current source.
		"""
		return 'datetime.fromtimestamp(os.path.getmtime(parser_.sourceToken))'
		
	def macro_srcstem(self):
		"""returns the stem of the source file currently parsed.
		
		Example: if you're currently parsing /tmp/foo.bar, the stem is foo.
		"""
		return 'os.path.splitext(os.path.basename(parser_.sourceToken))[0]'

	def macro_lastSourceElements(self, numElements):
		"""returns an expression calling rmkfuncs.lastSourceElements on
		the current input path.
		"""
		return 'lastSourceElements(parser_.sourceToken, int(numElements))'

	def macro_rootlessPath(self):
		"""returns an expression giving the current source's path with 
		the resource descriptor's root removed.
		"""
		return 'utils.getRelativePath(rd_.resdir, parser_.sourceToken)'

	def macro_inputSize(self):
		"""returns an expression giving the size of the current source.
		"""
		return 'os.path.getsize(parser_.sourceToken)'

	def macro_docField(self, name):
		"""returns an expression giving the value of the column name in the 
		document parameters.
		"""
		return '_parser.getParameters()[fieldName]'

	def macro_qName(self):
		"""returns the qName of the table we are currently parsing into.
		"""
		return "tableDef.getQName()"


class RowmakerDef(base.Structure, RowmakerMacroMixin):
	"""A definition of the mapping between grammar input and finished rows
	ready for shipout.

	Rowmakers consist of variables, procedures and mappings.  They
	result in a python callable doing the mapping.

	RowmakerDefs double as macro packages for the expansion of various
	macros.  The standard macros will need to be quoted, the rowmaker macros
	above yield python expressions.
	"""
	name_ = "rowmaker"

	_maps = base.StructListAttribute("maps", childFactory=MapRule,
		description="Mapping rules.", copyable=True)
	_vars = base.StructListAttribute("vars", childFactory=VarDef,
		description="Definitions of intermediate variables.",
		copyable=True)
	_procs = base.StructListAttribute("procs",
		childFactory=ProcDef, description="Procedures manipulating rows.",
		copyable=True) # XXX TODO: Remove
	_apps = base.StructListAttribute("apps",
		childFactory=ApplyDef, description="Procedure applications.",
		copyable=True)
	_defaults = base.DictAttribute("defaults", 
		itemAttD=base.UnicodeAttribute("default"),
		description="Default values on input items.", copyable=True)
	_rd = common.RDAttribute()
	_idmaps = base.StringListAttribute("idmaps", description="List of"
		' column names that are just "mapped through" (like map with dest'
		" only); you can use shell patterns to select multiple colums at once.",
		copyable=True)
	_simplemaps = base.IdMapAttribute("simplemaps", description=
		"Abbreviated notation for <map src>", copyable=True)
	_rowSource = base.EnumeratedUnicodeAttribute("rowSource", 
		default="rows", validValues=["rows", "parameters"],
		description="Source for the raw rows processed by this rowmaker.",
		copyable=True)
	_original = base.OriginalAttribute()

	@classmethod
	def makeIdentityFromTable(cls, table, **kwargs):
		"""returns a rowmaker that just maps input names to column names.

		All non-required fields receive None defaults.
		"""
		idmaps=",".join(c.name for c in table)
		defaults = dict((c.name, None) for c in table if not c.required)
		return base.makeStruct(cls, 
			idmaps=[c.name for c in table], defaults=defaults, **kwargs)

	@classmethod
	def makeTransparentFromTable(cls, table, **kwargs):
		"""returns a rowmaker that maps input names to column names without
		touching them.

		This is intended for grammars delivering "parsed" values, like, e.g.
		contextgrammar.
		"""
		defaults = dict((c.name, None) for c in table if not c.required)
		return base.makeStruct(cls, defaults=defaults, maps=[
				base.makeStruct(MapRule, dest=c.name, content_=c.name)
					for c in table],
			**kwargs)

	def completeElement(self):
		if self.simplemaps:
			for k,v in self.simplemaps.iteritems():
				self.feedObject("maps", base.makeStruct(MapRule, 
					dest=k, src=v))
		self._completeElementNext(RowmakerDef)

	def _getSource(self, tableDef):
		"""returns the source code for a mapper to a tableDef-defined table.
		"""
		lineMap = {}
		source = ['_result = {}']
		line = 1

		def appendToSource(srcLine, line, lineMarker):
			source.append(srcLine)
			line += 1
			lineMap[line] = lineMarker
			line += source[-1].count("\n")
			return line

		for v in self.vars:
			line = appendToSource(v.getCode(), line, "assigning "+v.name)
		for p in self.procs:  # XXX DEPRECATED
			line = appendToSource(p.getCall(), line, "executing "+p.name)
		for a in self.apps:
			line = appendToSource("%s(rowdict_, _result, targetTable_)"%a.name,
				line, "executing "+a.name)
		for m in self.maps:
			line = appendToSource(m.getCode(tableDef), line, "building "+m.dest)
		return "\n".join(source), lineMap

	def _getGlobals(self, tableDef):
		globals = {}
		for p in self.procs:
			name, func = p.getDefinition()
			globals[name] = func
		for a in self.apps:
			globals[a.name] = a.compile()
		globals["tableDef_"] = tableDef
		globals["rd_"] = self.rd
		return globals

	def _getDefaults(self):
		"""returns a mapping containing the user defaults plus base.Undefined
		for all defaulted arguments in proc defs.
		"""
		defaults = dict([(n, base.Undefined) 
			for p in self.procs
			for n in p.defaultedNames])
		defaults.update(self.defaults)
		return defaults
	
	def _resolveIdmaps(self, tableDef):
		"""adds mappings for self's idmap within tableDef.
		"""
		if self.idmaps is None:
			return
		existingMaps = set(m.dest for m in self.maps)
		baseNames = [c.name for c in tableDef]
		for colName in self.idmaps:
			matching = fnmatch.filter(baseNames, colName)
			if not matching:
				raise base.LiteralParseError("%s does not match any column"
					" names from the %s"%(colName, tableDef.id), "idmaps", 
					",".join(self.idmaps))
			for dest in matching:
				if dest not in existingMaps:
					self.maps.append(MapRule(self, dest=dest).finishElement())
		self.idmaps = []

	def _checkTable(self, tableDef):
		"""raises a LiteralParseError if we try to map to non-existing
		columns.
		"""
		for map in self.maps:
			try:
				tableDef.getColumnByName(map.dest)
			except KeyError:
				raise base.LiteralParseError("Cannot map to '%s' since it does"
					" not exist in %s"%(self.dest, tableDef.id), self.name_, self.dest)

	def _buildForTable(self, tableDef):
		"""returns a RowmakerDef with everything expanded and checked for
		tableDef.

		This may raise LiteralParseErrors if self's output is incompatible
		with tableDef.
		"""
		res = self.copyShallowly()
		res._resolveIdmaps(tableDef)
		res._checkTable(tableDef)
		return res

	def compileForTable(self, table):
		"""returns a function receiving a dictionary of raw values and
		returning a row ready for adding to a tableDef'd table.

		To do this, we first make a rowmaker instance with idmaps resolved
		and then check if the rowmaker result and the table structure
		are compatible.
		"""
		tableDef = table.tableDef
		rmk = self._buildForTable(tableDef)
		source, lineMap = rmk._getSource(tableDef)
		globals = rmk._getGlobals(tableDef)
		globals["targetTable_"] = table
		return Rowmaker(source, self.id, globals, rmk._getDefaults(), lineMap)

	def copyShallowly(self):
		return base.makeStruct(self.__class__, maps=self.maps[:], 
			vars=self.vars[:], procs=self.procs[:], defaults=self.defaults.copy(), 
			idmaps=self.idmaps, rowSource=self.rowSource, apps=self.apps[:])


identityRowmaker = base.makeStruct(RowmakerDef, idmaps="*")


class Rowmaker(object):
	"""is a callable that arrange for mapping of parse values.

	It is constructed with the mapping function, a dictionary of
	globals the function should see, a dictionary of defaults,
	giving keys to be inserted into the incoming rowdict before
	the mapping function is called, and a map of line numbers to
	names handled in that line.

	It is called with a dictionary of locals for the functions (i.e.,
	usually the result of a grammar iterRows).
	"""
	def __init__(self, source, name, globals, defaults, lineMap):
		try:
			self.code = compile(source, "generated mapper code", "exec")
		except SyntaxError, msg:
			raise base.LiteralParseError("Bad code in rowmaker (%s)"%unicode(msg),
				"rowmaker", source)
		self.source, self.name = source, name
		globals.update(rmkfuncs.__dict__)
		self.globals, self.defaults = globals, defaults
		self.keySet = set(self.defaults)
		self.lineMap = sorted(lineMap.items())

	def _guessExSourceName(self, tb):
		"""returns an educated guess as to which mapping should have
		caused that traceback in tb.

		This is done by inspecting the second-topmost stackframe.  It
		must hold the generated line that, possibly indirectly, caused
		the exception.  This line should be in the lineMap generated by
		RowmakerDef._getSource.
		"""
		if tb.tb_next:
			excLine = tb.tb_next.tb_lineno
		else: # toplevel failure, internal
			return "in toplevel (internal failure)"
		destInd = min(len(self.lineMap)-1, 
			bisect.bisect_left(self.lineMap, (excLine, "")))
		# If we're between lineMap entries, the one before the guessed one
		# is the one we want
		if self.lineMap[destInd][0]>excLine and destInd:
			destInd -= 1
		return self.lineMap[destInd][1]

	def _guessError(self, ex, rowdict, tb):
		"""tries to shoehorn a ValidationError our of ex.
		"""
		#traceback.print_tb(tb)
		destName = self._guessExSourceName(tb)
		try:
			if "_result" in rowdict: del rowdict["_result"]
			if "parser_" in rowdict: del rowdict["parser_"]
			if "rowdict_" in rowdict: del rowdict["rowdict_"]
		except TypeError:
			import sys
			sys.stderr.write("Internal failure in parse code:\n")
			traceback.print_tb(tb)
			rowdict = {"error": "Rowdict was no dictionary"}
		if isinstance(ex, KeyError):
			msg = ("Key %s not found in a mapping; probably the grammar"
				" did not yield the required field"%unicode(ex))
		else:
			msg = unicode(ex)
		raise base.ValidationError("While %s in %s: %s"%(destName, 
			self.name, msg), destName.split()[-1], rowdict)

	def __call__(self, vars):
		try:
			missingKeys = self.keySet-set(vars)
			for k in missingKeys:
				vars[k] = self.defaults[k]
			vars["rowdict_"] = vars
			exec self.code in self.globals, vars
			del vars["rowdict_"]
			return vars["_result"]
		except base.ValidationError:  # hopefully downstream knows better than we
			raise
		except Exception, ex:
			self._guessError(ex, vars, sys.exc_info()[2])
