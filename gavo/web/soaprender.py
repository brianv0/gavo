"""
SOAP rendering and related classes.
"""

import traceback

from nevow import inevow

from twisted.web import soap

from gavo import base
from gavo import svcs
from gavo.web import grend
from gavo.web import wsdl


class SOAPProcessor(soap.SOAPPublisher):
	"""is a helper to the SOAP renderer.

	It's actually a nevow resource ("page"), so whatever really has
	to do with SOAP (as opposed to returning WSDL) is done by this.
	"""
	def __init__(self, ctx, service, runServiceFromArgs):
		self.ctx, self.service = ctx, service
		self.runServiceFromArgs = runServiceFromArgs
		soap.SOAPPublisher.__init__(self)

	def _gotResult(self, result, request, methodName):
# We want SOAP docs that actually match what we advertize in the WSDL.
# So, I override SOAPPublisher's haphazard SOAPpy-based formatter.
		if result is None:  # Error has occurred.  This callback shouldn't be
			# called at all, but for some reason it is, and I can't be bothered
			# now to figure out why.
			return ""
		response = wsdl.serializePrimaryTable(result.original, self.service)
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
			return self.runServiceFromArgs(self.ctx, args)
		except Exception, exc:
			traceback.print_exc()
			return self._formatError(exc)

	def _formatError(self, exc):
		request = inevow.IRequest(self.ctx)
		self._sendResponse(request, wsdl.formatFault(exc, self.service), 
			status=500)


class SoapRenderer(grend.ServiceBasedRenderer):
	"""is a renderer that receives and formats SOAP messages.
	"""
	name="soap"
	preferredMethod = "POST"
	urlUse = "full"
# XXX TODO: With the next VODataService, make this to:
	#urlUse = "post"

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)

	@classmethod
	def makeAccessURL(cls, baseURL):
		return baseURL+"/soap/go"
	
	def runServiceFromArgs(self, ctx, args):
		"""starts the service.

		This being called back from the SOAPProcessor, and args is the
		argument tuple as given from SOAP.
		"""
		inputPars = dict(zip(
			[f.name for f in self.getInputFields(self.service)],
			args))
		return self.runServiceWithContext(inputPars, ctx)

	def renderHTTP(self, ctx):
		"""returns the WSDL for service.

		This is only called when there's a ?wsdl arg in the request,
		otherwise locateChild will return the SOAPProcessor.
		"""
		request = inevow.IRequest(ctx)
		if not hasattr(self.service, "_generatedWSDL"):
			queryMeta = svcs.QueryMeta.fromContext(ctx)
			self.service._generatedWSDL = wsdl.makeSOAPWSDLForService(
				self.service, queryMeta).render()
		request.setHeader("content-type", "text/xml")
		return self.service._generatedWSDL

	def locateChild(self, ctx, segments):
		request = inevow.IRequest(ctx)
		if request.uri.endswith("?wsdl"): # XXX TODO: use parsed headers here
			return self, ()
		return SOAPProcessor(ctx, self.service, self.runServiceFromArgs), ()

svcs.registerRenderer("soap", SoapRenderer)
