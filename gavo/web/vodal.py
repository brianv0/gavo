"""
Support for IVOA DAL and registry protocols.
"""

from nevow import appserver
from nevow import inevow
from nevow import rend

from twisted.internet import defer
from twisted.internet import threads
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import meta
from gavo import ElementTree
from gavo import datadef
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.parsing import resource
from gavo.web import common
from gavo.web import registry
from gavo.web import resourcebased


class DalRenderer(common.CustomErrorMixin, resourcebased.Form):
	"""is a base class for renderers for the usual IVOA DAL protocols.

	The main difference to the standard VOTable renderer is the custom
	error reporting.  For this, the inheriting class has to define
	a method _makeErrorTable(ctx, errorMessage) that must return a CoreResult
	instance producing a VOTable according to specification.
	"""

	implements(inevow.ICanHandleException)

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		super(DalRenderer, self).__init__(ctx, *args, **kwargs)

	_generateForm = resourcebased.Form.form_genForm

	def _writeErrorTable(self, ctx, errmsg):
		result = self._makeErrorTable(ctx, errmsg)
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		return defer.maybeDeferred(resourcebased.writeVOTable, request, 
				result, votable.VOTableMaker()
			).addCallback(lambda _: request.finishRequest(False) or ""
			).addErrback(lambda _: request.finishRequest(False) or "")

	def _getInputData(self, formData):
		return self.service.getInputData(formData)

	def _handleInputData(self, inputData, ctx):
		queryMeta = common.QueryMeta(ctx)
		queryMeta["formal_data"] = self.form.data
		return self.service.run(inputData, queryMeta
			).addCallback(self._handleOutputData, ctx
			).addErrback(self._handleError, ctx)

	def _handleOutputData(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('content-disposition', 
			'attachment; filename="votable.xml"')
		return resourcebased.serveAsVOTable(request, data)

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		return self._writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())

	def _handleInputErrors(self, errors, ctx):
		msg = "Error(s) in given Parameters: %s"%"; ".join(
			[str(e) for e in errors])
		return self._writeErrorTable(ctx, msg)


class ScsRenderer(DalRenderer):
	"""is a renderer for the Simple Cone Search protocol.

	These do their error signaling in the value attribute of an
	INFO child of RESOURCE.
	"""
	name = "scs.xml"

	def _makeErrorTable(self, ctx, msg):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta("info", meta.makeMetaValue(msg, name="info", 
			infoName="Error", infoId="Error"))
		return common.CoreResult(data, {}, common.QueryMeta(ctx))


class SiapRenderer(DalRenderer):
	"""is a renderer for a the Simple Image Access Protocol.

	These have errors in the content of an info element, and they support
	metadata queries.
	"""
	name = "siap.xml"

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
			return self._serveMetadata(ctx)
		return super(SiapRenderer, self).renderHTTP(ctx)

	def _serveMetadata(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		inputFields = [contextgrammar.InputKey.fromDataField(f) 
			for f in self.service.getInputFields()]
		for f in inputFields:
			f.set_dest("INPUT:"+f.get_dest())
		dataDesc = resource.makeSimpleDataDesc(self.rd, 
			self.service.getOutputFields(common.QueryMeta(ctx)))
		dataDesc.set_items(inputFields)
		data = resource.InternalDataSet(dataDesc)
		data.addMeta("_type", "metadata")
		data.addMeta("info", meta.makeMetaValue("OK", name="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		result = common.CoreResult(data, {}, common.QueryMeta(ctx))
		return resourcebased.writeVOTable(request, result, votable.VOTableMaker())

	def _handleOutputData(self, data, ctx):
		data.addMeta("info", meta.makeMetaValue("OK", name="info",
			infoName="QUERY_STATUS", infoValue="OK"))
		data.addMeta("_type", "result")
		return super(SiapRenderer, self)._handleOutputData(data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta("info", meta.makeMetaValue(str(msg), name="info",
			infoValue="ERROR", infoName="QUERY_STATUS"))
		return common.CoreResult(data, {}, common.QueryMeta(ctx))


class RegistryRenderer(rend.Page):
	def renderHTTP(self, ctx):
		# Make a robust (unchecked) pars dict for error rendering; real
		# parameter checking happens in getPMHResponse
		pars = dict((key, val[0]) 
			for key, val in inevow.IRequest(ctx).args.iteritems())
		return threads.deferToThread(registry.getPMHResponse, 
				inevow.IRequest(ctx).args
			).addCallback(self._renderResponse, ctx
			).addErrback(self._renderError, ctx, pars)
	
	def _renderError(self, failure, ctx, pars):
		try:
			return self._renderResponse(registry.getErrorTree(failure.value, pars),
				ctx)
		except:
			import traceback
			traceback.print_exc()
			failure.printTraceback()
			request = inevow.IRequest(ctx)
			request.setResponseCode(500)
			request.setHeader("content-type", "text/plain")
			request.write("Internal error.  Please notify site maintainer")
			request.finishRequest(False)
		return appserver.errorMarker
			
	def _renderResponse(self, etree, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		return ElementTree.tostring(etree.getroot(), registry.encoding)
