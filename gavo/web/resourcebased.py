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
from nevow import static
from nevow import tags as T, entities as E

from twisted.internet import defer

import gavo
from gavo import resourcecache
from gavo import typesystems
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.web import common
from gavo.web import creds
from gavo.web import htmltable
from gavo.web import gwidgets
from gavo.web import standardcores

from gavo.web.common import Error, UnknownURI


class RdBlocked(Exception):
	"""is raised when a ResourceDescriptor is blocked due to maintanence
	and caught by the dispatcher.
	"""


class ResourceBasedRenderer(common.CustomTemplateMixin, rend.Page, 
		common.GavoRenderMixin):
	"""is a page based on a resource descriptor.

	It is constructed with a resource descriptor and leave it
	in the rd attribute.
	"""
	def __init__(self, ctx, rd):
		self.rd = rd
		if hasattr(self.rd, "currently_blocked"):
			raise RdBlocked()
		super(ResourceBasedRenderer, self).__init__()


class ServiceBasedRenderer(ResourceBasedRenderer):
	"""is a resource based renderer using subId as a service id.

	These have the Service instance they should use in the service attribute.
	"""
	name = None

	def __init__(self, ctx, service):
		super(ServiceBasedRenderer, self).__init__(ctx, service.rd)
		self.service = service
		if not self.name in self.service.get_allowedRenderers():
			raise UnknownURI("The renderer %s is not allowed on this service."%
				self.name)


def getServiceRend(ctx, serviceParts, rendClass):
	"""returns a renderer for the service described by serviceParts.

	This is the function you should use to construct renderers.  It will
	construct the service, check auth, etc.
	"""
	def makeRenderer(service):
		return rendClass(ctx, service)
	descriptorId, subId = common.parseServicePath(serviceParts)
	try:
		rd = resourcecache.getRd(descriptorId)
	except IOError:
		raise UnknownURI("/".join(serviceParts))
	if not rd.has_service(subId):
		raise UnknownURI("The service %s is not defined"%subId)
	service = rd.get_service(subId)
	if service.get_requiredGroup():
		return creds.runAuthenticated(ctx, service.get_requiredGroup(),
			makeRenderer, service)
	else:
		return makeRenderer(service)


class BaseResponse(ServiceBasedRenderer):
	"""is a base class for renderers rendering responses to standard
	service queries.
	"""
	def __init__(self, ctx, service, inputData, queryMeta):
		super(BaseResponse, self).__init__(ctx, service)
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
	name = "form"

	def render_resulttable(self, ctx, data):
		return htmltable.HTMLTableFragment(data.child(ctx, "table"))

	def render_parpair(self, ctx, data):
		if data==None or data[1]==None:
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
			T.invisible(render=T.directive("commonhead")),
		],
		T.body(data=T.directive("query"))[
			T.h1(render=T.directive("meta"))["_title"],
			T.p(class_="warning", render=T.directive("warnTrunc")),
			T.div(class_="querypars", data=T.directive("queryseq"))[
				T.h2["Parameters"],
				T.ul(render=rend.sequence)[
					T.li(pattern="item", render=T.directive("parpair"))
				]
			],
			T.h2["Result"],
			T.div(class_="result") [
				T.div(class_="resmeta", data=T.directive("resultmeta"),
					render=T.directive("mapping"))[
					T.p[
						"Matched: ", T.slot(name="itemsMatched"),
					],
				],
				T.div(class_="result")[
					T.invisible(render=T.directive("resulttable")),
				],
			],
			T.div(class_="copyright", render=T.directive("metahtml"))["_copyright"],
		]])


def writeVOTable(request, dataSet, tableMaker):
	"""writes the VOTable representation  of the DataSet instance
	dataSet as created by tableMaker to request.
	"""
# XXX TODO: Make this asynchronous (else slow clients with big tables
# will bring you to a grinding halt)
	vot = tableMaker.makeVOT(dataSet)
	f = cStringIO.StringIO()
	tableMaker.writeVOT(vot, f)
	request.write(f.getvalue())
	request.finish()
	return ""  # shut off further rendering


def serveAsVOTable(request, data):
	"""writes a VOTable representation of the CoreResult instance data
	to request.
	"""
	request.setHeader("content-type", "application/x-votable")
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
	name = "form"
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		defer.maybeDeferred(self.data_query, ctx, None
			).addCallback(self._handleData, ctx
			).addErrback(self._handleError, ctx)
		return request.deferred

	def _handleData(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('content-disposition', 
			'attachment; filename=votable.xml')
		defer.maybeDeferred(serveAsVOTable, request, data
			).addCallback(self._tableWritten, ctx
			).addErrback(self._handleErrorDuringRender, ctx)
		return request.deferred

	def _tableWritten(self, dummy, ctx):
		pass
	
	def _handleError(self, failure, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/html")
		request.setHeader('content-disposition', 'inline')
		request.setResponseCode(500)
		return failure
	
	def _handleErrorDuringRender(self, failure, ctx):
		print ">>>>>>>>>>>>< During Render"
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.write(">>>> INTERNAL ERROR, INVALID OUTPUT <<<<")
		return request.finishRequest(False) or ""


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
				self.form.errors.add(formal.FieldValidationError(failure.value.msg,
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
	name = "form"
	def __init__(self, ctx, service):
		super(Form, self).__init__(ctx, service)
		if self.service.get_template("form"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("form"))
		self._ResourceMixin__behaviour().renderHTTP = new.instancemethod(
			_formBehaviour_renderHTTP, self._ResourceMixin__behaviour(),
			form.FormsResourceBehaviour)

	def translateFieldName(self, name):
		return self.service.translateFieldName(name)

	def _addInputKey(self, form, inputKey, data):
		"""adds a form field for an inputKey to the form.
		"""
		form.addField(inputKey.get_dest(), 
			inputKey.get_formalType(),
			inputKey.get_widgetFactory(),
			label=inputKey.get_tablehead(),
			description=inputKey.get_description())
	
	def _addQueryFields(self, form, data):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		for field in self.service.getInputFields():
			self._addInputKey(form, field, data)
			if field.get_default():
				form.data[field.get_dest()] = field.get_default()
			if data and data.has_key(field.get_dest()):
				form.data[field.get_dest()] = data[field.get_dest()]

	def _addMetaFields(self, form, queryMeta):
		"""adds fields to choose output properties to form.
		"""
		if self.service.count_output()>1:
			form.addField("_FILTER", formal.String(), formal.widgetFactory(
				formal.SelectChoice, 
				options=[(k, self.service.get_output(k).get_name()) 
					for k in self.service.itemsof_output() if k!="default"],
				noneOption=("default", self.service.get_output("default").get_name())),
				label="Output form")
		if (isinstance(self.service.get_core(), standardcores.DbBasedCore) and
				self.service.get_core().wantsTableWidget()):
			form.addField("_DBOPTIONS", gwidgets.FormalDict,
				formal.widgetFactory(gwidgets.DbOptions, self.service, queryMeta),
				label="Table")

	def form_genForm(self, ctx=None, data={}):
		queryMeta = common.QueryMeta(ctx)
		form = formal.Form()
		self._addQueryFields(form, data)
		self._addMetaFields(form, queryMeta)
		if self.name=="form":
			form.addField("_OUTPUT", formal.String, 
				formal.widgetFactory(gwidgets.OutputFormat, self.service),
				label="Output format")
		form.addAction(self.submitAction, label="Go")
		self.form = form
		return form

	def submitAction(self, ctx, form, data):
		queryMeta = common.QueryMeta(ctx)
		queryMeta["formal_data"] = data
		d = defer.maybeDeferred(self.service.getInputData, data
			).addCallback(self._runService, queryMeta, ctx
			).addErrback(self._handleInputErrors, ctx)
		return d

	# XXX TODO: add a custom error self._handleInputErrors(failure, ctx)
	# to catch FieldErrors and display a proper form on such errors.
	def _runService(self, inputData, queryMeta, ctx):
		format = queryMeta["format"]
		if format=="HTML":
			return HtmlResponse(ctx, self.service, inputData, queryMeta)
		elif format=="VOTable":
			res = VOTableResponse(ctx, self.service, inputData, queryMeta)
			return res
		else:
			raise Error("Invalid output format: %s"%format)

	def process(self, ctx):
		super(Form, self).process(ctx)

	defaultDocFactory = loaders.stan(T.html[
		T.head[
			T.title(render=T.directive("meta"))["title"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.h1(render=T.directive("meta"))["title"],
			T.div(id="intro", render=T.directive("metahtml"))["_intro"],
			T.invisible(render=T.directive("form genForm")),
			T.div(id="bottominfo", render=T.directive("metahtml"))["_bottominfo"],
			T.div(id="legal", render=T.directive("metahtml"))["_legal"],
		]])


class Static(GavoFormMixin, ServiceBasedRenderer):
	"""is a renderer that just hands through files.

	On this, you can either have a template "static" or have a static core
	returning a table with with a column called "filename".  The
	file designated in the first row will be used as-is.

	Queries with remaining segments return files from the staticData
	directory of the service.
	"""
	name = ".static."

	def __init__(self, ctx, service):
		ServiceBasedRenderer.__init__(self, ctx, service)
		if not service.get_staticData():
			raise UnknownURI("No static data on this service") # XXX TODO: FORBIDDEN
		if self.service.get_template("static"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("static"))
		self.basePath = os.path.join(service.rd.get_resdir(),
			service.get_staticData())
		self.rend = static.File(self.basePath)
	
	def renderHTTP(self, ctx):
		if inevow.ICurrentSegments(ctx)[-1] != '':
			request = inevow.IRequest(ctx)
			request.redirect(request.URLPath().child(''))
			return ''
		if self.customTemplate:
			return super(Static, self).renderHTTP(ctx)
		else:
			return self.service.run(None).addCallback(self._renderResultDoc, ctx)
	
	def _renderResultDoc(self, coreResult, ctx):
		rows = coreResult.original.getPrimaryTable().rows
		if len(rows)==0:
			raise UnknownURI("No matching resource")
		relativeName = rows[0]["filename"]
		return static.File(os.path.join(self.basePath, relativeName)
			).renderHTTP(ctx)

	def locateChild(self, ctx, segments):
		if segments==('',):
			return self, ()
		return self.rend.locateChild(ctx, segments)
