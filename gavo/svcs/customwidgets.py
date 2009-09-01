"""
Special gavo widgets and their corresponding types based on nevow formal.
"""

import urllib

from nevow import tags as T, entities as E
from nevow import inevow
from nevow.util import getPOSTCharset

from zope.interface import implements

from gavo import base
from gavo import rscdef
from gavo.base import typesystems
from gavo.imp import formal
from gavo.imp.formal import iformal
from gavo.imp.formal import types as formaltypes
from gavo.imp.formal import validation
from gavo.imp.formal import widget
from gavo.imp.formal.util import render_cssid
from gavo.imp.formal.widget import *
from gavo.imp.formal import widgetFactory


class OutputFormat(object):
	"""is a widget that offers various output options in close cooperation
	with gavo.js and QueryMeta.

	The javascript provides options for customizing output that non-javascript
	users will not see.  Also, formal doesn't see any of these.  See gavo.js
	for details.

	This widget probably only makes sense in the Form renderer and thus
	should probably go there.
	"""
	def __init__(self, typeOb, service, queryMeta):
		self.service = service
		self.typeOb = typeOb
		self._computeAvailableFields(queryMeta)
		self._computeAvailableFormats(queryMeta)

	def _computeAvailableFormats(self, queryMeta):
		"""sets the availableFormats property.

		It contains a list of strings of possible output formats.  Since
		OutputFormat is rendered by resourcebased.Form, this is pretty
		much constant; we add tar if the service delivers products.
		"""
		self.availableFormats = ["VOTable", "VOPlot", "FITS", "TSV"]
		if self.service.outputTable.getProductColumns():
			self.availableFormats.append("tar")
		
	def _computeAvailableFields(self, queryMeta):
		"""computes the fields a Core provides but are not output by
		the service by default.

		This of course only works if the core defines its output table.
		Otherwise, availableFields is an empty list.
		"""
		self.availableFields = []
		core = self.service.core
		if not core.outputTable or self.service.getProperty("noAdditionals", False):
			return
		coreNames = set(f.name for f in core.outputTable)
		defaultNames = set([f.name
			for f in self.service.getHTMLOutputFields(queryMeta, 
				ignoreAdditionals=True)])
		selectedFields = set(queryMeta["additionalFields"])
		for key in coreNames-defaultNames:
			try:
				self.availableFields.append((core.outputTable.getColumnByName(key),
					key in queryMeta["additionalFields"]))
			except KeyError: # Core returns fields not in its table, 
		                   # probably computes them
				pass

	def _makeFieldDescs(self):
		descs = [(f.name, str(selected), urllib.quote(
				f.tablehead)) for f, selected in self.availableFields]
		descs.sort(key=lambda a:a[2].upper())
		return "\n".join("%s %s %s"%d for d in descs)

	_labelOverrides = {
		"TSV": "Tab-separated ASCII",
	}

	def render(self, ctx, key, args, errors):
		return T.div(id=render_cssid("_OUTPUT"))[
			SelectChoice(formaltypes.String(), 
				options=[(s, self._labelOverrides.get(s,s)) 
					for s in self.availableFormats],
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
					T.img(src=base.makeSitePath("/builtin/img/bookmark.png"), 
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


class DBOptions(object):
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
		if getattr(self.service.core, "sortKey", None) is None:
			self.sortWidget = self._makeSortWidget(service, queryMeta)
		if getattr(self.service.core, "limit", None) is None:
			self.limitWidget = self._makeLimitWidget(service)
		
	def _makeSortWidget(self, service, queryMeta):
		keys = [f.name for f in self.service.getCurOutputFields(queryMeta,
			raiseOnUnknown=False)]
		if not keys:
			return None
		defaultKey = service.getProperty("defaultSort", None)
		if defaultKey:
			return SelectChoice(formaltypes.String(), options=
				[(key, key) for key in keys if key!=defaultKey], 
				noneOption=(defaultKey, defaultKey))
		else:
			return SelectChoice(formaltypes.String(), options=
				[(key, key) for key in keys])
	
	def _makeLimitWidget(self, service):
		keys = [(str(i), i) for i in [1000, 5000, 10000, 100000, 250000]]
		return SelectChoice(formaltypes.Integer(), options=keys,
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


# MultiSelectChoice is like formal's choice except you can specify a size.

class MultiSelectChoice(widget.SelectChoice):
	size = 3
	def __init__(self, original,  size=None, **kwargs):
		if size is not None:
			self.size=size
		widget.SelectChoice.__init__(self, original, **kwargs)

	def _renderTag(self, ctx, key, value, converter, disabled):
		if not isinstance(value, (list, tuple)):
			value = [value]
		# unfortunately, I need to copy all that code from formal to let 
		# me keep multiple selections
		def renderOptions(ctx, data):
			if self.noneOption is not None:
				yield T.option(value=iformal.IKey(self.noneOption).key())[
					iformal.ILabel(self.noneOption).label()]
			if data is None:
				return
			for item in data:
				optValue = iformal.IKey(item).key()
				optLabel = iformal.ILabel(item).label()
				optValue = converter.fromType(optValue)
				option = T.option(value=optValue)[optLabel]
				if optValue in value:
					option = option(selected='selected')
				yield option
		tag = T.select(name=key, id=render_cssid(key), data=self.options)[
			renderOptions]
		if disabled:
			tag(class_='disabled', disabled='disabled')
		return T.span(style="white-space:nowrap")[
			tag(size=str(self.size), multiple="multiple"),
			" ",
			T.span(class_="fieldlegend")[
				"No selection matches all, multiple values legal."]]

	def render(self, ctx, key, args, errors):
		converter = iformal.IStringConvertible(self.original)
		if errors:
			value = args.get(key, [])
		else:
			value = map(converter.fromType, args.get(key, []))
		return self._renderTag(ctx, key, value, converter, False)

	def processInput(self, ctx, key, args):
		values = args.get(key, [''])
		rv = []
		for value in values:
			value = iformal.IStringConvertible(self.original).toType(value)
			if self.noneOption is not None and value==iformal.IKey(self.noneOption):
				value = None
			rv.append(self.original.validate(value))
		return rv
	

def _getDisplayOptions(ik):
	"""helps EnumeratedWidget figure out the None option and the options
	for selection.
	"""
	noneOption = None
	options = []
	if ik.values.default is not None and ik.required:
		# default given but field required:  There's no noneOption but a
		# selected default
		options = ik.values.options
	elif ik.values.default:
		# default given and becomes the noneOption
		for o in ik.values.options:
			if o.content_==ik.values.default:
				noneOption = o
			else:
				options.append(o)
	else:  # no default given, make up ANY option as noneOption unless
	       # ik is required; if it's there make it displayed as well.
		options.extend(ik.values.options)
		noneOption = None
		if not ik.required and not ik.values.multiOk:
			noneOption = base.makeStruct(rscdef.Option, title="ANY", content_=None)
	return noneOption, options


def EnumeratedWidget(ik):
	"""is a widget factory for input keys over enumerated columns.

	This probably contains a bit too much magic, but let's see.  The current
	rules are:

	If values.multiOk is true, render a MultiSelectChoice, else
	render a SelectChoice or a RadioChoice depending on how many
	items there are.
	
	If ik is not required, add an ANY key evaluating to None.  For
	MultiSelectChoices we don't need this since for them, you can
	simply leave it all unselected.

	If there is a default, it becomes the NoneOption.
	"""
	if not ik.isEnumerated():
		raise base.StructureError("%s is not enumerated"%ik.name)
	noneOption, options = _getDisplayOptions(ik)
	moreArgs = {"noneOption": noneOption}
	if ik.values.multiOk:
		if ik.showItems==-1 or len(options)<4:
			baseWidget = CheckboxMultiChoice
			del moreArgs["noneOption"]
		else:
			baseWidget = MultiSelectChoice
			moreArgs["size"] = ik.showItems
	else:
		if len(options)<4:
			baseWidget = RadioChoice
		else:
			baseWidget = SelectChoice
	return formal.widgetFactory(baseWidget, options=options,
		**moreArgs)


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
	additionalMaterial = T.a(href=base.makeSitePath(
			"/builtin/help_vizier.shtml#floats"))[
		"[?num. expr.]"]

class DateExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=base.makeSitePath(
			"/builtin/help_vizier.shtml#dates"))[
		"[?date expr.]"]

class StringExpressionField(StringFieldWithBlurb):
	additionalMaterial = T.a(href=base.makeSitePath(
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
