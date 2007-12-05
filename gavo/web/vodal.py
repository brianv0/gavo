"""
Support for IVOA DAL protocols.
"""

from nevow import inevow

from twisted.internet import defer
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import datadef
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.web import common
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
		data.addMeta(name="_error", content=meta.InfoItem(msg, ""))
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
		inputFields = [contextgrammar.InputKey(**f.dataStore) 
			for f in self.service.getInputFields()]
		for f in inputFields:
			f.set_dest("INPUT:"+f.get_dest())
		dataDesc = resource.makeSimpleDataDesc(self.rd, 
			self.service.getOutputFields(common.QueryMeta(ctx)))
		dataDesc.set_items(inputFields)
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_type", content="metadata")
		data.addMeta(name="_query_status", content="OK")
		result = common.CoreResult(data, {}, common.QueryMeta(ctx))
		return resourcebased.writeVOTable(request, result, votable.VOTableMaker())

	def _handleOutputData(self, data, ctx):
		data.addMeta(name="_query_status", content=meta.InfoItem("OK", ""))
		data.addMeta(name="_type", content="result")
		data.addMeta(name="_query_status", content="OK")
		return super(SiapRenderer, self)._handleOutputData(data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_query_status", content=meta.InfoItem(
			"ERROR", str(msg)))
		return common.CoreResult(data, {}, common.QueryMeta(ctx))

