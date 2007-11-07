"""
Resource descriptor-based pages.
"""

import cStringIO
import new
import os

import formal
from formal import form

from nevow import loaders
from nevow import inevow
from nevow import rend
from nevow import tags as T, entities as E

from twisted.internet import defer

import gavo
from gavo import resourcecache
from gavo import typesystems
from gavo import votable
from gavo.web import common
from gavo.web import htmltable
from gavo.web import gwidgets
from gavo.web import standardcores

from gavo.web.common import Error


class ResourceBasedRenderer(common.CustomTemplateMixin, rend.Page, 
		common.GavoRenderMixin):
	"""is a page based on a resource descriptor.

	It is constructed with service parts of the form path/to/rd/service_name
	"""
	def __init__(self, serviceParts):
		self.serviceParts = serviceParts
		descriptorId, serviceId = common.parseServicePath(serviceParts)
		self.rd = resourcecache.getRd(descriptorId)
		if not self.rd.has_service(serviceId):
			raise common.UnknownURI("The service %s is not defined"%serviceId)
		self.service = self.rd.get_service(serviceId)
		super(ResourceBasedRenderer, self).__init__()


class BaseResponse(ResourceBasedRenderer):
	"""is a base class for renderers rendering responses to standard
	service queries.
	"""
	def __init__(self, serviceParts, inputData, queryMeta):
		super(BaseResponse, self).__init__(serviceParts)
		self.queryResult = self.service.run(inputData, queryMeta)
		if self.service.get_template("response"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("response"))

	def data_query(self, ctx, data):
		return self.queryResult

	data_result = data_query


class HtmlResponse(BaseResponse):
	"""is a renderer for queries for HTML tables.
	"""
	def render_resulttable(self, ctx, data):
		return htmltable.HtmlTableFragment(data.child(ctx, "table"))

	def render_parpair(self, ctx, data):
		return ctx.tag["%s: %s"%data]
	
	def render_warnTrunc(self, ctx, data):
		if data.queryMeta.get("Overflow"):
			return ctx.tag["Your query limit of %d rows was reached.  You may"
				" want to resubmit your query with a higher match limit."
				" Note that truncated queries without sorting are not"
				" reproducible."%data.queryMeta["dbLimit"]]
		else:
			return ""

	defaultDocFactory = loaders.stan(T.html[
		T.head[
			T.title["Query Result"],
			T.link(rel="stylesheet", href=common.makeSitePath("/formal.css"), 
				type="text/css"),
			T.script(type='text/javascript', 
				src=common.makeSitePath('/js/formal.js')),
		],
		T.body(data=T.directive("query"))[
			T.h1["Query Result"],
			T.p(class_="warning", render=T.directive("warnTrunc")),
			T.div(class_="querypars", data=T.directive("queryseq"))[
				T.h2["Parameters"],
				T.ul(render=rend.sequence)[
					T.li(pattern="item", render=T.directive("parpair"))
				]
			],
			T.div(class_="result") [
				T.div(class_="resmeta", data=T.directive("resultmeta"),
					render=T.directive("mapping"))[
					T.p[
						"Matched: ", T.slot(name="itemsMatched"),
					],
				],
				T.div(class_="result")[
					T.invisible(render=T.directive("resulttable")),
				]
			]
		]])


class VOTableResponse(BaseResponse):
	def __init__(self, serviceParts, data):
		BaseResponse.__init__(self, serviceParts, data)

	def renderHTTP(self, ctx):
		data = defer.maybeDeferred(self.data_query, ctx, None)
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		request.setHeader('content-disposition', 
			'attachment; filename=votable.xml')
		data.addCallback(lambda data: self._makeTable(request, data))
		data.addErrback(lambda err: self._makeErrorTable(request, err))
		return request.deferred

	def _makeErrorTable(self, request, err):
		f = cStringIO.StringIO("<xml>%s</xml>"%(str(err).replace("<","&lt;")))
		request.write(f.getvalue())
		request.finish()

	def _makeTable(self, request, data):
		tablemaker = votable.VOTableMaker({
			True: "td",
			False: "binary"}[data.queryMeta["tdEnc"]])
		vot = tablemaker.makeVOT(data)
		f = cStringIO.StringIO()
		tablemaker.writeVOT(vot, f)
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
	def __init__(self, serviceParts):
		super(Form, self).__init__(serviceParts)
		if self.service.get_template("form"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("form"))

	def form_genForm(self, ctx=None, data={}):
		form = formal.Form()
		for field in self.service.getInputFields():
			type, widgetFactory = typesystems.sqltypeToFormal(field.get_dbtype())
			if field.get_widgetFactory():
				widgetFactory = gwidgets.makeWidgetFactory(field.get_widgetFactory())
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
			form.addField("_FILTER", formal.String(), formal.widgetFactory(
				formal.SelectChoice, 
				options=[(k, self.service.get_output(k).get_name()) 
					for k in self.service.itemsof_output() if k!="default"],
				noneOption=("default", self.service.get_output("default").get_name())),
				label="Output form")
		if isinstance(self.service.get_core(), standardcores.DbBasedCore):
			form.addField("_DBOPTIONS", gwidgets.FormalDict,
				formal.widgetFactory(gwidgets.DbOptions, self.service),
				label="Table", description="Sort keys are only relevant for HTML"
					" output.  Queries hitting the match limit are only reproducible"
					" with sorting.")
		form.addField("_OUTPUT", gwidgets.FormalDict, 
			gwidgets.OutputOptions, label="Output format")
		form.addAction(self.submitAction, label="Go")
		self.form = form
		return form

	def renderHTTP(self, ctx):
		# XXX extreme pain: monkeypatch the resourceMixin's renderHTTP method
		self._ResourceMixin__behaviour().renderHTTP = new.instancemethod(
			_formBehaviour_renderHTTP, self._ResourceMixin__behaviour(),
			form.FormsResourceBehaviour)
		return super(Form, self).renderHTTP(ctx)

	def submitAction(self, ctx, form, data):
		queryMeta = common.QueryMeta(data)
		d = defer.maybeDeferred(self.service.getInputData, data
			).addCallback(self._formatResult, queryMeta
			).addErrback(self._handleInputError, queryMeta)
		return d

	def _handleInputError(self, failure, queryMeta):
		if isinstance(failure.value, formal.FormError):
			self.form.errors.add(failure.value)
		elif isinstance(failure.value, gavo.ValidationError):
			self.form.errors.add(formal.FieldValidationError(str(failure.value),
				self.service.translateFieldName(failure.value.fieldName)))
		else:
			failure.printTraceback()
			raise failure.value
		return self.form.errors

	# XXX TODO: add a custom error self._handleInputError(failure, queryMeta)
	# to catch FieldErrors and display a proper form on such errors.
	def _formatResult(self, inputData, queryMeta):
		format = queryMeta["format"]
		if format=="HTML":
			return HtmlResponse(self.serviceParts, inputData, queryMeta)
		elif format=="VOTable":
			return VOTableResponse(self.serviceParts, inputData, queryMeta)
		else:
			raise Error("Invalid output format: %s"%format)

	def process(self, ctx):
		super(Form, self).process(ctx)

	defaultDocFactory = loaders.stan(T.html[
		T.head[
			T.title(render=T.directive("meta"))["_title"],
			T.link(rel="stylesheet", href=common.makeSitePath("/formal.css"), 
				type="text/css"),
			T.script(type='text/javascript', src='/js/formal.js'),
		],
		T.body[
			T.h1(render=T.directive("meta"))["_title"],
			T.div(id="intro", render=T.directive("metahtml"))["_intro"],
			T.invisible(render=T.directive("form genForm")),
			T.div(id="bottominfo", render=T.directive("metahtml"))["_bottominfo"],
			T.div(id="legal", render=T.directive("metahtml"))["_legal"],
		]])
