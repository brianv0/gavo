"""
Description and handling of inputs to services.

This module in particular describes the InputKey, the primary means
of describing input widgets and their processing.

They are collected in contextGrammars, entities creating input tables
and parameters.
"""


from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo.rscdef import column

MS = base.makeStruct


class InputKey(column.ParamBase):
	"""A description of a piece of input.

	Think of inputKeys as abstractions for input fields in forms, though
	they are used for services not actually exposing HTML forms as well.

	Some of the DDL-type attributes (e.g., references) only make sense here
	if columns are being defined from the InputKey.
	"""
	name_ = "inputKey"

	# XXX TODO: make widgetFactory and showItems properties.
	_widgetFactory = base.UnicodeAttribute("widgetFactory", default=None,
		description="Python code for a custom widget factory for this input,"
		" e.g., 'Hidden' or 'widgetFactory(TextArea, rows=15, cols=30)'",
		copyable=True)
	_showItems = base.IntAttribute("showItems", default=3,
		description="Number of items to show at one time on selection widgets.",
		copyable=True)
	_inputUnit = base.UnicodeAttribute("inputUnit", default=None,
		description="Override unit of the table column with this.",
		copyable=True)

	def completeElement(self):
		self._completeElementNext(InputKey)
		if self.restrictedMode and self.widgetFactory:
			raise base.RestrictedElement("widgetFactory")

	def onElementComplete(self):
		self._onElementCompleteNext(InputKey)
		# compute scaling if an input unit is given
		self.scaling = None
		if self.inputUnit:
			self.scaling = base.computeConversionFactor(self.inputUnit, self.unit)
	
	def onParentComplete(self):
		if self.parent and hasattr(self.parent, "required"):
			# children of condDescs inherit their requiredness
			# (unless defaulted)
			self.required = self.parent.required
		# but if there's a defalt, never require an input
		if self.value:
			self.required = False

	@classmethod
	def fromColumn(cls, column, **kwargs):
		"""returns an InputKey for query input to column.
		"""
		instance = cls(None)
		instance.feedObject("original", column)
		for k,v in kwargs.iteritems():
			instance.feed(k, v)
		return instance.finishElement()


class InputTable(rscdef.TableDef):
	name_ = "inputTable"
	_params = rscdef.ColumnListAttribute("params",
		childFactory=InputKey, description='Input parameters for'
		' this table.', copyable=True, aliases=["param"])

	def adaptForRenderer(self, renderer):
		"""returns an inputTable tailored for renderer.

		This is discussed in svcs.core's module docstring.
		"""
		newParams, changed = [], False
		rendName = renderer.name
		for param in self.params:
			if param.getProperty("onlyForRenderer", None) is not None:
				if param.getProperty("onlyForRenderer")!=rendName:
					changed = True
					continue
			if param.getProperty("notForRenderer", None) is not None:
				if param.getProperty("notForRenderer")==rendName:
					changed = True
					continue
			newParams.append(param)
		if changed:
			return self.change(params=newParams)
		else:
			return self


class ContextRowIterator(grammars.RowIterator):
	"""is a row iterator over "contexts", i.e. single dictionary-like objects.

	Since it's useful in the service context, they return their dictionary
	as *both* parameters and a single row.
	"""
	def __init__(self, grammar, sourceToken, **kwargs):
		grammars.RowIterator.__init__(self, grammar, sourceToken, **kwargs)

	def _completeRow(self, rawRow):
		if self.grammar.defaults:
			procRow = self.grammar.defaults.copy()
		else:
			procRow = {}
		# No update here: We don't want to clobber defaults with None
		for key, val in rawRow.iteritems():
			if val is not None or key not in procRow:
				procRow[key] = val
		return procRow

	def _iterRows(self):
		yield self._completeRow(self.sourceToken)
	
	def getParameters(self):
		return self._completeRow(self.sourceToken)
	
	def getLocator(self):
		return "Context input"


class ContextGrammar(grammars.Grammar):
	"""A grammar for web inputs.

	These are almost exclusively in InputDDs.  They hold InputKeys defining
	what they take from the context.

	For DBCores, the InputDDs are generally defined implicitely via
	CondDescs.  Thus, only for other cores will you ever need to bother
	with ContextGrammars.

	The source tokens for context grammars are typed dictionaries, usually
	computed by nevow formal.
	"""
	name_ = "contextGrammar"

	yieldsTyped = True

	_inputKeys = rscdef.ColumnListAttribute("inputKeys", 
		childFactory=InputKey, description="Definition of the service's input"
			" fields", copyable="True")
	_original = base.OriginalAttribute("original")

	rowIterator = ContextRowIterator

	def onElementComplete(self):
		self.defaults = {}
		for ik in self.inputKeys:
			if ik.values and ik.values.default is not None:
				self.defaults[ik.name] = ik.values.default
		self._onElementCompleteNext(ContextGrammar)

	@classmethod
	def fromInputKeys(cls, inputKeys):
		"""returns a ContextGrammar having the passed inputKeys.
		"""
		return cls(None, inputKeys=inputKeys).finishElement()
	
	@classmethod
	def fromColumns(cls, srcColumns):
		"""returns a ContextGrammar having input keys for all columns in srcColumns.
		"""
		return cls.fromInputKeys([InputKey.fromColumn(c) for c in srcColumns])


class InputDescriptor(rscdef.DataDescriptor):
	"""A data descriptor for defining a core's input.

	In contrast to normal data descriptors, InputDescriptors generate
	a contextGrammar to feed the table mentioned in the first make if
	no grammar is given.  Conversely, if a contextGrammar is given but
	no make, a make with a table defined by the contextGrammar's inputKeys
	is automatically generated.

	Attributes like auto, dependents, sources and the like probably
	make little sense for inputDescriptors.
	"""
	name_ = "inputDD"

	def completeElement(self):
		# If there is a make, i.e. table, infer the context grammar,
		# if there's a context grammar, infer the table.
		if self.makes and self.grammar is None:
			self.feedObject("grammar", ContextGrammar.fromColumns(
				self.makes[0].table))
		if not self.makes and isinstance(self.grammar, ContextGrammar):
			self.feedObject("make", MS(rscdef.Make, 
				table=MS(rscdef.TableDef, columns=self.grammar.inputKeys)))
		self._completeElementNext(InputDescriptor)


def makeAutoInputDD(core):
	"""returns a standard inputDD for a core.

	The standard inputDD is just a context grammar with the core's input
	keys, and the table structure defined by these input keys.
	"""
	return MS(InputDescriptor,
		grammar=MS(ContextGrammar, inputKeys=core.inputTable.params))
