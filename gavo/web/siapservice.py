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

	def writeErrorTable(self, ctx, errmsg):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_query_status", content=meta.InfoItem(
			"ERROR", errmsg))
# XXX TODO: See if there's any chance we can get at QueryMeta here.
		result = common.CoreResult(data, {}, common.QueryMeta({}))
		return resourcebased.writeVOTable(request, result, votable.VOTableMaker())

	def _getInputData(self, formData):
		return self.service.getInputData(formData)

	def _handleInputData(self, inputData, ctx):
		return self.service.run(inputData, common.QueryMeta(self.form.data)
			).addCallback(self._handleOutputData, ctx
			).addErrback(self._handleError, ctx)

	def _handleOutputData(self, data, ctx):
		request = inevow.IRequest(ctx)
		data.addMeta(name="_query_status", content=meta.InfoItem("OK", ""))
		return resourcebased.serveAsVOTable(request, data)

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		return self.writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())

	def _handleInputErrors(self, errors, ctx):
		msg = "Error(s) in given Parameters: %s"%"; ".join(
			[str(e) for e in errors])
		return self.writeErrorTable(ctx, msg)
