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

import formal
from formal import form

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
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.formats import votable
from gavo.base import typesystems
from gavo.web import common
from gavo.web import htmltable
from gavo.web import grend
from gavo.web import producttar
from gavo.web import streaming
from gavo.web import weberrors

from gavo.svcs import Error, UnknownURI, ForbiddenURI


class ServiceResource(rend.Page):
	"""is a base class for resources answering form.

	They receive a service and the form data from formal.

	This whole interplay is governed by the form renderer below.

	Deriving classes should override 
	
	* _obtainOutput(ctx) -- returns the result of running the service 
		conditioned on the specific resource type; the default implementation 
		may do.  *Note*: _obtainOutput must return a deferred, whereas the
		standard service is synchronous.
	* _formatOutput(result, ctx) -- receives the result of _obtainOutput
	  and has to do the formatting
	* _handleOtherErrors(failure, ctx) -- is called when an exception
	  occurs that cannot be displayed in a form.  The default implementation
		delivers a page built from stan in the errorFactory class attribute,
		using grend.ErrorPage as renderer.
	"""
	name = "form"
	def __init__(self, service, formalData):
		rend.Page.__init__(self)
		self.service, self.formalData = service, formalData

	def renderHTTP(self, ctx):
		return self._obtainOutput(ctx
			).addCallback(self._formatOutput, ctx
			).addErrback(self._handleOtherErrors, ctx)

	def _obtainOutput(self, ctx):
		return threads.deferToThread(self.service.runFromContext, 
			self.formalData, ctx)

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


def streamVOTable(request, data):
	"""streams out the payload of an SvcResult as a VOTable.
	"""
	def writeVOTable(outputFile):
		"""writes a VOTable representation of the SvcResult instance data
		to request.
		"""
		try:
			tableMaker = votable.VOTableMaker({
				True: "td",
				False: "binary"}[data.queryMeta["tdEnc"]])
			vot = tableMaker.makeVOT(data.original)
			tableMaker.writeVOT(vot, outputFile)
		except:
			sys.stderr.write("Yikes -- error during VOTable render:\n")
			traceback.print_exc()
			outputFile.write(">>>> INTERNAL ERROR, INVALID OUTPUT <<<<")
			return ""
	return streaming.streamOut(writeVOTable, request)


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
		return streamVOTable(request, data)

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


class VOPlotResponse(ServiceResource, grend.GavoRenderMixin):
	"""returns a page embedding the VOPlot applet.
	"""
	def renderHTTP(self, ctx):
		return rend.Page.renderHTTP(self, ctx)

	def render_voplotArea(self, ctx, data):
		request = inevow.IRequest(ctx)
		parameters = request.args.copy()
		parameters["_FORMAT"]=["VOTable"]
		parameters["_TDENC"]=["True"]
		return ctx.tag[tag_embed(type = "application/x-java-applet",
				code="com.jvt.applets.PlotVOApplet",
				codebase=base.getConfig("web", "voplotCodebase"),
				votablepath=urlparse.urljoin(base.getConfig("web", "serverURL"),
					request.path),
				userguideURL=base.getConfig("web", "voplotUserman"),
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
						"."]]]

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
		request.setHeader("content-type", "text/plain")
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
				failure.printTraceback()
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
			inputKey.formalType,
			inputKey.widgetFactory,
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
		for inputKey in self.service.getInputFields():
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
		if (isinstance(self.service.core, svcs.DBCore) and
				self.service.core.wantsTableWidget()):
			form.addField("_DBOPTIONS", svcs.FormalDict,
				formal.widgetFactory(svcs.DBOptions, self.service, queryMeta),
				label="Table")

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
		self.form = form
		return form


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


def _makeNoParsBehaviour(action):
	def b(self, ctx):
		# This function is monkeypatched into the resource.__behaviour if
		# the underlying service doesn't have any input parameters at all
		# to always run the defined query.  This is probably only interesting
		# for FixedQueryCores.
		formName = "genForm"
		request = inevow.IRequest(ctx)
		if "_noPars" in request.args:  # break infinite recursion
			return None
		request.args["_noPars"] = [True]
		self.remember(ctx)
		d = defer.succeed(ctx)
		d.addCallback(form.locateForm, formName)
		d.addCallback(self._processForm, ctx)
		return d
	return b


class HTMLResultRenderMixin(object):
	"""is a mixin with render functions for HTML tables and associated 
	metadata within other pages.

	This is primarily used for the Form renderer.
	"""
	result = None

	def render_resulttable(self, ctx, data):
		if hasattr(data, "child"):
			return htmltable.HTMLTableFragment(data.child(ctx, "table"), 
				data.queryMeta)
		else:
			# a FormError, most likely
			return ""

	def render_parpair(self, ctx, data):
		if data is None or data[1] is None or "__" in data[0]:
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
	
	def data_result(self, ctx, data):
		return self.result


class Form(FormMixin, grend.ServiceBasedRenderer, HTMLResultRenderMixin):
	"""is a page that provides a search form for the selected service
	and doubles as render page for HTML tables.

	In partiular, it will dispatch the various output formats defined
	through svcs.

	It also does error reporting as long as that is possible within
	the form.
	"""
	name = "form"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		if "form" in self.service.templates:
			self.customTemplate = os.path.join(self.rd.resdir,
				self.service.templates["form"])
		# A service with no inputs will be run even if no form data
		# can be located:
		if self.service.getInputFields():
			self._ResourceMixin__behaviour().renderHTTP = new.instancemethod(
				_formBehaviour_renderHTTP, self._ResourceMixin__behaviour(),
				form.FormsResourceBehaviour)
		else:
			self._ResourceMixin__behaviour().renderHTTP = new.instancemethod(
				_makeNoParsBehaviour(self.submitAction), 
				self._ResourceMixin__behaviour(), form.FormsResourceBehaviour)
		self.queryResult = None

	def renderHTTP(self, ctx):
		res = defer.maybeDeferred(
			super(Form, self).renderHTTP, ctx)
		res.addErrback(self._crashAndBurn, ctx)
		return res

	def _crashAndBurn(self, failure, ctx):
		"""is called on errors nobody else cared to handle.
		"""

		res = weberrors.ErrorPage()
		return res.renderHTTP_exception(ctx, failure)

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
			raise base.ValidationError("Invalid output format: %s"%outputName,
				colName="_OUTPUT")

	def _runService(self, data, ctx):
		return threads.deferToThread(self.service.runFromContext, data, ctx
			).addCallback(self._formatOutput, ctx)

	def _realSubmitAction(self, ctx, form, data):
		"""is a helper for submitAction that does the real work.

		It is here so we can add an error handler in submitAction.
		"""
		try:
			queryMeta = svcs.QueryMeta.fromContext(ctx)
			if (self.service.core.outputTable.columns and 
					not self.service.getCurOutputFields(queryMeta)):
				raise base.ValidationError("These output settings yield no"
					" output fields", "_OUTPUT")
			managingResource = self._getResource(queryMeta["format"])
		except:
			return defer.fail()
		if managingResource is None:  # render result inline
			return self._runService(data, ctx)
		else:
			return defer.succeed(managingResource(self.service, data))

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

	def process(self, ctx):
		return super(Form, self).process(ctx)

	defaultDocFactory = common.doctypedStan(T.html[
		T.head(render=T.directive("commonhead"))[
			T.title(render=T.directive("meta"))["title"],
		],
		T.body(render=T.directive("withsidebar"))[
			T.h1(render=T.directive("meta"))["title"],
			T.div(class_="result", render=T.directive("ifdata"), 
					data=T.directive("result")) [
				T.div(class_="querypars", data=T.directive("queryseq"),
						render=T.directive("ifdata"))[
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
					T.p(render=T.directive("ifdata"), data=T.slot(name="message"),
						class_="resultMessage")[
							T.invisible(render=T.directive("data"))
					],
				],
				T.p(class_="warning", render=T.directive("warnTrunc")),
				T.div(class_="result")[
					T.invisible(render=T.directive("resulttable")),
				],
				T.h2[T.a(name="_queryForm")["Query Form"]],
			],
			T.div(id="intro", render=T.directive("metahtml"), class_="intro")[
				"_intro"],
			T.invisible(render=T.directive("form genForm")),
			T.div(id="bottominfo", render=T.directive("metahtml"))["_bottominfo"],
			T.div(class_="copyright", render=T.directive("metahtml"))["_copyright"],
		]])

grend.registerRenderer("form", Form)


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
		return threads.deferToThread(self.service.feedbackService.runFromContext, 
			data, ctx).addCallback(self._buildForm, request, ctx)
	
	def _buildForm(self, feedbackExprs, request, ctx):
		request.args = feedbackExprs.original
		return Form(ctx, self.service)

grend.registerRenderer("feedback", FeedbackForm)


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


class StaticRenderer(FormMixin, grend.ServiceBasedRenderer):
	"""is a renderer that just hands through files.

	On this, you can have a template "static" or have a static core
	returning a table with with a column called "filename".  The
	file designated in the first row will be used as-is.

	Queries with remaining segments return files from the staticData
	directory of the service, if defined.
	"""
	name = "static"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		if not service.staticData:# XXX TODO: FORBIDDEN
			raise svcs.UnknownURI("No static data on this service") 
		if "static" in self.service.templates:
			self.customTemplate = self.service.templates["static"]
		self.basePath = os.path.join(service.rd.resdir,
			service.staticData)
		if self.basePath:
			self.rend = static.File(self.basePath)
	
	def renderHTTP(self, ctx):
		if inevow.ICurrentSegments(ctx)[-1] != '':
			request = inevow.IRequest(ctx)
			request.redirect(request.URLPath().child(''))
			return ''
		if self.customTemplate:
			return grend.ServiceBasedRenderer.renderHTTP(self, ctx)
		else:
			return self.service.run(None).addCallback(self._renderResultDoc, ctx)
	
	def _renderResultDoc(self, svcResult, ctx):
		rows = svcResult.original.getPrimaryTable().rows
		if len(rows)==0:
			raise svcs.UnknownURI("No matching resource")
		relativeName = rows[0]["filename"]
		return static.File(os.path.join(self.basePath, relativeName)
			).renderHTTP(ctx)

	def locateChild(self, ctx, segments):
		if segments==('',):
			return self, ()
		if self.basePath:
			return self.rend.locateChild(ctx, segments)
		return None, ()

grend.registerRenderer("static", StaticRenderer)


class TextRenderer(grend.ServiceBasedRenderer):
	"""is a renderer that runs the service, expects back a string and
	displays that as text/plain.

	I don't think the is useful, but it's convenient for tests.
	"""
	name = "text"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
	
	def renderHTTP(self, ctx):
		queryMeta = common.QueryMeta.fromContext(ctx)
		d = defer.maybeDeferred(self.service.getInputData, 
				inevow.IRequest(ctx).args
			).addCallback(self._runService, queryMeta, ctx)
		return d

	def _runService(self, inputData, queryMeta, ctx):
		return self.service.run(inputData, queryMeta
			).addCallback(self._doRender, ctx)
	
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

grend.registerRenderer("custom", CustomRenderer)
