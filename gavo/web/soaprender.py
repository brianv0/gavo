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
	def __init__(self, ctx, service):
		self.ctx, self.service = ctx, service
		soap.SOAPPublisher.__init__(self)

	def _cbGotResult(self, result):
# We want SOAP docs that actually match what we advertize in the WSDL.
# So, I override SOAPPublisher's haphazard SOAP formatter.
		return wsdl.serializePrimaryTable(result, self.service)

	def soap_useService(self, *args):
		try:
			inputPars = dict(zip(
				[f.get_dest() for f in self.service.getInputFields()],
				args))
			return self._runService(self.service.getInputData(inputPars), 
				self.ctx)
		except:
			traceback.print_exc()
			raise

	def _runService(self, inputData, ctx):
		queryMeta = common.QueryMeta(ctx)
		return defer.maybeDeferred(self.service.run, inputData, queryMeta
			).addCallback(self._extractResult, ctx
			).addErrback(self._handleErrors, ctx)
	
	def _extractResult(self, coreResult, ctx):
		return coreResult.original.getPrimaryTable().rows
	
	def _handleErrors(self, failure, ctx):
		failure.printTraceback()
		return failure


class SoapRenderer(resourcebased.ServiceBasedRenderer):
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
