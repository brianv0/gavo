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

from gavo import record
from gavo.web import common



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
		ofs = core.tableDef.get_items()
		for of in ofs:
			if of.get_dest()=="accref":
				self.availableFormats.append("tar")
				break
		
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
			for f in self.service.getCurOutputFields(queryMeta)])
		for key in core.avOutputKeys-defaultNames:
			self.availableFields.append(core.tableDef.getFieldByName(key))

	def _makeFieldDescs(self):
		return "\n".join(["%s %s"%(f.get_dest(), urllib.quote(
				f.get_tablehead() or f.get_description() or f.get_dest()))
			for f in self.availableFields])

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
					T.img(src=common.makeSitePath("/builtin/img/bookmark.png"), 
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
		return widget.SelectChoice(formaltypes.String(), options=
			[(key, key) for key in keys])
	
	def _makeLimitWidget(self, service):
		keys = [(str(i), i) for i in [1000, 5000, 10000, 100000, 250000]]
		return widget.SelectChoice(formaltypes.Integer(), options=keys,
			noneOption=("100", 100))

	def render(self, ctx, key, args, errors):
		children = []
		if '_DBOPTIONS' in args:
			v = [[args["_DBOPTIONS"]["order"]], [args["_DBOPTIONS"]["limit"]]]
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
		if noneLabel==None:
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
		plainTag = super(StringFieldWithBlurb, self)._renderTag(ctx, key, value,
			readonly)
		return T.span[plainTag, " ", 
			T.span(class_="fieldlegend")[self.additionalMaterial]]


class NumericExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=common.makeSitePath(
			"/builtin/help_vizier.shtml#floats"))[
		"[?num. expr.]"]

class DateExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=common.makeSitePath(
			"/builtin/help_vizier.shtml#dates"))[
		"[?date expr.]"]

class StringExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=common.makeSitePath(
			"/builtin/help_vizier.shtml#string"))[
		"[?char expr.]"]


def makeWidgetFactory(code):
	return eval(code)
