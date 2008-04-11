"""
Resource descriptor-based pages.
"""

import cStringIO
import mutex
import new
import os
import sys
import time
import traceback
import urllib
import urlparse

import formal
from formal import form

from nevow import flat
from nevow import loaders
from nevow import inevow
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E

from twisted.internet import defer
from twisted.internet import threads

import gavo
from gavo import config
from gavo import resourcecache
from gavo import fitstable
from gavo import typesystems
from gavo import utils
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.web import common
from gavo.web import creds
from gavo.web import htmltable
from gavo.web import gwidgets
from gavo.web import producttar
from gavo.web import standardcores

from gavo.web.common import Error, UnknownURI


class RdBlocked(Exception):
	"""is raised when a ResourceDescriptor is blocked due to maintanence
	and caught by the dispatcher.
	"""


class ErrorPage(common.GavoRenderMixin, rend.Page):
	def __init__(self, failure, *args, **kwargs):
		self.failure = failure
		super(ErrorPage, self).__init__(*args, **kwargs)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		return defer.maybeDeferred(super(ErrorPage, self).renderHTTP(ctx)
			).addErrback(lambda _: request.finishRequest(False) or "")
	
	def render_errmsg(self, ctx, data):
		return ctx.tag[str(self.failure.getErrorMessage())]


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
	name = "form"
	def __init__(self, ctx, service, inputData, queryMeta):
		super(BaseResponse, self).__init__(ctx, service)
		self.queryResult = self.service.run(inputData, queryMeta)
		if self.service.get_template("response"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("response"))

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		return defer.maybeDeferred(self.data_query, ctx, None
			).addCallback(self._handleData, ctx
			).addErrback(self._handleError, ctx)

	def data_query(self, ctx, data):
		return self.queryResult

	data_result = data_query


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
	def _handleData(self, data, ctx):
		request = inevow.IRequest(ctx)
		if data.queryMeta.get("Overflow"):
			fName = "truncated_votable.xml"
		else:
			fName = "votable.xml"
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%fName)
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
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.write(">>>> INTERNAL ERROR, INVALID OUTPUT <<<<")
		return request.finishRequest(False) or ""


tag_embed = T.Proto("embed")
tag_noembed = T.Proto("noembed")


class VOPlotResponse(common.GavoRenderMixin, rend.Page):
	"""returns a page embedding the VOPlot applet.

	This doesn't inherit from BaseResponse since we don't need the
	query results here, so computing them would be wasteful.
	"""
	name = "form"
	def __init__(self, service):
		self.service = service

	def render_voplotArea(self, ctx, data):
		request = inevow.IRequest(ctx)
		parameters = request.args.copy()
		parameters["_FORMAT"]=["VOTable"]
		parameters["_TDENC"]=["True"]
		return tag_embed(type = "application/x-java-applet",
				code="com.jvt.applets.PlotVOApplet",
				codebase=config.get("web", "voplotCodebase"),
				votablepath=urlparse.urljoin(config.get("web", "serverURL"),
					request.path),
				userguideURL=config.get("web", "voplotUserman"),
				archive=("voplot.jar,voplot_3rdParty/Aladin.jar,voplot_3rdParty/"
					"cern.jar,voplot_3rdParty/fits-0.99.1-1.4-compiled.jar,"
					"voplot_3rdParty/commons-discovery-0.2.jar,"
					"voplot_3rdParty/commons-logging-1.0.4.jar,"
					"voplot_3rdParty/axis.jar,voplot_3rdParty/jaxrpc.jar,"
					"voplot_3rdParty/log4j-1.2.8.jar,voplot_3rdParty/saaj.jar,"
					"voplot_3rdParty/wsdl4j-1.5.1.jar"),
				width="850",
				height="650",
				parameters="?"+urllib.urlencode(parameters, doseq=True),
				MAYSCRIPT="true",
				background="#faf0e6",
				scriptable="true",
				pluginspage="http://java.sun.com/products/plugin/1.3.1/"
					"plugin-install.html")[
					tag_noembed["No Java Plug-in support for applet, see, e.g., ",
						T.a(href="http://java.sun.com/products/plugin/")[
							"http://java.sun.com/products/plugin"],
						"."]]

	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title(render=T.directive("meta"))["title"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.div(class_="voplotarea", render=T.directive("voplotArea"),
				style="text-align:center"),
		]
	])


class FileResponse(BaseResponse):
	"""is an abstract base class for responses calling out to generate
	a file to be delivered.
	"""
	def _handleData(self, data, ctx):
		self.coreResult = data
		request = inevow.IRequest(ctx)
		return threads.deferToThread(self.generateFile, request
			).addCallback(self._serveFile, request
			).addErrback(self._handleError, ctx)

	def generateFile(self, request):
		"""has to return a file name containing the data to be delivered.

		The data to operate on are in the coreResult attribute.
		"""
	
	def getTargetName(self):
		"""has to return a pair of file name, MIME type.
		"""

	# must be some stan that can be used to construct an ErrorPage
	errorFactory = None

	def _realHandleError(self, failure, ctx):
		failure.printTraceback()
		errPg = ErrorPage(failure, docFactory=self.errorFactory)
		return errPg

	def _handleError(self, failure, ctx):
		try:
			return self._realHandleError(failure, ctx)
		except:
			traceback.print_exc()
			request = inevow.IRequest(ctx)
			request.setHeader("content-type", "text/plain")
			request.setResponseCode(500)
			request.write("Yikes.  There was an error generating your file,\n"
				"and another error rendering the error.\n"
				"You should report this. Thanks.\n")
		return request.finishRequest(False) or ""

	def _serveFile(self, filePath, request):
		name, mime = self.getTargetName()
		request.setHeader("content-type", mime)
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%name)
		static.FileTransfer(open(filePath), os.path.getsize(filePath),
			request)
		os.unlink(filePath)
		return request.deferred


# pyfits obviously is not thread-safe.  We put a mutex around it
# and hope we'll be fine.
_fitsTableMutex = mutex.mutex()

class FITSTableResponse(FileResponse):
	def generateFile(self, request):
		while not _fitsTableMutex.testandset():
			time.sleep(0.1)
		try:
			res = fitstable.makeFITSTableFile(self.coreResult.original)
		finally:
			_fitsTableMutex.unlock()
		return res
	
	def getTargetName(self):
		if self.coreResult.queryMeta.get("Overflow"):
			return "truncated_data.fits", "application/x-fits"
		else:
			return "data.fits", "application/x-fits"

	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["FITS generation failed"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["FITS generation failed"],
				T.p["We're sorry, but the generation of the FITS file didn't work"
					" out.  You're welcome to report this failure, but, frankly,"
					" our main output format for structured data is the VOTable,"
					" and you should consider using it.  Check out ",
					T.a(href="http://www.star.bris.ac.uk/~mbt/topcat/")[
						"topcat"],
					" for starters."],
				T.p["Anyway, here's the error message you should send in together"
					" with the URL you were using with your bug report: ",
					T.tt(render=T.directive("errmsg")),],
				T.p["Thanks."],
			]])


class TarResponse(FileResponse):
	"""delivers a tar of products contained.
	"""
	def generateFile(self, request):
		return producttar.getTarMaker().getTarFile(self.coreResult, 
			request.getUser(), request.getPassword())
	
	def getTargetName(self):
		if self.coreResult.queryMeta.get("Overflow"):
			return "truncated_data.tar", "application/x-tar"
		else:
			return "data.tar", "application/x-tar"

	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["tar generation failed"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["tar generation failed"],
				T.p["We're sorry, but the creation of the tar file didn't work"
					" out.  Please report this failure to the operators"
					" giving the URL you were using and the following message: ",
					T.tt(render=T.directive("errmsg"))],
				T.p["Thanks."],
			]])


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
		self.queryResult = None

	def renderer(self, ctx, name):
		"""returns code for a renderer named name.

		This overrides the method inherited from nevow's RenderFactory to
		add a lookup in our service.
		"""
		if self.service.get_specRend(name):
			return self.service.get_specRend(name)
		return super(Form, self).renderer(ctx, name)

	# renderers for HTML tables
	def render_resulttable(self, ctx, data):
		return htmltable.HTMLTableFragment(data.child(ctx, "table"), 
			data.queryMeta)

	def render_parpair(self, ctx, data):
		if data==None or data[1]==None or "__" in data[0]:
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
	
	def data_query(self, ctx, data):
		return self.queryResult
	
	data_result = data_query
	#end renderers for html tables

	def translateFieldName(self, name):
		return self.service.translateFieldName(name)

	def _addInputKey(self, form, inputKey, data):
		"""adds a form field for an inputKey to the form.
		"""
		unit = ""
		if inputKey.get_dbtype()!="date":  # Sigh.
			unit = inputKey.get_inputUnit() or inputKey.get_unit() or ""
			if unit:
				unit = " [%s]"%unit
		label = inputKey.get_tablehead() or inputKey.get_dest()
		form.addField(inputKey.get_dest(), 
			inputKey.get_formalType(),
			inputKey.get_widgetFactory(),
			label=label+unit,
			description=inputKey.get_description())
	
	def _addQueryFields(self, form, data):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		for field in self.service.getInputFields():
			self._addInputKey(form, field, data)
			if data and data.has_key(field.get_dest()):
				form.data[field.get_dest()] = data[field.get_dest()]
			elif field.get_default():
				form.data[field.get_dest()] = field.get_default()

	def _fakeDefaults(self, form, ctx):
		"""adds keys not yet in form.data but present in ctx to form.data.

		The idea here is that you can bookmark template forms.  The
		values in the bookmark are not normally picked up since _processForm 
		doesn't run.
		"""
		for key, val in inevow.IRequest(ctx).args.iteritems():
			if key not in form.data:
				form.data[key] = val

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
		self._fakeDefaults(form, ctx)
		if self.name=="form":
			form.addField("_OUTPUT", formal.String, 
				formal.widgetFactory(gwidgets.OutputFormat, self.service, queryMeta),
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

	def _computeResult(self, ctx, service, inputData, queryMeta):
		self.queryResult = self.service.run(inputData, queryMeta)
		if self.service.get_template("response"):
			self.customTemplate = os.path.join(self.rd.get_resdir(),
				self.service.get_template("response"))
		request = inevow.IRequest(ctx)
		del request.args["__nevow_form__"]
		return self

	# XXX TODO: add a custom error self._handleInputErrors(failure, ctx)
	# to catch FieldErrors and display a proper form on such errors.
	def _runService(self, inputData, queryMeta, ctx):
		format = queryMeta["format"]
		if format=="HTML":
			return self._computeResult(ctx, self.service, inputData, queryMeta)
		elif format=="VOTable":
			res = VOTableResponse(ctx, self.service, inputData, queryMeta)
			return res
		elif format=="VOPlot":
			return VOPlotResponse(self.service)
		elif format=="FITS":
			return FITSTableResponse(ctx, self.service, inputData, queryMeta)
		elif format=="tar":
			return TarResponse(ctx, self.service, inputData, queryMeta)
		else:
			raise gavo.ValidationError("Invalid output format: %s"%format,
				"_OUTPUT")

	def process(self, ctx):
		super(Form, self).process(ctx)

	defaultDocFactory = common.doctypedStan(T.html[
		T.head(render=T.directive("commonhead"))[
			T.title(render=T.directive("meta"))["title"],
		],
		T.body(render=T.directive("withsidebar"))[
			T.h1(render=T.directive("meta"))["title"],
			T.div(class_="result", render=T.directive("ifdata"), 
					data=T.directive("query")) [
				T.div(class_="querypars", data=T.directive("queryseq"))[
					T.h2[T.a(href="#_queryForm")["Parameters"]],
					T.ul(render=rend.sequence)[
						T.li(pattern="item", render=T.directive("parpair"))
					],
				],
				T.h2["Result"],
				T.div(class_="resmeta", data=T.directive("resultmeta"),
					render=T.directive("mapping"))[
					T.p[
						"Matched: ", T.slot(name="itemsMatched"),
					],
				],
				T.p(class_="warning", render=T.directive("warnTrunc")),
				T.div(class_="result")[
					T.invisible(render=T.directive("resulttable")),
				],
				T.h2[T.a(name="_queryForm")["Query Form"]],
			],
			T.div(id="intro", render=T.directive("metahtml"))["_intro"],
			T.invisible(render=T.directive("form genForm")),
			T.div(id="bottominfo", render=T.directive("metahtml"))["_bottominfo"],
			T.div(class_="copyright", render=T.directive("metahtml"))["_copyright"],
		]])


def compileCoreRenderer(source):
	"""returns a code object that can be inserted as a method to a service.

	This is used to implement renderers usable in custom templates for
	services.  The code is defined in a service declaration in the resource
	descriptor.
	"""
	ns = dict(globals())
	ns["source"] = source
	code = ("def renderForNevow(self, ctx, data):\n"
		"  try:\n"+
		utils.fixIndentation(source, "     ")+"\n"
		"  except:\n"
		"    sys.stderr.write('Error in\\n%s\\n'%source)\n"
		"    traceback.print_exc()\n"
		"    raise\n")
	try:
		exec code in ns
	except SyntaxError:
		sys.stderr.write("Invalid source:\n%s\n"%code)
		raise
	return ns["renderForNevow"]


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
