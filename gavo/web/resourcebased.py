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
from gavo.parsing import contextgrammar
from gavo.web import common
from gavo.web import htmltable
from gavo.web import gwidgets
from gavo.web import standardcores

from gavo.web.common import Error, UnknownURI


class ResourceBasedRenderer(common.CustomTemplateMixin, rend.Page, 
		common.GavoRenderMixin):
	"""is a page based on a resource descriptor.

	It is constructed with service parts of the form path/to/rd/sub_id

	It leaves the resource descriptor in the rd attribute, and the sub_id
	(which is usually a service or data id) in the subId attribute.
	"""
	def __init__(self, serviceParts):
		self.serviceParts = serviceParts
		descriptorId, self.subId = common.parseServicePath(serviceParts)
		try:
			self.rd = resourcecache.getRd(descriptorId)
		except IOError:
			raise UnknownURI("/".join(serviceParts))
		super(ResourceBasedRenderer, self).__init__()


class ServiceBasedRenderer(ResourceBasedRenderer):
	"""is a resource based renderer using subId as a service id.

	These have the Service instance they should use in the service attribute.
	"""
	def __init__(self, serviceParts):
		super(ServiceBasedRenderer, self).__init__(serviceParts)
		if not self.rd.has_service(self.subId):
			raise common.UnknownURI("The service %s is not defined"%self.subId)
		self.service = self.rd.get_service(self.subId)


class DataBasedRenderer(ResourceBasedRenderer):
	"""is a resource based renderer using subId as a data id.

	These have the DataDescriptor instance they should operate on
	in the dataDesc attribute.
	"""
	def __init__(self, serviceParts):
		super(DataBasedRenderer, self).__init__(serviceParts)
		self.dataDesc = self.rd.getDataById(self.subId)


class BaseResponse(ServiceBasedRenderer):
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
		if data==None or data[1]==None or data[1]=='None':
			return ""
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


class GavoFormMixin(formal.ResourceMixin, object):
	"""is a mixin providing some desirable common behaviour for formal forms
	in the context of the archive service.
	"""
	def translateFieldName(self, name):
		"""returns the "root" source of errors in name.

		service.translateFieldName is a possible source of this data.

		You'll need to override this method in deriving classes that
		have fields derived from others.
		"""
		return name

	def _handleInputErrors(self, failure, ctx):
		"""goes as an errback to form handling code to allow correction form
		rendering at later stages than validation.
		"""
		if isinstance(failure.value, formal.FormError):
			self.form.errors.add(failure.value)
		elif isinstance(failure.value, gavo.ValidationError):
			if failure.value.fieldName!="<unknown>":# XXX TODO: check if field exists.
				self.form.errors.add(formal.FieldValidationError(str(failure.value),
					self.translateFieldName(failure.value.fieldName)))
			else:
				failure.printTraceback()
				self.form.errors.add(formal.FormError("Problem with input"
					" in some field: %s"%failure.getErrorMessage()))
		else:
			failure.printTraceback()
			raise failure.value
		return self.form.errors


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


class Form(GavoFormMixin, ServiceBasedRenderer):
	"""is a page that provides a search form for the selected service.
	"""
	def __init__(self, ctx, serviceParts):
		super(Form, self).__init__(serviceParts)
		if self.service.get_template("form"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("form"))

	def translateFieldName(self, name):
		return self.service.translateFieldName(name)

	def _makeWidgetFactory(self, field, type):
		"""returns a widget appropriate for field.

		The type is a *nevow formal* type, which is not necessarily
		inferable from the db type (see InputKeys vs. data fields).

		Really, right now we only see if we have an enumerated type,
		in which case we generate a selection box.
		"""
		if field.get_widgetFactory():
			return gwidgets.makeWidgetFactory(field.get_widgetFactory())
		if field.isEnumerated():
			items = field.get_values().get_options().copy()
			items.remove(field.get_values().get_default())
			return formal.widgetFactory(gwidgets.SimpleSelectChoice,
				[str(i) for i in items], str(field.get_values().get_default()))
		else:
			return None

	def _addDataField(self, form, field, data):
		"""adds a form field for the datadef.DataField to the form.
		"""
		type, widgetFactory = typesystems.sqltypeToFormal(field.get_dbtype())
		form.addField(field.get_dest(), 
			type(required=not field.get_optional()),
			self._makeWidgetFactory(field, type) or widgetFactory,
			label=field.get_tablehead(),
			description=field.get_description())
	
	def _addInputKey(self, form, field, data):
		"""adds a form field for the contextgrammar.InputKey to the form.

		In contrast to DataFields, for InputKeys we assume all validation
		is done in later stages of processing, i.e., we'll always have
		string as the nevow formal type and plain widgets (unless we have
		an enumerated type).
		"""
# XXX todo: make a widget that provides context-sensitive syntax help
		form.addField(field.get_source() or field.get_dest(),
			formal.String(required=not field.get_optional()),
			self._makeWidgetFactory(field, formal.String),
			label=field.get_tablehead(),
			description=field.get_description())

	def _addQueryFields(self, form, data):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		for field in self.service.getInputFields():
			if isinstance(field, contextgrammar.InputKey):
				self._addInputKey(form, field, data)
			else:
				self._addDataField(form, field, data)
			if field.get_default():
				form.data[field.get_dest()] = field.get_default()
			if data and data.has_key(field.get_dest()):
				form.data[field.get_dest()] = data[field.get_dest()]

	def _addMetaFields(self, form):
		"""adds fields to choose output properties to form.
		"""
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

	def form_genForm(self, ctx=None, data={}):
		form = formal.Form()
		self._addQueryFields(form, data)
		self._addMetaFields(form)
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
		queryMeta = common.QueryMeta(ctx)
		queryMeta["formal_data"] = data
		d = defer.maybeDeferred(self.service.getInputData, data
			).addCallback(self._formatResult, queryMeta
			).addErrback(self._handleInputErrors, ctx)
		return d

	# XXX TODO: add a custom error self._handleInputErrors(failure, ctx)
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
