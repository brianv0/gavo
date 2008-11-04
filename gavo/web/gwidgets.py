"""
Special gavo widgets and their corresponding types based on nevow formal.
"""

import urllib

from nevow import tags as T, entities as E
from nevow import inevow
import formal
from formal import iformal
from formal import types as formaltypes
from formal import validation
from formal import widget
from formal.util import render_cssid
from formal.widget import *
from formal import widgetFactory
from zope.interface import implements

import gavo
from gavo import datadef
from gavo import macros
from gavo import record
from gavo import typesystems
from gavo import unitconv
from gavo.web import common
from gavo.web import vizierexprs



def getOptionRenderer(initValue):
	"""returns a generator for option fields within a select field.
	"""
	def renderOptions(self, selItems):
		for value, label in selItems:
			option = T.option(value=value)[label]
			if value==initValue:
				yield option(selected="selected")
			else:
				yield option
	return renderOptions


class OutputFormat(object):
	"""is a widget that offers various output options in close cooperation
	with gavo.js and QueryMeta.

	The javascript provides options for customizing output that non-javascript
	users will not see.  Also, formal doesn't see any of these.  See gavo.js
	for details.
	"""
	def __init__(self, typeOb, service, queryMeta):
		self.service = service
		self.typeOb = typeOb
		self._computeAvailableFields(queryMeta)
		self._computeAvailableFormats(queryMeta)

	def _computeAvailableFormats(self, queryMeta):
		self.availableFormats = ["VOTable", "VOPlot", "FITS", "TSV"]
		core = self.service.get_core()
		if not hasattr(core, "tableDef"):
			return
# XXX TODO: Once we have a real interface.isImplementedIn, do away with
# this gruesome hack -- it's really supposed to check for products in the
# output table
		if "accref" in core.tableDef.get_items():
			self.availableFormats.append("tar")
		
	def _computeAvailableFields(self, queryMeta):
		"""computes the fields a DbBasedCore provides but doesn't 
		output by default.
		"""
# XXX TODO: We should provide some control over what fields are offered here
		self.availableFields = []
		core = self.service.get_core()
		if not hasattr(core, "tableDef"):
			return
		defaultNames = set([f.get_dest() 
			for f in self.service.getHTMLOutputFields(queryMeta, 
				ignoreAdditionals=True)])
		for key in core.avOutputKeys-defaultNames:
			try:
				self.availableFields.append(core.tableDef.getFieldByName(key))
			except KeyError: # Core returns fields not in its table, probably computes them
				pass

	def _makeFieldDescs(self):
		descs = [(f.get_dest(), urllib.quote(
				f.get_tablehead() or f.get_description() or f.get_dest()))
			for f in self.availableFields]
		descs.sort(key=lambda a:a[1].upper())
		return "\n".join("%s %s"%d for d in descs)

	def render(self, ctx, key, args, errors):
		return T.div(id=render_cssid("_OUTPUT"))[
			widget.SelectChoice(formaltypes.String(), 
				options=[(s, s) for s in self.availableFormats],
				noneOption=("HTML", "HTML")).render(ctx, "_FORMAT", args, errors)(
					onchange="output_broadcast(this.value)"),
			T.span(id=render_cssid(key, "QlinkContainer"), 
					style="padding-left:200px")[
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"],
				" ",
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeBookmarkLink(getEnclosingForm(this))")[
					T.img(src=macros.makeSitePath("/builtin/img/bookmark.png"), 
						class_="silentlink", title="Link to this form", alt="[bookmark]")
				],
			],
			T.br,
			T.div(id="op_selectItems", style="visibility:hidden;position:absolute;"
					"bottom:-10px", title="ignore")[
						self._makeFieldDescs()]]
	
	renderImmutable = render  # This is a lost case

	def processInput(self, ctx, key, args):
		return args.get("_FORMAT", ["HTML"])[0]


class DbOptions(object):
	"""is a widget that offers limit and sort options for db based cores.

	This is for use in a formal form and goes together with the FormalDict
	type below.
	"""
	implements(iformal.IWidget)

	sortWidget = None
	limitWidget = None

	def __init__(self, typeOb, service, queryMeta):
		self.service = service
		self.typeOb = typeOb
		if self.service.get_core().get_sortOrder() is common.Undefined:
			self.sortWidget = self._makeSortWidget(service, queryMeta)
		if self.service.get_core().get_limit() is common.Undefined:
			self.limitWidget = self._makeLimitWidget(service)
		
	def _makeSortWidget(self, service, queryMeta):
		keys = [f.get_dest() for f in self.service.getCurOutputFields(queryMeta)]
		defaultKey = service.get_property("defaultSort")
		if defaultKey:
			return widget.SelectChoice(formaltypes.String(), options=
				[(key, key) for key in keys if key!=defaultKey], 
				noneOption=(defaultKey, defaultKey))
		else:
			return widget.SelectChoice(formaltypes.String(), options=
				[(key, key) for key in keys])
	
	def _makeLimitWidget(self, service):
		keys = [(str(i), i) for i in [1000, 5000, 10000, 100000, 250000]]
		return widget.SelectChoice(formaltypes.Integer(), options=keys,
			noneOption=("100", 100))

	def render(self, ctx, key, args, errors):
# XXX TODO: Clean up this mess -- you probably don't want the widget in
# this way anyway.
		children = []
		if '_DBOPTIONS' in args:
			v = [[args["_DBOPTIONS"]["order"]] or "", 
				[args["_DBOPTIONS"]["limit"] or 100]]
		else:
			v = [args.get("_DBOPTIONS_ORDER", ['']), 
				args.get("_DBOPTIONS_LIMIT", [100])]
		if errors:
			args = {"_DBOPTIONS_ORDER": v[0], "_DBOPTIONS_LIMIT": v[1]}
		else:
			args = {"_DBOPTIONS_ORDER": v[0][0], "_DBOPTIONS_LIMIT": int(v[1][0])}
		if self.sortWidget:
			children.extend(["Sort by ",
				self.sortWidget.render(ctx, "_DBOPTIONS_ORDER", args, errors),
				"   "])
		if self.limitWidget:
			children.extend(["Limit to ",
				self.limitWidget.render(ctx, "_DBOPTIONS_LIMIT", args, errors),
				" items."])
		return T.span(id=render_cssid(key))[children]

	# XXX TODO: make this immutable.
	renderImmutable = render

	def processInput(self, ctx, key, args):
		order, limit = None, None
		if self.sortWidget:
			order = self.sortWidget.processInput(ctx, "_DBOPTIONS_ORDER", args)
		if self.limitWidget:
			limit = self.limitWidget.processInput(ctx, "_DBOPTIONS_LIMIT", args)
		return {
			"order": order,
			"limit": limit,
		}


class FormalDict(formaltypes.Type):
	"""is a formal type for dictionaries.
	"""
	pass


class SimpleSelectChoice(SelectChoice):
	def __init__(self, original, options, noneLabel=None):
		if noneLabel is None:
			noneOption = None
		else:
			noneOption = (noneLabel, noneLabel)
		super(SimpleSelectChoice, self).__init__(original,
			[(o,o) for o in options], noneOption)


# The multichoice code mostly stolen from formal -- their widget had no
# way of controlling the size

_UNSET = object()

class MultichoiceBase(object):
	"""
	A base class for widgets that provide the UI to select one or more items
	from a list.

	Based on ChoiceBase

	options:
		A sequence of objects adaptable to IKey and ILabel. IKey is used as the
		<option>'s value attribute; ILabel is used as the <option>'s child.
		IKey and ILabel adapters for tuple are provided.
	noneOption:
		An object adaptable to IKey and ILabel that is used to identify when
		nothing has been selected. Defaults to ('', '')
	"""

	options = None
	noneOption = None

	def __init__(self, original, options=None, noneOption=_UNSET, size=3):
		self.original = original
		if options is not None:
			self.options = options
		if noneOption is not _UNSET:
			self.noneOption = noneOption
		self.size = size

	def processInput(self, ctx, key, args):
		values = args.get(key, [''])
		rv = []
		for value in values:
			value = iformal.IStringConvertible(self.original).toType(value)
			if self.noneOption is not None and value == self.noneOption[0]:
				value = None
			rv.append(self.original.validate(value))
		return rv


class MultiselectChoice(MultichoiceBase):
	"""
	A drop-down list of options.

	<select>
	  <option value="...">...</option>
	</select>

	"""
	implements( iformal.IWidget )

	noneOption = ('', '')

	def _renderTag(self, ctx, key, value, converter, disabled):
		def renderOptions(ctx, data):
			if self.noneOption is not None and not self.original.required:
				yield T.option(value=iformal.IKey(self.noneOption).key())[
					iformal.ILabel(self.noneOption).label()]
			if data is None:
				return
			for item in data:
				optValue = iformal.IKey(item).key()
				optLabel = iformal.ILabel(item).label()
				optValue = converter.fromType(optValue)
				option = T.option(value=optValue)[optLabel]

				if value and optValue in value:
					option = option(selected='selected')

				yield option

		tag=T.select(name=key, id=render_cssid(key), data=self.options, 
			multiple="multiple", size=str(self.size))[renderOptions]

		if disabled:
			tag(class_='disabled', disabled='disabled')
		return tag

	def render(self, ctx, key, args, errors):
		converter = iformal.IStringConvertible(self.original)
		if errors:
			value = args.get(key, [''])
		else:
			value = converter.fromType(args.get(key))
		return self._renderTag(ctx, key, value, converter, False)

	def renderImmutable(self, ctx, key, args, errors):
		converter = iformal.IStringConvertible(self.original)
		value = converter.fromType(args.get(key))
		return self._renderTag(ctx, key, value, converter, True)


class SimpleMultiSelectChoice(MultiselectChoice):
	noneOption = ("ANY", "ANY")
	def __init__(self, original, options, showitems):
		super(MultiselectChoice, self).__init__(original,
			[(o,o) for o in options], size=showitems)


class StringFieldWithBlurb(widget.TextInput):
	"""is a text input widget with additional material at the side.
	"""
	additionalMaterial = ""

	def _renderTag(self, ctx, key, value, readonly):
		plainTag = widget.TextInput._renderTag(self, ctx, key, value,
			readonly)
		return T.span(style="white-space:nowrap")[
			plainTag, 
			T.img(onclick="document.getElementById('genForm-%s').value=''"%key,
				src="/builtin/img/clearButton.png", alt="[clear]", 
				title="Clear field", style="vertical-align:bottom"),
			" ",
			T.span(class_="fieldlegend")[self.additionalMaterial]]


class NumericExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=macros.makeSitePath(
			"/builtin/help_vizier.shtml#floats"))[
		"[?num. expr.]"]

class DateExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=macros.makeSitePath(
			"/builtin/help_vizier.shtml#dates"))[
		"[?date expr.]"]

class StringExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=macros.makeSitePath(
			"/builtin/help_vizier.shtml#string"))[
		"[?char expr.]"]


class ScalingTextArea(widget.TextArea):
	"""is a text area that scales with the width of the window.
	"""
	def _renderTag(self, ctx, key, value, readonly):
		tag=T.textarea(name=key, id=render_cssid(key), rows=self.rows,
			style="width:100% !important")[value or '']
		if readonly:
			tag(class_='readonly', readonly='readonly')
		return tag


def makeWidgetFactory(code):
	return eval(code)


class InputKey(datadef.DataField):
	"""is a key for a ContextGrammar.
	"""
	additionalFields = {
		"formalType":    None, # nevow formal type to use.
		"widgetFactory": None, # Python code to generate a formal widget factory
		                       # for this field.
		"showitems": 3,        # #items to show in multi selections
		"value": None,         # value in a constant field (rendered hidden)
		"scaling": None,       # multiply incoming value by this (will be clobbered
		                       # if you set inputUnit)
		"inputUnit": None,     # unit the user is supposed to use
	}
	
	def set_formalType(self, formalType):
		"""sets the nevow formal type for the input field.

		The argument can either be a string, in which case it is interpreted
		as an *SQL* type and translated to the corresponding formal type,
		or a formal type.
		"""
		if isinstance(formalType, basestring):
			defaultType, defaultWidget = sqltypeToFormal(
				formalType)
			if not self.dataStore["formalType"]:
				self.dataStore["formalType"] = defaultType
			if not self.dataStore["widgetFactory"]:
				self.set_widgetFactory(defaultWidget)
		else:
			self.dataStore["formalType"] = formalType

	def get_formalType(self):
		if self.dataStore.get("formalType"):
			return self.dataStore["formalType"](
				required=not self.get_optional())
		if self.isEnumerated():
			formalType = sqltypeToFormal(self.get_dbtype())[0]
		else:
			formalType = formal.String
		return formalType(required=not self.get_optional())

	def set_scaling(self, val):
		if val is None:
			self.dataStore["scaling"] = None
		else:
			self.dataStore["scaling"] = float(val)

	def set_inputUnit(self, val):
		if val is None:
			self.dataStore["inputUnit"] = None
			self.set_scaling(None)
		else:
			self.dataStore["inputUnit"] = val
			self.set_scaling(unitconv.getFactor(val, self.get_unit()))

	def set_widgetFactory(self, widgetFactory):
		"""sets the widget factory either from source code or from a formal
		WidgetFactory object.
		"""
		if isinstance(widgetFactory, basestring):
			self.dataStore["widgetFactory"] = makeWidgetFactory(
				widgetFactory)
		else:
			self.dataStore["widgetFactory"] = widgetFactory

	def get_widgetFactory(self):
		"""returns a widget factory appropriate for dbtype and values.
		"""
# XXX TODO: handle booleans
		if self.dataStore.get("widgetFactory"):
			res = self.dataStore["widgetFactory"]
		elif self.get_value():
			return formal.Hidden
		elif self.isEnumerated():
			if self.get_values().get_multiOk():
				res = formal.widgetFactory(
					SimpleMultiSelectChoice,
					[str(i) for i in self.get_values().get_options()],
					self.get_showitems())
			else:
				items = self.get_values().get_options()
# XXX TODO sanitize the whole default/none option mess.
#				try:
#					items.remove(self.get_values().get_default())
#				except ValueError:
#					pass
				noneLabel = None
				if self.get_optional():
					noneLabel = "ANY"
				res = formal.widgetFactory(
					SimpleSelectChoice,
					[str(i) for i in items], self.get_default())
		else:
			_, res = sqltypeToFormal(self.get_dbtype())
		return res

	def getValueIn(self, *args, **kwargs):
		if self.get_value() is not None:
			return self.get_value()
		return super(InputKey, self).getValueIn(*args, **kwargs)

	@classmethod
	def fromDataField(cls, dataField, attrs={}):
		"""returns an InputKey for query input to dataField
		"""
		instance = super(InputKey, cls).fromDataField(dataField)
		instance.set_dbtype(vizierexprs.getVexprFor(instance.get_dbtype()))
		instance.set_source(instance.get_dest())
		instance.set_optional(True)
		for key, val in attrs.iteritems():
			instance.set(key, val)
		return instance

	@classmethod
	def makeAuto(cls, dataField, queryMeta={}):
		"""returns an InputKey if dataField is "queriable", None otherwise.
		"""
		if dataField.get_displayHint().get("type")=="suppress":
			return
		try:
			hasVexprType = vizierexprs.getVexprFor(dataField.get_dbtype())
		except gavo.Error:
			return
		return cls.fromDataField(dataField)


class ToFormalConverter(typesystems.FromSQLConverter):
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
		"vexpr-float": (formal.String, NumericExpressionField),
		"vexpr-date": (formal.String, DateExpressionField),
		"vexpr-string": (formal.String, StringExpressionField),
		"file": (formal.File, None),
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return formal.String

sqltypeToFormal = ToFormalConverter().convert


