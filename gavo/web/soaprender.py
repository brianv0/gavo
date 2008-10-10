"""
SOAP rendering and related classes.
"""

import traceback

from nevow import inevow

from twisted.internet import defer
from twisted.web import soap

from gavo.parsing import contextgrammar
from gavo.web import common
from gavo.web import resourcebased
from gavo.web import wsdl


class SOAPProcessor(soap.SOAPPublisher):
	"""is a helper to the SOAP renderer.

	It's actually a nevow resource ("page"), so whatever really has
	to do with SOAP (as opposed to returning WSDL) is done by this.
	"""
	def __init__(self, ctx, service):
		self.ctx, self.service = ctx, service
		self.request = inevow.IRequest(ctx)
		soap.SOAPPublisher.__init__(self)

	def _gotResult(self, result, request, methodName):
# We want SOAP docs that actually match what we advertize in the WSDL.
# So, I override SOAPPublisher's haphazard SOAPpy-based formatter.
		if result is None:  # Error has occurred.  This callback shouldn't be
			# called at all, but for some reason it is, and I can't be bothered
			# now to figure out why.
			return ""
		response = wsdl.serializePrimaryTable(result, self.service)
		self._sendResponse(request, response)
	
	def _gotError(self, failure, request, methodName):
		failure.printTraceback()
		try:
			self._sendResponse(request, 
				wsdl.formatFault(failure.value, self.service), status=500)
		except:
			traceback.print_exc()

	def soap_useService(self, *args):
		try:
			inputPars = dict(zip(
				[f.get_dest() for f in self.service.getInputFields()],
				args))
			return self._runService(self.service.getInputData(inputPars), 
				self.ctx)
		except Exception, exc:
			traceback.print_exc()
			return self._formatError(exc)

	def _formatError(self, exc):
		self._sendResponse(self.request, wsdl.formatFault(exc, self.service), 
			status=500)

	def _runService(self, inputData, ctx):
		queryMeta = common.QueryMeta(ctx)
		return defer.maybeDeferred(self.service.run, inputData, queryMeta)


class SoapRenderer(resourcebased.ServiceBasedRenderer):
	"""is a renderer that receives and formats SOAP messages.
	"""
	name="soap"
	def __init__(self, ctx, service):
		resourcebased.ServiceBasedRenderer.__init__(self, ctx, service)

	def renderHTTP(self, ctx):
		"""returns the WSDL for service.

		This is only called when there's a ?wsdl arg in the request,
		otherwise locateChild will return the SOAPProcessor.
		"""
		request = inevow.IRequest(ctx)
		if not hasattr(self.service, "_generatedWSDL"):
			queryMeta = common.QueryMeta(ctx)
			self.service._generatedWSDL = wsdl.makeSOAPWSDLForService(
				self.service, queryMeta).render()
		request.setHeader("content-type", "text/xml")
		return self.service._generatedWSDL

	def locateChild(self, ctx, segments):
		request = inevow.IRequest(ctx)
		if request.uri.endswith("?wsdl"): # XXX TODO: use parsed headers here
			return self, ()
		return SOAPProcessor(ctx, self.service), ()
