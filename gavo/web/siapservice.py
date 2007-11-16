"""
A real, standards-compliant siap service.

We don't want a standard resource-based service here since the entire error
handling is completely different.
"""

from nevow import inevow

from twisted.internet import defer
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import datadef
from gavo import votable
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.web import common
from gavo.web import resourcebased


class SiapService(common.CustomErrorMixin, resourcebased.Form):
	implements(inevow.ICanHandleException)

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		resourcebased.Form.__init__(self, ctx, *args, **kwargs)

	_generateForm = resourcebased.Form.form_genForm

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
			return self._serveMetadata(ctx)
		return super(SiapService, self).renderHTTP(ctx)

	def _serveMetadata(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		inputFields = [datadef.DataField(**f.dataStore) 
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

	def _writeErrorTable(self, ctx, errmsg):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_query_status", content=meta.InfoItem(
			"ERROR", errmsg))
		result = common.CoreResult(data, {}, common.QueryMeta(ctx))
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
		data.addMeta(name="_query_status", content=meta.InfoItem("OK", ""))
		data.addMeta(name="_type", content="result")
		data.addMeta(name="_query_status", content="OK")
		return resourcebased.serveAsVOTable(request, data)

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		return self._writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())

	def _handleInputErrors(self, errors, ctx):
		msg = "Error(s) in given Parameters: %s"%"; ".join(
			[str(e) for e in errors])
		return self._writeErrorTable(ctx, msg)
