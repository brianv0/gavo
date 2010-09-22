"""
The form renderer and related code.
"""

# XXX TODO: break this up.

import cStringIO
import imp
import mutex
import new
import os
import sys
import time
import traceback
import urllib
import urlparse


from nevow import context
from nevow import flat
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from nevow import url
from nevow import util

from twisted.internet import defer
from twisted.internet import threads

from zope.interface import implements

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo.imp import formal
from gavo.imp.formal import form
from gavo.formats import csvtable
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.base import typesystems
from gavo.web import common
from gavo.web import grend
from gavo.web import producttar
from gavo.web import streaming

from gavo.svcs import Error, UnknownURI, ForbiddenURI


class ServiceResource(grend.ServiceBasedRenderer):
	"""is a base class for resources answering the form renderer.

	They receive a service and the form data from formal.

	This whole interplay is governed by the form renderer below.

	Deriving classes should override 
	
		- _obtainOutput(ctx) -- returns the result of running the service 
			conditioned on the specific resource type; the default implementation 
			may do.  *Note*: _obtainOutput must return a deferred, whereas the
			standard service is synchronous.
		- _formatOutput(result, ctx) -- receives the result of _obtainOutput
			and has to do the formatting
		- _handleOtherErrors(failure, ctx) -- is called when an exception
			occurs that cannot be displayed in a form.  The default implementation
			delivers a page built from stan in the errorFactory class attribute,
			using grend.ErrorPage as renderer.
	"""
	name = "form"
	def __init__(self, ctx, service, formalData):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		self.formalData = formalData

	def renderHTTP(self, ctx):
		return self._obtainOutput(ctx
			).addCallback(self._formatOutput, ctx
			).addErrback(self._handleOtherErrors, ctx)

	def _obtainOutput(self, ctx):
		return self.runServiceWithContext(self.formalData, ctx)

	def _formatOutput(self, res, ctx):
		return ""

	def _handleOtherErrors(self, failure, ctx):
		failure.printTraceback()
		if isinstance(failure, (base.ValidationError, formal.FormError)):
			return failure
		return grend.ErrorPage(failure, docFactory=self.errorFactory)

	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["Unexpected Exception"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["Unexpected Exception"],
				T.p["An unexpected error happened, and we would be very"
					" grateful if you could report what you did to",
					T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
						"gavo@ari.uni-heidelberg.de"],
					", since figuring out what went wrong is much easier"
					" knowing this than by just expecting our server's local"
					" problem report."],
				T.p["You should include the following error message and the"
					" URL you were using with your bug report: ",
					T.tt(render=T.directive("errmsg")),],
				T.p["Thanks."],
			]])


class VOTableResponse(ServiceResource):
	"""is a renderer for queries for VOTables.  
	
	It's not immediately suitable for "real" VO services since it will return
	HTML error pages and re-display forms if their values don't validate.

	An example for a "real" VO service is siapservice.SiapService.
	"""
	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		if data.queryMeta.get("Overflow"):
			fName = "truncated_votable.xml"
		else:
			fName = "votable.xml"
		request.setHeader("content-type", "application/x-votable")
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%fName)
		return streaming.streamVOTable(request, data)

	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["VOTable generation failed"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["VOTable generation failed"],
				T.p["We're sorry, but there was an error on our side"
					" while generating the VOTable.  We would be very grateful"
					" if you could report this error, together with the"
					" URL you used and the following message to"
					" gavo@ari.uni-heidelberg.de: ",
					T.tt(render=T.directive("errmsg")),],
				T.p["Thanks -- meanwhile, chances are we'll render your"
					' VOTable all right if you check "human readable" under'
					' "Output Format".']],
			])


tag_embed = T.Proto("embed")
tag_noembed = T.Proto("noembed")


class VOPlotResponse(ServiceResource):
	"""returns a page embedding the VOPlot applet.
	"""
	def renderHTTP(self, ctx):
		return rend.Page.renderHTTP(self, ctx)

	def render_voplotArea(self, ctx, data):
		request = inevow.IRequest(ctx)
		parameters = request.args.copy()
		parameters[formal.FORMS_KEY] = "genForm"
		parameters["_FORMAT"]=["VOTable"]
		parameters["_TDENC"]=["True"]
		return ctx.tag[tag_embed(type = "application/x-java-applet",
				code="com.jvt.applets.PlotVOApplet",
				codebase=base.getConfig("web", "voplotCodebase"),
				votablepath=urlparse.urljoin(base.getConfig("web", "serverURL"),
					request.path)+"?",
				userguideURL=base.getConfig("web", "voplotUserman"),
				archive="voplot.jar",
				width="850",
				height="650",
				parameters=urllib.urlencode(parameters, doseq=True),
				MAYSCRIPT="true",
				background="#faf0e6",
				scriptable="true",
				pluginspage="http://java.sun.com/products/plugin/1.3.1/"
					"plugin-install.html")[
					tag_noembed["You need proper Java support for VOPlot"]]]

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


# pyfits obviously is not thread-safe.  We put a mutex around it
# and hope we'll be fine.
_fitsTableMutex = mutex.mutex()

class FITSTableResponse(ServiceResource):
	"""is a resource turning the data into a FITS binary table.
	"""
	def generateFile(self, request):
		while not _fitsTableMutex.testandset():
			time.sleep(0.1)
		try:
			res = fitstable.makeFITSTableFile(self.svcResult.original)
		finally:
			_fitsTableMutex.unlock()
		return res
	
	def getTargetName(self):
		if self.svcResult.queryMeta.get("Overflow"):
			return "truncated_data.fits", "application/x-fits"
		else:
			return "data.fits", "application/x-fits"

	def _formatOutput(self, data, ctx):
		self.svcResult = data
		request = inevow.IRequest(ctx)
		return threads.deferToThread(self.generateFile, request
			).addCallback(self._serveFile, request)

	def _serveFile(self, filePath, request):
		name, mime = self.getTargetName()
		request.setHeader("content-type", mime)
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%name)
		static.FileTransfer(open(filePath), os.path.getsize(filePath),
			request)
		os.unlink(filePath)
		return request.deferred

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


class TextResponse(ServiceResource):
	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		content = texttable.getAsText(data.original)
		request.setHeader('content-disposition', 
			'attachment; filename=table.tsv')
		request.setHeader("content-type", "text/tab-separated-values")
		request.setHeader("content-length", len(content))
		request.write(content)
		return ""

	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["Text table generation failed"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["Text table generation failed"],
				T.p["We're sorry, but there was an error while rendering the"
					" text table."
					" You're welcome to report this failure, but, frankly,"
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


class TarResponse(ServiceResource):
	"""delivers a tar of products requested.
	"""
	def _formatOutput(self, data, ctx):
		queryMeta = data.queryMeta
		request = inevow.IRequest(ctx)
		return producttar.getTarMaker().deliverProductTar(data, request, queryMeta)
			

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


class FormMixin(formal.ResourceMixin, object):
	"""is a mixin to produce input forms for services and display
	errors within these forms.
	"""
	# used for error display on form-less pages
	errorFactory = common.doctypedStan(T.html[
			T.head[
				T.title["Error in service parameters"],
				T.invisible(render=T.directive("commonhead")),
			],
			T.body[
				T.h1["Error in Service Parameters"],
				T.p["Something went wrong in processing your (probably implicit,"
					" since you are seeing this rather than a note in an input"
					" form) input."],
				T.p["The system claims the following went wrong:"],
				T.p(style="text-align: center")[
					T.tt(render=T.directive("errmsg")),],
				T.p["You may want to report this to gavo@ari.uni-heidelberg.de."],
			]])

	def _handleInputErrors(self, failure, ctx):
		"""goes as an errback to form handling code to allow correction form
		rendering at later stages than validation.
		"""
		if not hasattr(self, "form"): # no reporting in form possible
			if isinstance(failure.value, base.ValidationError):
				return grend.ErrorPage(failure, docFactory=self.errorFactory)
			raise failure.value
		if isinstance(failure.value, formal.FormError):
			self.form.errors.add(failure.value)
		elif isinstance(failure.value, base.ValidationError) and isinstance(
				failure.value.colName, basestring):
			try:
				# Find out the formal name of the failing field...
				failedField = self.translateFieldName(failure.value.colName)
				# ...and make sure it exists
				self.form.items.getItemByName(failedField)
				self.form.errors.add(formal.FieldValidationError(
					str(failure.getErrorMessage()), failedField))
			except KeyError: # Failing field cannot be determined
				self.form.errors.add(formal.FormError("Problem with input"
					" in the internal or generated field '%s': %s"%(
						failure.value.colName, failure.getErrorMessage())))
		else:
			failure.printTraceback()
			return failure
		return self.form.errors

	def translateFieldName(self, name):
		return self.service.translateFieldName(name)

	def _addInputKey(self, form, inputKey, data):
		"""adds a form field for an inputKey to the form.
		"""
		unit = ""
		if inputKey.type!="date":  # Sigh.
			unit = inputKey.inputUnit or inputKey.unit or ""
			if unit:
				unit = " [%s]"%unit
		label = inputKey.tablehead
		form.addField(inputKey.name,
			inputKey.getCurrentFormalType(),
			inputKey.getCurrentWidgetFactory(),
			label=label+unit,
			description=inputKey.description)

	def _addFromInputKey(self, inputKey, form, data):
		self._addInputKey(form, inputKey, data)
		if data and data.has_key(inputKey.name):
			form.data[inputKey.name] = data[inputKey.name]
		elif inputKey.values and inputKey.values.default:
			form.data[inputKey.name] = inputKey.values.default

	def _addQueryFields(self, form, data):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		for inputKey in self.getInputFields(self.service):
			self._addFromInputKey(inputKey, form, data)

	def _fakeDefaults(self, form, ctx):
		"""adds keys not yet in form.data but present in ctx to form.data.

		The idea here is that you can bookmark template forms.  The
		values in the bookmark are not normally picked up by formal
		since _processForm doesn't run.
		"""
		for key, val in inevow.IRequest(ctx).args.iteritems():
			if key not in form.data:
				form.data[key] = val

	def _addMetaFields(self, form, queryMeta, data):
		"""adds fields to choose output properties to form.
		"""
		for serviceKey in self.service.serviceKeys:
			self._addFromInputKey(serviceKey, form, data)
		try:
			if self.service.core.wantsTableWidget():
				form.addField("_DBOPTIONS", svcs.FormalDict,
					formal.widgetFactory(svcs.DBOptions, self.service, queryMeta),
					label="Table")
		except AttributeError: # probably no wantsTableWidget method on core
			pass

	def _getFormLinks(self):
		"""returns stan for widgets building GET-type strings for the current 
		form content.
		"""
		return T.div(class_="formLinks")[
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"],
				" ",
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeBookmarkLink(getEnclosingForm(this))")[
					T.img(src=base.makeSitePath("/static/img/bookmark.png"), 
						class_="silentlink", title="Link to this form", alt="[bookmark]")
				],
			]

	def form_genForm(self, ctx=None, data=None):
		queryMeta = svcs.QueryMeta.fromContext(ctx)
		if data is None and ctx is not None:
			data = dict((k,v[0]) for k,v in inevow.IRequest(ctx).args.iteritems())
		form = formal.Form()
		self._addQueryFields(form, data)
		self._addMetaFields(form, queryMeta, data)
		self._fakeDefaults(form, ctx)
		if self.name=="form":
			form.addField("_OUTPUT", formal.String, 
				formal.widgetFactory(svcs.OutputFormat, self.service, queryMeta),
				label="Output format")
		form.addAction(self.submitAction, label="Go")
		form.actionMaterial = self._getFormLinks()
		self.form = form
		return form


class Form(FormMixin, grend.ServiceBasedRenderer, grend.HTMLResultRenderMixin):
	"""is a page that provides a search form for the selected service
	and doubles as render page for HTML tables.

	In partiular, it will dispatch the various output formats defined
	through svcs.

	It also does error reporting as long as that is possible within
	the form.
	"""
	name = "form"
	runOnEmptyInputs = False

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		if "form" in self.service.templates:
			self.customTemplate = self.service.templates["form"]

		# enable special handling if I'm rendering fixed-behaviour services
		# (i.e., ones that never have inputs)
		if not self.getInputFields(self.service):
			self.runOnEmptyInputs = True
		self.queryResult = None

	@classmethod
	def isBrowseable(self, service):
		return True

	@classmethod
	def isCacheable(self, segments, request):
		return segments==()

	def renderHTTP(self, ctx):
		if self.runOnEmptyInputs:
			inevow.IRequest(ctx).args[form.FORMS_KEY] = ["genForm"]
		res = defer.maybeDeferred(
			super(Form, self).renderHTTP, ctx)
		return res

	knownResultPages = {
		"TSV": TextResponse,
		"VOTable": VOTableResponse,
		"VOPlot": VOPlotResponse,
		"FITS": FITSTableResponse,
		"tar": TarResponse,
		"HTML": None,
	}

	def _getResource(self, outputName):
		"""returns a nevow Resource subclass that produces outputName
		documents.
		"""
		try:
			return self.knownResultPages[outputName]
		except KeyError:
			raise base.ui.logOldExc(
				base.ValidationError("Invalid output format: %s"%outputName,
					colName="_OUTPUT"))

	def _realSubmitAction(self, ctx, form, data):
		"""is a helper for submitAction that does the real work.

		It is here so we can add an error handler in submitAction.
		"""
		try:
			queryMeta = svcs.QueryMeta.fromContext(ctx)
			queryMeta["formal_data"] = data
			if (self.service.core.outputTable.columns and 
					not self.service.getCurOutputFields(queryMeta)):
				raise base.ValidationError("These output settings yield no"
					" output fields", "_OUTPUT")
			managingResource = self._getResource(queryMeta["format"])
		except:
			return defer.fail()
		if managingResource is None:  # render result inline
			return self.runService(data, queryMeta
				).addCallback(self._formatOutput, ctx)
		else:
			return defer.succeed(managingResource(ctx, self.service, data))

	def submitAction(self, ctx, form, data):
		"""is called by formal when input arguments indicate the service should
		run.

		This happens either when the service takes no input data or when
		the sentinel argument of the form is present.

		The method returns a deferred resource.
		"""
		return self._realSubmitAction(ctx, form, data
			).addErrback(self._handleInputErrors, ctx)

	def _formatOutput(self, res, ctx):
		self.result = res
		request = inevow.IRequest(ctx)
		def finisher(result):
			return util.maybeDeferred(request.finishRequest, False
				).addCallback(lambda r: result)
		if "response" in self.service.templates:
			doc = self.service.templates["response"]
		else:
			doc = self.docFactory.load(ctx)
		self.rememberStuff(ctx)
		ctx =  context.WovenContext(ctx, T.invisible[doc])
		return self.flattenFactory(doc, ctx, request.write, finisher)

	defaultDocFactory = svcs.loadSystemTemplate("defaultresponse.html")

svcs.registerRenderer(Form)


class FeedbackForm(Form):
	"""is a page that renders a form with vexprs filled in of a feedback 
	query.

	Basically, you give items in feedbackSelect arguments which
	are directly parsed into a DataSet's columns.  With these, a
	FeedbackCore is directly called (i.e., not through the service,
	since that would expect very different arguments).

	The FeedbackCore returns a data set that only has a document
	row containing vizier expressions for the ranges of the input
	parameter of the data set given in the feedbackSelect items.

	Only then is the real Form processing started.	I'll admit this
	is a funky renderer.

	This only works on DbBasedCores (and doesn't make sense otherwise).
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		# If no feedbackSelect is present, it's the feedback search or
		# the user has not selected feedback items
		if not "feedbackSelect" in request.args:
			return Form(ctx, self.service)
		# Make a feedback service on the service unless one exists.
		if not hasattr(self.service, "feedbackService"):
			self.service.feedbackService = svcs.FeedbackService.fromService(
				self.service)
		data = request.args
		return self.runServiceWithContext(data, ctx
			).addCallback(self._buildForm, request, ctx)

	def processData(self, rawData, queryMeta):
		inputData = self.service.feedbackService.makeDataFor(self, rawData)
		return self.service.feedbackService.runWithData(inputData, queryMeta)

	def _buildForm(self, feedbackExprs, request, ctx):
		request.args = feedbackExprs.original
		return Form(ctx, self.service)

svcs.registerRenderer(FeedbackForm)


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
	except SyntaxError, ex:
		raise base.ui.logOldExc(base.BadCode(code, "core renderer", ex))
	return ns["renderForNevow"]


class StaticRenderer(FormMixin, grend.ServiceBasedRenderer):
	"""is a renderer that just hands through files.

	The standard operation here is to set a staticData property pointing
	to a resdir-relative directory used to serve files for.  Indices
	for directories are created.

	You can define a root resource by giving an indexFile property on
	the service.
	"""
	name = "static"

	def __init__(self, ctx, service):
		try:
			self.indexFile = os.path.join(service.rd.resdir, 
				service.getProperty("indexFile"))
		except KeyError:
			self.indexFile = None
		try:
			self.staticPath = os.path.join(service.rd.resdir, 
				service.getProperty("staticData"))
		except KeyError:
			self.staticPath = None

	@classmethod
	def isBrowseable(self, service):
		return service.getProperty("indexFile", None) 

	def renderHTTP(self, ctx):
		if inevow.ICurrentSegments(ctx)[-1]!='':
			# force a trailing slash on the "index"
			request = inevow.IRequest(ctx)
			request.redirect(request.URLPath().child(''))
			return ''
		if self.indexFile:
			return static.File(self.indexFile)
		else:
			raise svcs.UnknownURI("No matching resource")
	
	def locateChild(self, ctx, segments):
		if segments==('',) and self.indexFile:
			return self, ()
		elif self.staticPath is None:
			raise svcs.ForbiddenURI("No static data on this service") 
		else:
			if segments[-1]=="static": # no trailing slash given
				segments = ()            # -- swallow the segment
			return static.File(self.staticPath), segments

svcs.registerRenderer(StaticRenderer)


class FixedPageRenderer(grend.ServiceBasedRenderer):
	"""A renderer that always returns a single file.

	The file is given in the service's fixed template.
	"""
	name = "fixed"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		self.customTemplate = None
		try:
			self.customTemplate = self.service.templates["fixed"]
		except KeyError:
			raise base.ui.logOldExc(
				svcs.UnknownURI("fixed renderer needs a 'fixed' template"))

	@classmethod
	def isCacheable(cls, segments, request):
		return True
	
	@classmethod
	def isBrowseable(self, service):
		return True

svcs.registerRenderer(FixedPageRenderer)


class TextRenderer(grend.ServiceBasedRenderer):
	"""is a renderer that runs the service, expects back a string and
	displays that as text/plain.

	I don't think this is useful, but it's convenient for tests.
	"""
	name = "text"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
	
	def renderHTTP(self, ctx):
		d = self.runServiceWithContext(inevow.IRequest(ctx).args, ctx
			).addCallback(self._runService, queryMeta, ctx
			).addCallback(self._doRender, ctx)
		return d

	def _doRender(self, coreOutput, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/plain")
		request.write(str(coreOutput.original))
		return request.finishRequest(False) or ""
	

class CustomRenderer(grend.ServiceBasedRenderer):
	"""is a wrapper for user-defined renderers.

	The services defining this must have a customPage field. 
	It must be a tuple (page, (name, file, pathname, descr)), where page is
	a nevow resource constructible like a renderer (i.e., receiving a
	context and a service).  They will, in general, have locateChild
	overridden.

	(name, file, pathname, descr) is the result of load_module and is used
	in the special child "_reload" that will cause a reload of the
	underlying module and an assignment of its MainPage to realPage
	(like importparser does on the first import).
	"""
	name = "custom"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		if not self.service.customPage:
			raise svcs.UnknownURI("No custom page defined for this service.")
		pageClass, self.reloadInfo = service.customPageCode
		self.realPage = pageClass(ctx, service)

	@classmethod
	def isBrowseable(self, service):
		return True  # this may be somewhat broad.

	def _reload(self, ctx):
		mod = imp.load_module(*self.reloadInfo)
		pageClass = mod.MainPage
		self.service.customPageCode = (pageClass, self.reloadInfo)
		return url.here.curdir()

	def renderHTTP(self, ctx):
		return self.realPage.renderHTTP(ctx)
	
	def locateChild(self, ctx, segments):
		if segments and segments[0]=="_reload":
			return common.runAuthenticated(ctx, "", self._reload, ctx), ()
		return self.realPage.locateChild(ctx, segments)

svcs.registerRenderer(CustomRenderer)
