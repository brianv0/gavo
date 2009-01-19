"""
Support for IVOA DAL and registry protocols.
"""

import datetime

import formal

from nevow import appserver
from nevow import inevow
from nevow import rend

from twisted.internet import defer
from twisted.internet import threads
from twisted.python import failure

from zope.interface import implements

from gavo import base
from gavo import rscdef
from gavo import rsc
from gavo import svcs
from gavo.protocols import registry
from gavo.utils import ElementTree
from gavo.web import grend
from gavo.web import resourcebased


MS = base.makeStruct


class DALRenderer(grend.CustomErrorMixin, resourcebased.Form):
	"""is a base class for renderers for the usual IVOA DAL protocols.

	The main difference to the standard VOTable renderer is the custom
	error reporting.  For this, the inheriting class has to define
	a method _makeErrorTable(ctx, errorMessage) that must return a SvcResult
	instance producing a VOTable according to specification.
	"""

	implements(inevow.ICanHandleException)

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		reqArgs = inevow.IRequest(ctx).args
		if not "_DBOPTIONS_LIMIT" in reqArgs:
			reqArgs["_DBOPTIONS_LIMIT"] = [
				str(base.getConfig("ivoa", "dalDefaultLimit"))]
		resourcebased.Form.__init__(self, ctx, *args, **kwargs)

	_generateForm = resourcebased.Form.form_genForm

	def _writeErrorTable(self, ctx, errmsg):
		result = self._makeErrorTable(ctx, errmsg)
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		return defer.maybeDeferred(resourcebased.streamVOTable, request, 
				result
			).addCallback(lambda _: request.finishRequest(False) or ""
			).addErrback(lambda _: request.finishRequest(False) or "")

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('content-disposition', 
			'attachment; filename="votable.xml"')
		request.setHeader("content-type", "application/x-votable")
		return resourcebased.streamVOTable(request, data)

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		return self._writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())
	
	def _crashAndBurn(self, failure, ctx):
		failure.printTraceback()
		return self.renderHTTP_exception(ctx, failure)

	def _handleInputErrors(self, errors, ctx):
		def formatError(e):
			if isinstance(e, formal.FieldError):
				return "%s: %s"%(e.fieldName, str(e))
			else:
				return str(e.getErrorMessage())
		if isinstance(errors, list):
			msg = "Error(s) in given Parameters: %s"%"; ".join(
				[formatError(e) for e in errors])
		else:
			msg = formatError(errors)
		return self._writeErrorTable(ctx, msg)


class SCSRenderer(DALRenderer):
	"""is a renderer for the Simple Cone Search protocol.

	These do their error signaling in the value attribute of an
	INFO child of RESOURCE.
	"""
	name = "scs.xml"

	def _makeErrorTable(self, ctx, msg):
		data = rsc.makeData(MS(rscdef.DataDescriptor, parent_=self.service.rd))
		data.addMeta("info", base.makeMetaValue(msg, name="info", 
			infoName="Error", infoId="Error"))
		return svcs.SvcResult(data, {}, svcs.QueryMeta.fromContext(ctx))

grend.registerRenderer("scs.xml", SCSRenderer)


class SIAPRenderer(DALRenderer):
	"""is a renderer for a the Simple Image Access Protocol.

	These have errors in the content of an info element, and they support
	metadata queries.
	"""
	name = "siap.xml"

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
			return self._serveMetadata(ctx)
		return DALRenderer.renderHTTP(self, ctx)

	def _makeMetadataData(self, queryMeta):
		inputFields = [svcs.InputKey.fromColumn(f) 
			for f in self.service.getInputFields()]
		for f in inputFields:
			f.name = "INPUT:"+f.name
		inputTable = MS(rscdef.TableDef, columns=inputFields)
		outputTable = MS(rscdef.TableDef, columns=
			self.service.getCurOutputFields(queryMeta))

		nullRowmaker = MS(rscdef.RowmakerDef)
		dataDesc = MS(rscdef.DataDescriptor, makes=[
			MS(rscdef.Make, table=inputTable, role="parameters", 
				rowmaker=nullRowmaker),
			MS(rscdef.Make, table=self.service.core.outputTable, 
				rowmaker=nullRowmaker)],
			parent_=self.service.rd)

		data = rsc.makeData(dataDesc)
		data.addMeta("_type", "metadata")
		data.addMeta("info", base.makeMetaValue("OK", name="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		return svcs.SvcResult(data, {}, queryMeta)

	def _serveMetadata(self, ctx):
		metaData = self._makeMetadataData(svcs.QueryMeta.fromContext(ctx))
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		return resourcebased.streamVOTable(request, metaData)

	def _formatOutput(self, data, ctx):
		data.original.addMeta("info", base.makeMetaValue("OK", name="info",
			infoName="QUERY_STATUS", infoValue="OK"))
		data.original.addMeta("_type", "results")
		return DALRenderer._formatOutput(self, data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		dataDesc = MS(rscdef.DataDescriptor, parent_=self.service.rd)
		data = rsc.makeData(dataDesc)
		data.addMeta("info", base.makeMetaValue(str(msg), name="info",
			infoValue="ERROR", infoName="QUERY_STATUS"))
		return svcs.SvcResult(data, {}, svcs.QueryMeta.fromContext(ctx))

grend.registerRenderer("siap.xml", SIAPRenderer)


class RegistryCore(svcs.Core):
	"""is a core processing OAI requests.

	Its signature requires a single input key containing the complete
	args from the incoming request.  This is necessary to satisfy the
	requirement of raising errors on duplicate arguments.

	It returns an ElementTree.

	This core is intended to work the the RegistryRenderer.
	"""
	name_ = "registryCore"

	def completeElement(self):
		if self.inputDD is not base.Undefined:
			raise base.StructureError("RegistryCores have a fixed"
				" inputDD that you may not override.")
		self.inputDD = base.parseFromString(svcs.InputDescriptor, """
			<inputDD>
				<table id="_pubregInput">
					<column name="args" type="raw"
						description="The raw dictionary of input parameters"/>
				</table>
				<make table="_pubregInput"/>
			</inputDD>""")
		if self.outputTable is base.Undefined:
			self.outputTable = base.makeStruct(svcs.OutputTableDef)
		self._completeElementNext(RegistryCore)

	def runWithPMHDict(self, args):
		pars = {}
		for argName, argVal in args.iteritems():
			if len(argVal)!=1:
				raise registry.BadArgument(argName)
			else:
				pars[argName] = argVal[0]
		try:
			verb = pars["verb"]
		except KeyError:
			raise registry.BadArgument("verb")
		try:
			handler = registry.pmhHandlers[verb]
		except KeyError:
			raise registry.BadVerb("'%s' is an unsupported operation."%pars["verb"])
		return ElementTree.ElementTree(handler(pars).asETree())

	def run(self, service, inputData, queryMeta):
		"""returns an ElementTree containing a OAI-PMH response for the query 
		described by pars.
		"""
		args = inputData.getPrimaryTable().rows[0]["args"]
		return self.runWithPMHDict(args)

svcs.registerCore(RegistryCore)


class RegistryRenderer(grend.ServiceBasedRenderer):
	name = "pubreg.xml"

	def renderHTTP(self, ctx):
		# Make a robust (unchecked) pars dict for error rendering; real
		# parameter checking happens in getPMHResponse
		inData = {"args": inevow.IRequest(ctx).args}
		return threads.deferToThread(self.service.runFromContext, inData, ctx
			).addCallback(self._renderResponse, ctx
			).addErrback(self._renderError, ctx, inData["args"])

	def _renderResponse(self, svcResult, ctx):
		return self._renderXML(svcResult.original, ctx)

	def _renderXML(self, etree, ctx):
# XXX TODO: etree can be pretty large -- do we want async operation
# here?  Stream this?
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		return ElementTree.tostring(etree.getroot(), registry.encoding)

	def _getErrorTree(self, exception, pars):
		"""returns an ElementTree containing an OAI-PMH error response.

		If exception is one of "our" exceptions, we translate them to error messages.
		Otherwise, we reraise the exception to an enclosing
		function may "handle" it.

		Contrary to the recommendation in the OAI-PMH spec, this will only
		return one error at a time.
		"""
		from gavo.protocols.registrymodel import OAI

		if isinstance(exception, registry.OAIError):
			code = exception.__class__.__name__
			code = code[0].lower()+code[1:]
			message = str(exception)
		else:
			raise exception
		return ElementTree.ElementTree(OAI.PMH[
			OAI.responseDate[datetime.datetime.now().strftime(
				registry._isoTimestampFmt)],
			OAI.request(verb=pars.get("verb", ["Identify"])[0], 
					metadataPrefix=pars.get("metadataPrefix", [None])[0]),
			OAI.error(code=code)[
				message
			]
		].asETree())

	def _renderError(self, failure, ctx, pars):
		try:
			return self._renderXML(self._getErrorTree(failure.value, pars),
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
			
grend.registerRenderer("pubreg.xml", RegistryRenderer)
