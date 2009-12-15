"""
Definition of rowmakers.

rowmakers are objects that take a dictionary of some kind and emit
a row suitable for inclusion into a table.
"""

import bisect
import fnmatch
import os
import re
import sys
import traceback

from gavo import base
from gavo import utils
from gavo.base import structure
from gavo.rscdef import common
from gavo.rscdef import macros
from gavo.rscdef import procdef
from gavo.rscdef import rmkfuncs
from gavo.rscdef import rowtriggers
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
		description="Exceptions that should be caught and"
		" cause the value to be NULL, separated by commas.")
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
		else:
			colDef = tableDef.getColumnByName(self.dest)
			if colDef.values and colDef.values.nullLiteral is not None:
				code.append("if %s=='%s':\n  _result['%s'] = None\nelse:"%(self.src,
					colDef.values.nullLiteral, self.dest))
			try:
				code.append('_result["%s"] = %s'%(self.dest, 
					base.sqltypeToPythonCode(colDef.type)%self.src))
			except base.ConversionError:
				raise base.LiteralParseError("map", colDef.type,
					hint="Auto-mapping to %s is impossible since"
					" no default map for %s is known"%(self.dest, colDef.type))
		code = "".join(code)
		if self.nullExcs is not base.NotGiven:
			code = 'try:\n%s\nexcept (%s): _result["%s"] = None'%(
				re.sub("(?m)^", "  ", code), self.nullExcs, self.dest)
		return code


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
			raise base.LiteralParseError("name", self.name,
				hint="Var names must be valid python"
				" identifiers, and '%s' is not"%self.name)

	def getCode(self):
		return "%s = %s"%(self.name, self.parent.expand(self.content_))


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
		return 'datetime.utcfromtimestamp(os.path.getmtime(parser_.sourceToken))'
		
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
	_apps = base.StructListAttribute("apps",
		childFactory=ApplyDef, description="Procedure applications.",
		copyable=True)
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
	_ignoreOn = base.StructAttribute("ignoreOn", default=None,
		childFactory=rowtriggers.IgnoreOn, description="Conditions on the"
		" input record (as delivered by the grammar) to cause the input"
		" record to be dropped by the rowmaker.", copyable=True)
	_original = base.OriginalAttribute()

	@classmethod
	def makeIdentityFromTable(cls, table, **kwargs):
		"""returns a rowmaker that just maps input names to column names.
		"""
		idmaps=",".join(c.name for c in table)
		return base.makeStruct(cls, idmaps=[c.name for c in table], **kwargs)

	@classmethod
	def makeTransparentFromTable(cls, table, **kwargs):
		"""returns a rowmaker that maps input names to column names without
		touching them.

		This is intended for grammars delivering "parsed" values, like, e.g.
		contextgrammar.
		"""
		return base.makeStruct(cls, maps=[
				base.makeStruct(MapRule, dest=c.name, content_=c.name)
					for c in table],
			**kwargs)

	def completeElement(self):
		if self.simplemaps:
			for k,v in self.simplemaps.iteritems():
				nullExcs = base.NotGiven
				if v.startswith("@"):
					v = v[1:]
					nullExcs = "NameError,"
				self.feedObject("maps", base.makeStruct(MapRule, 
					dest=k, src=v, nullExcs=nullExcs))
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

		if self.ignoreOn:
			line = appendToSource("if checkTrigger(rowdict_):\n"
				"  raise IgnoreThisRow(rowdict_)",
				line, "Checking ignore")
		for v in self.vars:
			line = appendToSource(v.getCode(), line, "assigning "+v.name)
		for a in self.apps:
			line = appendToSource("%s(rowdict_, _result, targetTable_)"%a.name,
				line, "executing "+a.name)
		for m in self.maps:
			line = appendToSource(m.getCode(tableDef), line, "building "+m.dest)
		return "\n".join(source), lineMap

	def _getGlobals(self, tableDef):
		globals = {}
		for a in self.apps:
			globals[a.name] = a.compile()
		if self.ignoreOn:
			globals["checkTrigger"] = self.ignoreOn
		globals["tableDef_"] = tableDef
		globals["rd_"] = self.rd
		return globals

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
				raise base.LiteralParseError("idmaps", ",".join(self.idmaps),
					hint="%s does not match any column names from table %s"%(
						colName, tableDef.id))
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
				raise base.LiteralParseError(self.name_, self.dest, 
					"Cannot map to '%s' since it does not exist in %s"%(
						map.dest, tableDef.id))

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
		return Rowmaker(source, self.id, globals, tableDef.getDefaults(), lineMap)

	def copyShallowly(self):
		return base.makeStruct(self.__class__, maps=self.maps[:], 
			vars=self.vars[:], idmaps=self.idmaps[:], rowSource=self.rowSource, 
			apps=self.apps[:], ignoreOn=self.ignoreOn)


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
			raise base.BadCode(source, "rowmaker", msg)
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
		"""tries to shoehorn a ValidationError out of ex.
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
			msg = unicode(str(ex), "iso-8859-1", "replace")
		raise base.ValidationError("While %s in %s: %s"%(destName, 
			self.name, msg), destName.split()[-1], rowdict)

	def __call__(self, vars):
		try:
			missingKeys = self.keySet-set(vars)
			for k in missingKeys:
				vars[k] = self.defaults[k]
			vars["rowdict_"] = vars
			exec self.code in self.globals, vars
			return vars["_result"]
		except rmkfuncs.IgnoreThisRow: # pass these on
			raise
		except base.ValidationError:  # hopefully downstream knows better than we
			raise
		except Exception, ex:
			self._guessError(ex, vars, sys.exc_info()[2])
