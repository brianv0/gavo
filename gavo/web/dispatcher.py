import re
import traceback
import math
import cStringIO
import new

from twisted.internet import defer

from nevow import rend, loaders, wsgi, inevow, static, url, flat
from nevow import tags as T, entities as E
import formal
from formal import types as formaltypes
from formal import iformal
from formal import form
from formal import validation
from formal.util import render_cssid
from zope.interface import implements

from gavo import config
from gavo import resourcecache
from gavo import typesystems
from gavo.web.querulator import queryrun
from gavo import Error


class UnknownURI(Error):
	"""signifies that a http 404 should be returned to the dispatcher.
	"""


_linkGeneratingJs = """
function getEnclosingForm(element) {
// returns the form element immediately enclosing element.
	if (element.nodeName=="FORM") {
		return element;
	}
	return getEnclosingForm(element.parentNode);
}

function getSelectedEntries(selectElement) {
// returns an array of all selected entries from a select element 
// in url encoded form
	var result = new Array();
	var i;

	for (i=0; i<selectElement.length; i++) {
		if (selectElement.options[i].selected) {
			result.push(selectElement.name+"="+encodeURIComponent(
				selectElement.options[i].value))
		}
	}
	return result;
}

function makeQueryItem(element) {
// returns an url-encoded query tag item out of a form element
	var val=null;

	switch (element.nodeName) {
		case "INPUT":
			if (element.name && element.value) {
				val = element.name+"="+encodeURI(element.value);
			}
			break;
		case "SELECT":
			return getSelectedEntries(element).join("&");
			break;
		default:
			alert("No handler for "+element.nodeName);
	}
	if (val) {
		return val;
	} else {
		return element.NodeName;
	}
}

function makeResultLink(form) {
	// returns a link to the result sending the HTML form form would
	// yield.
	var fragments = new Array();
	var fragment;
	var i;

	items = form.elements;
	for (i=0; i<items.length; i++) {
		fragment = makeQueryItem(items[i]);
		if (fragment) {
			fragments.push(fragment);
		}
	}
	return form.getAttribute("action")+"?"+fragments.join("&");
}
"""


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


def parseServicePath(serviceParts):
	"""returns a tuple of resourceDescriptor, serviceName.

	A serivce id consists of an inputsDir-relative path to a resource 
	descriptor, a slash, and the name of a service within this descriptor.

	This function returns a tuple of inputsDir-relative path and service name.
	It raises a gavo.Error if sid has an invalid format.  The existence of
	the resource or the service are not checked.
	"""
	return "/".join(serviceParts[:-1]), serviceParts[-1]


class OutputOptions(object):
	"""a widget that offers various output formats for tables.

	This is for use in a formal form and goes together with the FormalDict
	type below.
	"""
# OMG, what a ghastly hack.  Clearly, I'm doing this wrong.  Well, it's the
# first thing I'm really trying with formal, so bear with me (and reimplement
# at some point...)
# Anyway: This is supposed to be a "singleton", i.e. the input key is ignored.
	implements( iformal.IWidget )

	def __init__(self, original):
		self.original = original

	def _renderTag(self, key, readonly, format, verbosity, tdEnc):
		if not format:
			format = "HTML"
		if not verbosity:
			verbosity = "2"
		if not tdEnc or tdEnc=="False":
			tdEnc = False
		formatEl = T.select(type="text", name='FORMAT',
			onChange='adjustOutputFields(this)',
			onMouseOver='adjustOutputFields(this)',
			id=render_cssid(key, "FORMAT"),
			data=[("HTML", "HTML"), ("VOTable", "VOTable"), 
				("VOPlot", "VOPlot")])[
			getOptionRenderer(format)]
		verbosityEl = T.select(type="text", name='VERB',
			id=render_cssid(key, "VERB"), style="width: auto",
			data=[("1","1"), ("2","2"), ("3","3")])[
				getOptionRenderer(verbosity)]
		tdEncEl = T.input(type="checkbox", id=render_cssid(key, "TDENC"),
			name="TDENC", class_="field boolean checkbox", value="True",
			style="width: auto")
		if tdEnc:
			tdEncEl(checked="checked")
		if readonly:
			for el in (formatEl, verbosityEl, tdEncEl):
				el(class_='readonly', readonly='readonly')
		# This crap is reproduced in the JS below -- rats
		if format=="HTML":
			verbVis = tdVis = "hidden"
		elif format=="VOPlot":
			verbVis, tdVis = "visible", "hidden"
		else:
			verbVis = tdVis = "visible"

		return T.div(class_="outputOptions")[
			T.inlineJS(_linkGeneratingJs),
			T.inlineJS('function adjustOutputFields(obj) {'
				'verbNode = obj.parentNode.childNodes[4];'
				'tdNode = obj.parentNode.childNodes[6];'
				'switch (obj.value) {'
					'case "HTML":'
						'verbNode.style.visibility="hidden";'
						'tdNode.style.visibility="hidden";'
						'break;'
					'case "VOPlot":'
						'verbNode.style.visibility="visible";'
						'tdNode.style.visibility="hidden";'
						'break;'
					'case "VOTable":'
						'verbNode.style.visibility="visible";'
						'tdNode.style.visibility="visible";'
						'break;'
					'}'
				'}'
			),
			"Format ", formatEl,
			T.span(id=render_cssid(key, "verbContainer"), style="visibility:%s"%
				verbVis)[" Verbosity ", verbosityEl], " ",
			T.span(id=render_cssid(key, "tdContainer"), style="visibility:%s"%
				tdVis)[tdEncEl, " VOTables for humans "],
			T.span(id=render_cssid(key, "QlinkContainer"))[
				T.a(href="", class_="resultlink", onMouseOver=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"]
			],
		]

	def _getArgDict(self, key, args):
		return {
			"format": args.get("FORMAT", [''])[0],
			"verbosity": args.get("VERB", ['2'])[0],
			"tdEnc": args.get("TDENC", ["False"])[0]}

	def render(self, ctx, key, args, errors):
		return self._renderTag(key, False, **self._getArgDict(key, args))

	def renderImmutable(self, ctx, key, args, errors):
		return self._renderTag(key, True, **self._getArgDict(key, args))

	def processInput(self, ctx, key, args):
		value = self._getArgDict(key, args)
		if not value["format"] in ["HTML", "VOTable", "VOPlot"]:
			raise validation.FieldValidationError("Unsupported output format")
		try:
			if not 1<=int(value["verbosity"])<=3:
				raise validation.FieldValidationError("Verbosity must be between"
					" 1 and 3")
		except ValueError:
			raise validation.FieldValidationError("Verbosity must be between"
					" 1 and 3")
		if value["tdEnc"] not in ["True", "False", None]:
			raise validation.FieldValidationError("tdEnc can only be True"
				" or False")
		value["tdEnc"] = value["tdEnc"]=="True"
		return value


class FormalDict(formaltypes.Type):
	"""is a formal type for dictionaries.
	"""
	pass


class MetaRenderMixin(object):
	"""is a mixin that allows inclusion of meta information.

	To do that, you say <tag render="meta">METAKEY</tag> or
	<tag render="metahtml">METAKEY</tag>
	"""
	def _doRenderMeta(self, ctx, flattenerFunc):
		metaKey = ctx.tag.children[0]
		metaVal = self.service.getMeta(metaKey)
		if metaVal:
			return ctx.tag.clear()[flattenerFunc(metaVal)]
		else:
			return T.comment["Meta item %s not given."%metaKey]

	def render_meta(self, ctx, data):
		return self._doRenderMeta(ctx, str)
	
	def render_metahtml(self, ctx, data):
		return self._doRenderMeta(ctx, lambda c: T.xml(c.asHtml()))


class ResourceBasedRenderer(rend.Page, MetaRenderMixin):
	"""is a page based on a resource descriptor.

	It is constructed with service parts of the form path/to/rd/service_name
	"""
	def __init__(self, serviceParts):
		rend.Page.__init__(self)
		self.serviceParts = serviceParts
		descriptorId, serviceId = parseServicePath(serviceParts)
		super(ResourceBasedRenderer, self).__init__()
		self.rd = resourcecache.getRd(descriptorId)
		if not self.rd.has_service(serviceId):
			raise UnknownURI("The service %s is not defined"%serviceId)
		self.service = self.rd.get_service(serviceId)


class HtmlTableFragmentPreformat(rend.Fragment):
	"""renders a table in HTML doing the value formatting before rendering.

	Don't use.
	"""
	def __init__(self, table):
		self.table = table
		super(HtmlTableFragment, self).__init__()

	def data_formatted(self, ctx, data):
		def makeHint(literalHint):
			parts = literalHint.split(",")
			return [parts[0]]+map(eval, parts[1:])
		formatter = queryrun.HtmlValueFormatter(None, None)
		formattedRows = []
		fieldProps = [(f.get_dest(), makeHint(f.get_displayHint()))
			for index, f in enumerate(self.table.getFieldDefs())]
		for row in self.table:
			newRow = {}
			for dest, hint in fieldProps:
				newRow[dest] = formatter.format(hint, row[dest], row)
			formattedRows.append(newRow)
		return formattedRows

	def _getDefaultHtmlRow(self):
		row = T.tr(render=rend.mapping, pattern="item")
		for f in self.table.getFieldDefs():
			row[T.td(data=T.slot(f.get_dest()), render=rend.data)]
		return row

	def rend(self, ctx, data):
		return T.table(border="1", render=rend.sequence, 
				data=self.data_formatted(None, None)) [
			self._getDefaultHtmlRow()]


class FormatterFactory:
	"""is a factory for functions mapping values to stan elements representing
	those values in HTML tables.
	"""
	def __call__(self, format, args):
		return getattr(self, "_make_%s_formatter"%format)(*args)

	def _make_string_formatter(self):
		return str

	def _make_hourangle_formatter(self, secondFracs=2):
		def format(deg):
			"""converts a float angle in degrees to an hour angle.
			"""
			rest, hours = math.modf(deg/360.*24)
			rest, minutes = math.modf(rest*60)
			return "%d %02d %2.*f"%(int(hours), int(minutes), secondFracs, rest*60)
		return format
	
	def _make_sexagesimal_formatter(self, secondFracs=1):
		def format(deg):
			"""converts a float angle in degrees to a sexagesimal angle.
			"""
			rest, degs = math.modf(deg)
			rest, minutes = math.modf(rest*60)
			return "%+d %02d %2.*f"%(int(degs), abs(int(minutes)), secondFracs,
				abs(rest*60))
		return format

	def _make_date_formatter(self, dateFormat="iso"):
		def format(date):
			if date==None:
				return "N/A"
			return date.strftime("%Y-%m-%d")
		return format

	def _make_juliandate_formatter(self, fracFigs=1):
		def format(date):
			return date.jdn
		return format


class HtmlTableFragment(rend.Fragment):
	"""is an HTML renderer for gavo Tables.
	"""
	def __init__(self, table):
		self.table = table
		super(HtmlTableFragment, self).__init__()
		self.formatterFactory = FormatterFactory()

	def _makeFormatFunction(self, hint):
		if hint==None:
			return str
		parts = hint.split(",")
		return self.formatterFactory(parts[0], map(eval, parts[1:]))

	def render_usehint(self, ctx, data):
		atts = ctx.tag.attributes
		formatVal = atts.get("formatter", None)
		if formatVal==None:
			formatVal = self._makeFormatFunction(atts.get("hint", None))
		if atts.has_key("formatter"): del ctx.tag.attributes["formatter"]
		if atts.has_key("hint"): del ctx.tag.attributes["hint"]
		return ctx.tag[formatVal(data)]

	def render_headCell(self, ctx, fieldDef):
		cont = fieldDef.get_tablehead()
		if cont==None:
			cont = fieldDef.get_description()
		if cont==None:
			cont = fieldDef.get_dest()
		desc = fieldDef.get_description()
		if desc==None:
			desc = cont
		return ctx.tag(title=desc)[T.xml(cont)]

	def render_defaultRow(self, ctx, items):
		for f in self.table.getFieldDefs():
			ctx.tag(render=rend.mapping)[T.td(data=T.slot(f.get_dest()), 
				formatter=self._makeFormatFunction(f.get_displayHint()), 
				render=T.directive("usehint"))]
		return ctx.tag

	def data_table(self, ctx, data):
		return self.table

	def data_fielddefs(self, ctx, data):
		return self.table.getFieldDefs()

	docFactory = loaders.stan(T.table(border="1")[
		T.tr(data=T.directive("fielddefs"), render=rend.sequence) [
			T.th(pattern="item", render=T.directive("headCell"))
		],
		T.invisible(
				render=rend.sequence,
				data=T.directive("table")) [
			T.tr(pattern="item", render=T.directive("defaultRow"))
		]
	])


class BaseResponse(ResourceBasedRenderer):
	"""is a base class for renderers rendering responses to standard
	service queries.
	"""
	def __init__(self, serviceParts, data):
		super(BaseResponse, self).__init__(serviceParts)
		self.data = data

	def data_query(self, ctx, data):
		if ctx:
			return self.service.getResult(self.data, ctx.arg("FILTER", "default"))
		else:
			return self.service.getResult(self.data, "default")


class HtmlResponse(BaseResponse):
	"""is a renderer for queries for HTML tables.
	"""
	def render_resulttable(self, ctx, data):
		return HtmlTableFragment(data.getTables()[0])

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Query Result"],
			T.link(rel="stylesheet", href="/formal.css", type="text/css"),
			T.script(type='text/javascript', src='/js/formal.js'),
		],
		T.body[
			T.h1["Query Result"],
			T.div(class_="result", data=T.directive("query"))[
				T.invisible(render=T.directive("resulttable")),
			]
		]])


class VOTableResponse(BaseResponse):
	def renderHTTP(self, ctx):
		data = defer.maybeDeferred(self.data_query, ctx, None)
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		request.setHeader('content-disposition', 
			'attachment; filename="votable.xml"')
		data.addCallback(lambda data: self._makeTable(request, data))
		data.addErrback(lambda err: self._makeErrorTable(request, err))
		return request.deferred

	def _makeErrorTable(self, request, err):
		f = cStringIO.StringIO("<xml>%s</xml>"%str(err))
		request.write(f.getvalue())
		request.finish()

	def _makeTable(self, request, data):
		f = cStringIO.StringIO()
		data.exportToVOTable(f)
		request.write(f.getvalue())
		request.finish()


def _formBehaviour_renderHTTP(self, ctx):
	# This function is monkeypatched into the resource.__behaviour to
	# make it accept form requests no matter what the request method is.
	request = inevow.IRequest(ctx)
	formName = request.args.get(form.FORMS_KEY, [None])[0]
	if formName is None:
			return None
	self.remember(ctx)
	d = defer.succeed(ctx)
	d.addCallback(form.locateForm, formName)
	d.addCallback(self._processForm, ctx)
	return d


class Form(formal.ResourceMixin, ResourceBasedRenderer):
	"""is a page that provides a search form for the selected service.
	"""
	def form_genForm(self, ctx=None, data={}):
		form = formal.Form()
		for field in self.service.getInputFields():
			type, widgetFactory = typesystems.sqltypeToFormal(field.get_dbtype())
			form.addField(field.get_dest(), 
				type(required=not field.get_optional()),
				widgetFactory,
				label=field.get_tablehead(),
				description=field.get_description())
			if field.get_default():
				form.data[field.get_dest()] = field.get_default()
			if data and data.has_key(field.get_dest()):
				form.data[field.get_dest()] = data[field.get_dest()]
		if self.service.count_output()>1:
			form.addField("FILTER", formal.String(), formal.widgetFactory(
				formal.SelectChoice, 
				options=[(k, self.service.get_output(k).get_name()) 
					for k in self.service.itemsof_output() if k!="default"],
				noneOption=("default", self.service.get_output("default").get_name())),
				label="Output form")
		form.addField("output", FormalDict, OutputOptions, label="Output")
		form.addAction(self.submitAction, label="Go")
		return form

	def renderHTTP(self, ctx):
		# XXX extreme pain: monkeypatch the resourceMixin's renderHTTP method
		self._ResourceMixin__behaviour().renderHTTP = new.instancemethod(
			_formBehaviour_renderHTTP, self._ResourceMixin__behaviour(),
			form.FormsResourceBehaviour)
		return super(Form, self).renderHTTP(ctx)

	def submitAction(self, ctx, form, data):
		format = ctx.arg("FORMAT", "VOTable")
		if format=="HTML":
			return HtmlResponse(self.serviceParts, data)
		elif format=="VOTable":
			return VOTableResponse(self.serviceParts, data)
		else:
			return ErrorResponse("Invalid output format: %s"%format)

	def process(self, ctx):
		super(Form, self).process(ctx)

	docFactory = loaders.stan(T.html[
		T.head[
			T.title(render=T.directive("meta"))["_title"],
			T.link(rel="stylesheet", href="/formal.css", type="text/css"),
			T.script(type='text/javascript', src='/js/formal.js'),
		],
		T.body[
			T.h1(render=T.directive("meta"))["_title"],
			T.div(id="intro", render=T.directive("metahtml"))["_intro"],
			T.invisible(render=T.directive("form genForm")),
			T.div(id="bottominfo", render=T.directive("metahtml"))["_bottominfo"],
			T.div(id="legal", render=T.directive("metahtml"))["_legal"],
		]])


class DebugPage(rend.Page):
	def __init__(self, *args, **kwargs):
		self.args, self.kwargs = args, kwargs

	def data_args(self, ctx, data):
		return self.args

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Debug page"],
		],
		T.body[
			T.h1["Here we go"],
			T.p["I was constructed with the following arguments:"],
			T.ul(render=rend.sequence, id="args", data=T.directive("args"))[
				T.li(pattern="item", render=rend.data)
			]
		]
	])


renderClasses = {
	"form": Form,
	"debug": DebugPage,
}


class ArchiveService(rend.Page):

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Archive Service"]
		],
		T.body[
			T.a(href="apfs/res/apfs_new/catquery/form")["Here"]
		]
	])

	def locateChild(self, ctx, segments):
		if not segments or not segments[0]:
			res = self
		else:
			name = segments[0]
			if hasattr(self, "child_"+name):
				return getattr(self, "child_"+name), segments[1:]
			
			act = segments[-1]
			try:
				res = renderClasses[act](segments[:-1])
			except UnknownURI:
				res = rend.FourOhFour()
			except:
				traceback.print_exc()
				res = rend.FourOhFour()
		return res, ()


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("querulator")
root = ArchiveService()
wsgiApp = wsgi.createWSGIApplication(root)
