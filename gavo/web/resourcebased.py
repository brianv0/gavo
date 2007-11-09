"""
Resource descriptor-based pages.
"""

import cStringIO
import new
import os
import traceback

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


def writeVOTable(request, dataSet, tableMaker):
	"""writes the VOTable representation  of the DataSet instance
	dataSet as created by tableMaker to request.
	"""
# XXX TODO: Make this asynchronous (else slow clients with big tables
# will bring you to a grinding halt)
	try:
		vot = tableMaker.makeVOT(dataSet)
		f = cStringIO.StringIO()
		tableMaker.writeVOT(vot, f)
		request.write(f.getvalue())
		request.finish()
	except:
# XXX TODO: emit some sensible emergency stuff here
		traceback.print_exc()
		request.write("<<< >>>PANIC: INTERNAL ERROR, DATA NOT COMPLETE")
	return ""  # shut off further rendering


def serveAsVOTable(request, data):
	"""writes a VOTable representation of the CoreResult instance data
	to request.
	"""
	tableMaker = votable.VOTableMaker({
		True: "td",
		False: "binary"}[data.queryMeta["tdEnc"]])
	return writeVOTable(request, data.original, tableMaker)


class VOTableResponse(BaseResponse):
	"""is a renderer for queries for VOTables.  
	
	It's not immediately suitable for "real" VO services since it will return
	HTML error pages and re-display forms if their values don't validate.

	An example for a "real" VO service is siapservice.SiapService.
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		defer.maybeDeferred(self.data_query, ctx, None
			).addCallback(self._handleData, ctx
			).addErrback(self._handleError, ctx)
		return request.deferred

	def _handleData(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		request.setHeader('content-disposition', 
			'attachment; filename=votable.xml')
		serveAsVOTable(request, data
			).addCallback(self._tableWritten, ctx
			).addErrback(self._handleError, ctx)
		return request.deferred

	def _tableWritten(self, dummy, ctx):
		pass
	
	def _handleError(self, failure, ctx):
# XXX TODO Work on this
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/html")
		request.setHeader('content-disposition', 'inline')
		request.setResponseCode(500)
		print ">>>>>>>>>>>>>>>> Error, will hang, find out why"
		failure.printTraceback()
		return failure



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
	def __init__(self, ctx, serviceParts):
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
				label="Table")
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
			).addErrback(self._handleInputError, ctx, queryMeta)
		return d

	def _handleInputError(self, failure, ctx, queryMeta):
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
			res = VOTableResponse(self.serviceParts, inputData, queryMeta)
			return res
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
