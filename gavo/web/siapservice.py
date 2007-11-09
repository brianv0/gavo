"""
A real, standards-compliant siap service.

We don't want a standard resource-based service here since the entire error
handling is completely different.
"""

from nevow import appserver
from nevow import inevow
from nevow import util as nevowutil

from twisted.internet import defer
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import votable
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.web import common
from gavo.web import resourcebased


class SiapService(resourcebased.Form):
	implements(inevow.ICanHandleException)

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		resourcebased.Form.__init__(self, ctx, *args, **kwargs)

	def renderHTTP(self, ctx):
		# This is mainly an extract of what we need of formal.Form.process
		# generate the form -- I guess we should put this into a Form class
		# of its own.
		try:
			self.form_genForm(ctx)
			request = inevow.IRequest(ctx)
			charset = nevowutil.getPOSTCharset(ctx)
			# Get the request args and decode the arg names
			args = dict([(k.decode(charset),v) for k,v in request.args.items()])
			self.form.errors.data = args
			# Iterate the items and collect the form data and/or errors.
			for item in self.form.items:
				item.process(ctx, self.form, args, self.form.errors)
			# format validation errors
			if self.form.errors:
				return self._handleInputErrors(ctx, self.form.errors.errors)
			return defer.maybeDeferred(self.service.getInputData, self.form.data
				).addCallback(self._handleInputData, ctx
				).addErrback(self._handleError, ctx)
		except:
			return self.renderHTTP_exception(ctx, failure.Failure())

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

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		return self.writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())

	def _handleInputData(self, inputData, ctx):
		return self.service.run(inputData, common.QueryMeta(self.form.data)
			).addCallback(self._handleOutputData, ctx
			).addErrback(self._handleError, ctx)

	def _handleOutputData(self, data, ctx):
		request = inevow.IRequest(ctx)
		data.addMeta(name="_query_status", content=meta.InfoItem("OK", ""))
		return resourcebased.serveAsVOTable(request, data)

	def _handleInputErrors(self, ctx, errors):
		msg = "Error(s) in given Parameters: %s"%"; ".join(
			[str(e) for e in errors])
		return self.writeErrorTable(ctx, msg)
	
	def _handleError(self, failure, ctx):
		if isinstance(failure.value, gavo.ValidationError):
			return self._handleInputErrors(ctx, ["Parameter %s: %s"%(
				failure.value.fieldName, failure.getErrorMessage())])
		return self.renderHTTP_exception(ctx, failure)
