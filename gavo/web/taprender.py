"""
A renderer for TAP, both sync and async.
"""

from __future__ import with_statement

import os
import traceback

from nevow import inevow
from nevow import rend
from nevow import url
from nevow import util
from twisted.internet import threads
from twisted.python import log

from gavo import base
from gavo import formats
from gavo import svcs
from gavo import utils
from gavo.protocols import tap
from gavo.protocols import taprunner
from gavo.protocols import uws
from gavo.protocols import uwsactions
from gavo.web import common
from gavo.web import grend
from gavo.web import streaming
from gavo.web import vosi
from gavo.votable import V


@utils.memoized
def getTAPVersion():
	return base.caches.getRD(tap.RD_ID).getProperty("TAP_VERSION")


class ErrorResource(rend.Page):
	def __init__(self, errMsg, exc=None):
		self.errMsg = errMsg
		self.hint = getattr(exc, "hint", None)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		request.setResponseCode(400)  # make some informed choice here?
		doc = V.VOTABLE[
			V.INFO(name="QUERY_STATUS", value="ERROR")[
					self.errMsg]]
		if self.hint:
			doc[V.INFO(name="HINT", value="HINT")[
				self.hint]]
		return doc.render()


class UWSRedirect(rend.Page):
	"""a redirection for UWS (i.e., 303).

	The DC-global redirects use a 302 status, munge redirection URLs, and 
	we don't want any HTML payload here anyway.

	The locactions used here are relative to the tap-renderer's URL
	(i.e., async/ points to the async root).
	"""
	def __init__(self, location):
		self.location = str(
			"%s/%s"%(self.getServiceURL(), location))

	@utils.memoized
	def getServiceURL(self):
		return base.caches.getRD(tap.RD_ID).getById("run").getURL("tap")

	def renderHTTP(self, ctx):
		req = inevow.IRequest(ctx)
		req.code = 303
		req.setHeader("location", self.location)
		req.setHeader("content-type", "text/plain")
		req.write("Go here: %s\n"%self.location)
		return ""


class TAPQueryResource(rend.Page):
	"""the resource executing sync TAP queries.

	While not really going through UWS, this does create a UWS job and
	tears it down later.
	"""
	def _doRender(self, ctx):
		with tap.TAPJob.createFromRequest(inevow.IRequest(ctx)) as job:
			parameters = job.parameters
			job.executionduration = base.getConfig("async", "defaultExecTimeSync")
			jobId = job.jobId
		taprunner.runTAPJob(parameters, jobId)
		with tap.TAPJob.makeFromId(jobId) as job:
			if job.phase==uws.COMPLETED:
				# This is TAP, so there's exactly one result
				res = job.getResults()[0]
				name, type = res["resultName"], res["resultType"]
				# hold on to the result fd so its inode is not lost when we delete
				# the job.
				f = open(os.path.join(job.getWD(), name))
				job.delete()
				return (f, type)
			elif job.phase==uws.ERROR:
				exc = job.getError()
				job.delete()
				raise exc
			elif job.phase==uws.ABORTED:
				job.delete()
				raise uws.UWSError("Job was manually aborted.  For synchronous"
					" jobs, this probably means the operators killed it.",
					jobId)
			else:
				job.delete()
				raise uws.UWSError("Internal error.  Invalid UWS phase.")

	def renderHTTP(self, ctx):
		try:
			return threads.deferToThread(self._doRender, ctx
				).addCallback(self._formatResult, ctx
				).addErrback(self._formatError)
		except base.Error, ex:
			return base.ui.logOldExc(ErrorResource(unicode(ex), ex))

	def _formatError(self, failure):
		failure.printTraceback()
		return ErrorResource(failure.getErrorMessage(), failure.value)

	def _formatResult(self, res, ctx):
		request = inevow.IRequest(ctx)
		f, type = res

		def writeTable(outputFile):
			utils.cat(f, outputFile)

		request.setHeader("content-type", type)
		# if request has an accumulator, we're testing.
		if hasattr(request, "accumulator"):
			writeTable(request)
			return ""
		else:
			return streaming.streamOut(writeTable, request)


def getSyncResource(ctx, service, segments):
	if segments:
		raise svcs.UnknownURI("No resources below sync")
	request = common.getfirst(ctx, "REQUEST", base.Undefined)
	if request=="doQuery":
		return TAPQueryResource(service, ctx)
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
		failure.printTraceback()
		request.setHeader("content-type", "text/xml")
		return ErrorResource(failure.getErrorMessage(), failure.value)


class JoblistResource(MethodAwareResource, UWSErrorMixin):
	"""The web resource corresponding to async root.

	GET yields a job list, POST creates a job.
	"""
	def _doGET(self, ctx, request):
		res = uwsactions.getJobList()
		return res
	
	def _doPOST(self, ctx, request):
		with tap.TAPJob.createFromRequest(request) as job:
			jobId = job.jobId
		return UWSRedirect("async/%s"%jobId)

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
		).addErrback(self._redirectAsNecessary, ctx
		).addErrback(self._deliverError, request)

	def _redirectAsNecessary(self, failure, ctx):
		failure.trap(svcs.WebRedirect)
		return UWSRedirect(failure.value.rawDest)

	def _deliverResult(self, result, request):
		if hasattr(result, "renderHTTP"):  # it's a finished resource
			return result
		request.setHeader("content-type", "text/xml")
		request.write(utils.xmlrender(result).encode("utf-8"))
		return ""
	

def getAsyncResource(ctx, service, segments):
	if segments:
		return JobResource(service, segments)
	else:
		return JoblistResource(service)


# Sadly, TAP protocol keys need to be case insensitive (2.3.10)
# In general, this is, of course, an extremely unwelcome feature,
# so we restrict it to the keys specified in the TAP spec.
_caseInsensitiveKeys = set(["REQUEST", "VERSION", "LANG", "QUERY", 
	"FORMAT", "MAXREC", "RUNID", "UPLOAD"])

def reparseRequestArgs(ctx):
	"""adds attributes scalars and files to ctx's request.

	Scalars contains non-field arguments, files the files.  Both are
	dictionaries containing the first item found for a key.
	"""
	request = inevow.IRequest(ctx)
	request.scalars, request.files = {}, {}
	if request.fields:
		for key in request.fields:
			field = request.fields[key]
			if field.filename:
				request.files[key] = field
			else:
				if key.upper() in _caseInsensitiveKeys:
					key = key.upper()
				request.scalars[key] = request.fields.getfirst(key)


class TAPRenderer(grend.ServiceBasedRenderer):
	"""A renderer for the synchronous version of TAP.

	Basically, this just dispatches to the sync and async resources.
	"""
	name = "tap"

	def renderHTTP(self, ctx):
		# we *could* have some nice intro here, but really -- let's just
		# redirect to info and save some work, ok?
		raise svcs.WebRedirect(self.service.getURL("info", absolute=False))

	def locateChild(self, ctx, segments):
		if not segments[-1]: # trailing slashes are forbidden here
			if len(segments)==1: # root resource; don't redirect, it would be a loop
				return self, ()
			raise svcs.WebRedirect(
				self.service.getURL("tap")+"/"+"/".join(segments[:-1]))
		reparseRequestArgs(ctx)
		request = inevow.IRequest(ctx)
		try:
			if "VERSION" in request.scalars:
				if request.scalars["VERSION"]!=getTAPVersion():
					return ErrorResource("Version mismatch; this service only supports"
						" TAP version %s."%getTAPVersion()), ()
			if segments:
				if segments[0]=='sync':
					res = getSyncResource(ctx, self.service, segments[1:])
				elif segments[0]=='async':
					res = getAsyncResource(ctx, self.service, segments[1:])
				elif segments[0]=='availability':
					res = vosi.VOSIAvailabilityRenderer(ctx, self.service)
				elif segments[0]=='capabilities':
					res = vosi.VOSICapabilityRenderer(ctx, self.service)
				elif segments[0]=='tables':
					res = vosi.VOSITablesetRenderer(ctx, self.service)
				else:
					raise svcs.UnknownURI("Bad TAP path %s"%"/".join(segments))
				return res, ()
		except svcs.UnknownURI:
			raise
		except base.Error, ex:
			# see flagError in protocols.uws for the reason for the next if
			if not isinstance(exception, base.ValidationError):
				base.ui.notifyErrorOccurred("TAP error")
			return ErrorResource(str(ex), ex), ()
		raise common.UnknownURI("Bad TAP path %s"%"/".join(segments))

svcs.registerRenderer(TAPRenderer)
