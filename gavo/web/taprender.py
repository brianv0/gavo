"""
A renderer for TAP, both sync and async.
"""

from __future__ import with_statement

import traceback

from nevow import inevow
from nevow import rend
from nevow import url
from nevow import util
from twisted.internet import threads

from gavo import base
from gavo import formats
from gavo import svcs
from gavo.protocols import taprunner
from gavo.protocols import uws
from gavo.protocols import uwsactions
from gavo.web import common
from gavo.web import grend
from gavo.web import streaming
from gavo.web import vosi
from gavo.web import weberrors
from gavo.votable import V


TAP_VERSION = "1.0"


class ErrorResource(rend.Page):
	def __init__(self, errMsg):
		self.errMsg = errMsg

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		doc = V.VOTABLE[
			V.INFO(name="QUERY_STATUS", value="ERROR")[
					self.errMsg]]
		return doc.render()


class TAPQueryResource(rend.Page):
	"""the resource executing sync TAP queries.
	"""
	def _doRender(self, ctx):
		format = taprunner.normalizeTAPFormat(
			common.getfirst(ctx, 'FORMAT', 'votable'))
		formats.checkFormatIsValid(format)
		query = common.getfirst(ctx, 'QUERY', base.Undefined)
		return threads.deferToThread(taprunner.runTAPQuery,
			query, 5, 'untrustedquery'
			).addCallback(self._format, format, ctx)

	def renderHTTP(self, ctx):
		try:
			return self._doRender(ctx
				).addErrback(self._formatError)
		except base.Error, ex:
			return ErrorResource(unicode(ex))

	def _formatError(self, failure):
		failure.printTraceback()
		return ErrorResource(failure.getErrorMessage())

	def _format(self, res, format, ctx):
		def writeTable(outputFile):
			return taprunner.writeResultTo(format, res, outputFile)

		request = inevow.IRequest(ctx)
		# if request has an accumulator, we're testing and don't stream
		if hasattr(request, "accumulator"):
			writeTable(request)
			return ""
		else:
			return streaming.streamOut(writeTable, request)


SUPPORTED_LANGS = {
	'ADQL': TAPQueryResource,
	'ADQL-2.0': TAPQueryResource,
}


def getQueryResource(service, ctx):
	lang = common.getfirst(ctx, 'LANG', None)
	try:
		generator = SUPPORTED_LANGS[lang]
	except KeyError:
		return ErrorResource("Unknown query language '%s'"%lang)
	return generator()


def getSyncResource(service, ctx, segments):
	if segments:
		return weberrors.NotFoundPage("No resources below sync")
	request = common.getfirst(ctx, "REQUEST", base.Undefined)
	if request=="doQuery":
		return getQueryResource(service, ctx)
	elif request=="getCapabilities":
		return vosi.VOSICapabilityRenderer(ctx, service)
	return ErrorResource("Invalid REQUEST: '%s'"%request)


class MethodAwareResource(rend.Page):
	"""is a rend.Page with behaviour depending on the HTTP method.
	"""
	def __init__(self, service):
		self.service = service
		rend.Page.__init__(self)

	def _doBADMETHOD(self, ctx, request):
		raise svcs.BadMethod(request.method)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		handlingMethod = getattr(self, "_do"+request.method, self._doBADMETHOD)
		return threads.deferToThread(handlingMethod, ctx, request
			).addCallback(self._deliverResult, request
			).addErrback(self._deliverError, request)


class UWSErrorMixin(object):
	def _deliverError(self, failure, request):
		request.setHeader("content-type", "text/xml")
		failure.printTraceback()
		return ""


class JoblistResource(MethodAwareResource, UWSErrorMixin):
	"""The web resource corresponding to async root.

	GET yields a job list, POST creates a job.
	"""
	def _doGET(self, ctx, request):
		return uwsactions.getJobList()
	
	def _doPOST(self, ctx, request):
		with uws.createFromRequest(request) as job:
			jobId = job.jobId
		return url.URL.fromString("%s/async/%s"%(
			self.service.getURL("tap"),
			jobId))

	def _deliverResult(self, res, request):
		request.setHeader("content-type", "text/xml")
		return res
	


class JobResource(rend.Page, UWSErrorMixin):
	"""The web resource corresponding to async requests for jobs.
	"""
	def __init__(self, service, segments):
		self.service, self.segments = service, segments

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		return threads.deferToThread(
			uwsactions.doJobAction, request, self.segments
		).addCallback(self._deliverResult, request
		).addErrback(self._redirectAsNecessary
		).addErrback(self._deliverError, request)

	def _redirectAsNecessary(self, failure):
		failure.trap(svcs.WebRedirect)
		return url.URL.fromString("%s/%s"%(
			self.service.getURL("tap"),
			failure.value.args[0]))

	def _deliverResult(self, result, request):
		request.setHeader("content-type", "text/xml")
		return result
	

def getAsyncResource(service, ctx, segments):
	if segments:
		return JobResource(service, segments)
	else:
		return JoblistResource(service)


class TAPRenderer(grend.ServiceBasedRenderer):
	"""A renderer for the synchronous version of TAP.

	Basically, this just dispatches to the sync and async resources.
	"""
	name = "tap"

	def _returnError(self, failure):
		failure.printTraceback()
		return ErrorResource(failure.getErrorMessage())

	def locateChild(self, ctx, segments):
		try:
			if common.getfirst(ctx, "VERSION", TAP_VERSION)!=TAP_VERSION:
				return ErrorResource("Version mismatch; this service only supports"
					" TAP version %s."%TAP_VERSION), ()
			if segments:
				if segments[0]=='sync':
					res = getSyncResource(self.service, ctx, segments[1:])
				elif segments[0]=='async':
					res = getAsyncResource(self.service, ctx, segments[1:])
				else:
					res = None
				return res, ()
		except base.Error, ex:
			traceback.print_exc()
			return ErrorResource(str(ex))
		raise UnknownURI("Bad TAP path %s"%"/".join(segments))

svcs.registerRenderer(TAPRenderer)
