"""
A renderer for TAP, both sync and async.
"""

import traceback

from nevow import inevow
from nevow import rend
from twisted.internet import threads

from gavo import base
from gavo import svcs
from gavo.protocols import taprunner
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
			taprunner.writeResultTo(format, res, outputFile)

		request = inevow.IRequest(ctx)
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
					res = getAsyncResource(ctx, segments[1:])
				else:
					res = None
				return res, ()
		except base.Error, ex:
			traceback.print_exc()
			return ErrorResource(str(ex))
		raise UnknownURI("Bad TAP path %s"%"/".join(segments))

svcs.registerRenderer(TAPRenderer)
