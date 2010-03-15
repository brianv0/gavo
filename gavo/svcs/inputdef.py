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
from gavo.base import vizierexprs
from gavo.imp import formal
from gavo.svcs import customwidgets

MS = base.makeStruct


class InputKey(rscdef.Column):
	"""A description of a piece of input.

	Think of inputKeys as abstractions for input fields in forms, though
	they are used for services not actually exposing HTML forms as well.

	Some of the DDL-type attributes (e.g., references) only make sense here
	if columns are being defined from the InputKey.
	"""
	name_ = "inputKey"

	_formalType = base.UnicodeAttribute("formalType", default=base.Undefined,
		description="Type for the input widget, defaults to being computed"
			" from the column's type.", copyable=True)
	_widgetFactory = base.UnicodeAttribute("widgetFactory", default=None,
		description="Python code for a custom widget factory for this input,"
		" e.g., 'Hidden' or 'widgetFactory(TextArea, rows=15, cols=30)'",
		copyable=True)
	_showItems = base.IntAttribute("showItems", default=3,
		description="Number of items to show at one time on selection widgets.",
		copyable=True)
	_value = base.UnicodeAttribute("value", default=None,
		description="A constant value for this field (will be rendered as hidden).",
		copyable=True)
	_inputUnit = base.UnicodeAttribute("inputUnit", default=None,
		description="Override unit of the table column with this.",
		copyable=True)

	def __repr__(self):
		return "<InputKey %s (%s)>"%(self.name, self.type)

	def completeElement(self):
		self._completeElementNext(InputKey)
# XXX TODO: Fix the mess with widgetFactory and formalType by defining
# special attribute types for them.  Leave the attribute defined
# as strings and add properties to InputKeys like compiledWidgetFactory
# or the like.
		# Adapt type if we were built from a column.
		if (hasattr(self, "_originalObject") 
				and isinstance(self._originalObject, rscdef.Column)
				and self.formalType is base.Undefined):
			self.toVizierType()

		if self.formalType is base.Undefined:
			self.formalType = sqltypeToFormal(self.type)[0](required=self.required)

		# If no widget factory has been specified, infer one
		if self.widgetFactory is None:
			if self.value is not None:
				self.useWidget = formal.Hidden
			elif self.isEnumerated():
				self.useWidget = customwidgets.EnumeratedWidget(self)
			else:
				self.useWidget = sqltypeToFormal(self.type)[1]
		else:
			self.useWidget = self.widgetFactory

	def onElementComplete(self):
		self._onElementCompleteNext(InputKey)

		# convert formalType to a real formal type if it's still a string.
		if isinstance(self.formalType, basestring):
			defaultType, defaultWidget = sqltypeToFormal(self.formalType)
			if self.useWidget is None:
				self.useWidget = defaultWidget
			self.formalType = defaultType(required=self.required)

		# compute scaling if an input unit is given
		self.scaling = None
		if self.inputUnit:
			self.scaling = base.computeConversionFactor(self.inputUnit, self.unit)

		# compile a widget factory if it's a string
		if isinstance(self.useWidget, basestring):
			self.useWidget = customwidgets.makeWidgetFactory(self.useWidget)
	
	def getFormalVar(self):
		return self.formalType(required=self.required)

	def toVizierType(self):
		"""turns a normal column type into a type for inputting vizier expressions.

		This is called by fromColumn and completeElement when the type comes
		from a raw column.
		"""
		if self.isEnumerated():
			return
		try:
			self.type = vizierexprs.getVexprFor(self.type)
		except base.ConversionError: # no vexpr type, leave raw type
			pass

	@classmethod
	def fromColumn(cls, column, **kwargs):
		"""returns an InputKey for query input to dataField
		"""
		instance = cls(None)
		instance.feed("original", column)
		for k,v in kwargs.iteritems():
			instance.feed(k, v)
		return instance.finishElement()

	@classmethod
	def makeAuto(cls, column, queryMeta={}):
		"""returns an InputKey if column is "queriable" (vizier-typable and not
		suppressed), None otherwise.
		"""
		if dataField.displayHint.get("type")=="suppress":
			return
		try:
			hasVexprType = vizierexprs.getVexprFor(column.type)
		except base.Error:
			return
		return cls.fromDataField(dataField)


class ContextRowIterator(grammars.RowIterator):
	"""is a row iterator over "contexts", i.e. single dictionary-like objects.

	Since it's useful in the service context, they return their dictionary
	as *both* parameters and a single row.
	"""
	def __init__(self, grammar, sourceToken, **kwargs):
		grammars.RowIterator.__init__(self, grammar, sourceToken, **kwargs)

	def _completeRow(self, rawRow):
		if self.grammar.defaults:
			val = self.grammar.defaults.copy()
		else:
			val = {}
		val.update(rawRow)
		return val

	def _iterRows(self):
		yield self._completeRow(self.sourceToken)
	
	def getParameters(self):
		return self._completeRow(self.sourceToken)
	
	def getLocator(self):
		return "Context input"


class ContextGrammar(grammars.Grammar):
	"""A grammar for web inputs.

	These are almost exclusively in InputDD.  They hold InputKeys defining
	what they take from the context.

	For DBCores, the InputDDs are generally defined implicitely via
	CondDescs.  Thus, only for other cores will you ever need to bother
	with ContextGrammars.

	The source tokens for context grammars are dictionaries, usually
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

rscdef.registerGrammar(ContextGrammar)


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


class ToFormalConverter(base.typesystems.FromSQLConverter):
	"""is a converter from SQL types to Formal type specifications.

	The result of the conversion is a tuple of formal type and widget factory.
	"""
	typeSystem = "Formal"
	simpleMap = {
		"smallint": (formal.Integer, formal.TextInput),
		"integer": (formal.Integer, formal.TextInput),
		"int": (formal.Integer, formal.TextInput),
		"bigint": (formal.Integer, formal.TextInput),
		"real": (formal.Float, formal.TextInput),
		"float": (formal.Float, formal.TextInput),
		"boolean": (formal.Boolean, formal.Checkbox),
		"double precision": (formal.Float, formal.TextInput),
		"double": (formal.Float, formal.TextInput),
		"text": (formal.String, formal.TextInput),
		"char": (formal.String, formal.TextInput),
		"date": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
			twoCharCutoffYear=50, dayFirst=True)),
		"time": (formal.Time, formal.TextInput),
		"timestamp": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
			twoCharCutoffYear=50, dayFirst=True)),
		"vexpr-float": (formal.String, customwidgets.NumericExpressionField),
		"vexpr-date": (formal.String, customwidgets.DateExpressionField),
		"vexpr-string": (formal.String, customwidgets.StringExpressionField),
		"file": (formal.File, None),
		"raw": (formal.String, formal.TextInput),
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return formal.String, formal.TextInput

sqltypeToFormal = ToFormalConverter().convert
