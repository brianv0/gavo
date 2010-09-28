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
from gavo.base import typesystems
from gavo.web import common
from gavo.web import grend
from gavo.web import producttar
from gavo.web import serviceresults
from gavo.web import streaming

from gavo.svcs import Error, UnknownURI, ForbiddenURI


class Form(grend.FormMixin, 
		grend.CustomTemplateMixin,
		grend.HTMLResultRenderMixin, 
		grend.ServiceBasedPage):
	"""The "normal" renderer within DaCHS for web-facing services.

	It will display a form and allow outputs in various formats.

	It also does error reporting as long as that is possible within
	the form.
	"""
	name = "form"
	runOnEmptyInputs = False
	compute = True

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
		if "form" in self.service.templates:
			self.customTemplate = self.service.templates["form"]

		# enable special handling if I'm rendering fixed-behaviour services
		# (i.e., ones that never have inputs) XXX TODO: Figure out where I used this and fix that to use the fixed renderer (or whatever)
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
		return grend.FormMixin.renderHTTP(self, ctx)

	def _realSubmitAction(self, ctx, form, data):
		"""is a helper for submitAction that does the real work.

		It is here so we can add an error handler in submitAction.
		"""
		queryMeta = svcs.QueryMeta.fromContext(ctx)
		queryMeta["formal_data"] = data
		if (self.service.core.outputTable.columns and 
				not self.service.getCurOutputFields(queryMeta)):
			raise base.ValidationError("These output settings yield no"
				" output fields", "_OUTPUT")
		if queryMeta["format"]=="HTML":
			resultWriter = self
		else:
			resultWriter = serviceresults.getFormat(queryMeta["format"])
		if resultWriter.compute:
			d = self.runService(data, queryMeta)
		else:
			d = defer.succeed(None)
		return d.addCallback(resultWriter._formatOutput, ctx)

	def submitAction(self, ctx, form, data):
		"""is called by formal when input arguments indicate the service should
		run.

		This happens either when the service takes no input data or when
		the sentinel argument of the form is present.

		The method returns a deferred resource.
		"""
		return defer.maybeDeferred(self._realSubmitAction, ctx, form, data
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


class StaticRenderer(grend.FormMixin, grend.ServiceBasedPage):
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


class FixedPageRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A renderer that always returns a single file.

	The file is given in the service's fixed template.
	"""
	name = "fixed"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
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


class TextRenderer(grend.ServiceBasedPage):
	"""is a renderer that runs the service, expects back a string and
	displays that as text/plain.

	I don't think this is useful, but it's convenient for tests.
	"""
	name = "text"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
	
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
	

class CustomRenderer(grend.ServiceBasedPage):
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
		grend.ServiceBasedPage.__init__(self, ctx, service)
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
