"""
Support for IVOA DAL and registry protocols.
"""

import datetime


from nevow import appserver
from nevow import inevow
from nevow import rend

from twisted.internet import defer
from twisted.internet import threads
from twisted.python import failure

from zope.interface import implements

from gavo import base
from gavo import registry
from gavo import rscdef
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo.imp import formal
from gavo.imp.VOTable import DataModel as VOTable
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

	resultType = "application/x-votable+xml"
	urlUse = "base"

	def __init__(self, ctx, *args, **kwargs):
		ctx.remember(self, inevow.ICanHandleException)
		reqArgs = inevow.IRequest(ctx).args
		if not "_DBOPTIONS_LIMIT" in reqArgs:
			reqArgs["_DBOPTIONS_LIMIT"] = [
				str(base.getConfig("ivoa", "dalDefaultLimit"))]
		reqArgs["_FORMAT"] = ["VOTable"]
		resourcebased.Form.__init__(self, ctx, *args, **kwargs)

	@classmethod
	def makeAccessURL(cls, baseURL):
		return "%s/%s?"%(baseURL, cls.name)

	_generateForm = resourcebased.Form.form_genForm

	def _getResource(self, outputName):
		# These always render themselves
		return None

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
		request.setHeader("content-type", self.resultType)
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

	Services using this renderer *must* have meta items testQuery.ra and
	testQuery.dec set to the (decimal) RA and dec of an object in the 
	published catalogue (actually, to a position within 0.001 deg of such
	an object).

	You must set the following metadata items on services using
	this renderer if you want to register them:

	* testQuery.ra, testQuery.dec -- A position for which an object is present
	  within 0.001 degrees.
	"""
	name = "scs.xml"

	def _writeErrorTable(self, ctx, msg):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		request.write(str(VOTable.VOTable(
			description=self.service.getMeta("description").getContent(),
			info=[
				VOTable.Info(ID="Error", name="Error", 
					value=str(msg).replace('"', '\\"'))])))
		return ""

	def _formatOutput(self, data, ctx):
		"""makes output SCS 1.02 compatible or causes the service to error out.

		This comprises mapping meta.id;meta.main to ID_MAIN and
		pos.eq* to POS_EQ*.
		"""
		ucdCasts = {
			"meta.id;meta.main": {"ucd": "ID_MAIN"},
			"pos.eq.ra;meta.main": {"ucd": "POS_EQ_RA_MAIN", "type": "double"},
			"pos.eq.dec;meta.main": {"ucd": "POS_EQ_DEC_MAIN", "type": "double"},
		}
		realCasts = {}
		table = data.original.getPrimaryTable()
		for ind, ofield in enumerate(table.tableDef.columns):
			if ofield.ucd in ucdCasts:
				realCasts[ofield.name] = ucdCasts.pop(ofield.ucd)
		if ucdCasts:
			return self._writeErrorTable(ctx, "Table cannot be formatted for"
				" SCS.  Column(s) with the following new UCD(s) were missing in"
				" output table: %s"%', '.join(translatedUCDs))
		table.votCasts = realCasts
		return DALRenderer._formatOutput(self, data, ctx)

svcs.registerRenderer("scs.xml", SCSRenderer)


class SIAPRenderer(DALRenderer):
	"""is a renderer for a the Simple Image Access Protocol.

	These have errors in the content of an info element, and they support
	metadata queries.

	It is recommended to set the following metadata items on services
	using this renderer:

	* testQuery.pos.ra, testQuery.pos.dec -- RA and Dec for a query that
	  yields at least one image
	* testQuery.size.ra, testQuery.size.dec -- RoI extent for a query that 
		yields at least one image.
	"""
	name = "siap.xml"

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
			return self._serveMetadata(ctx)
		return DALRenderer.renderHTTP(self, ctx)

	_outputTableCasts = {
		"pixelScale": {"datatype": "double"},
		"wcs_cdmatrix": {"datatype": "double"},
		"wcs_refValues": {"datatype": "double"},
		"bandpassHi": {"datatype": "double"},
		"bandpassLo": {"datatype": "double"},
		"bandpassRefval": {"datatype": "double"},
		"wcs_refPixel": {"datatype": "double"},
		"wcs_projection": {"arraysize": "3", "castFunction": lambda s: s[:3]},
	}

	def _makeMetadataData(self, queryMeta):
		inputFields = [svcs.InputKey.fromColumn(f) 
			for f in self.service.getInputFields()]
		for f in inputFields:
			f.name = "INPUT:"+f.name
		inputTable = MS(rscdef.TableDef, columns=inputFields)
		outputTable = MS(rscdef.TableDef, columns=
			self.service.getCurOutputFields(queryMeta), id="result")

		nullRowmaker = MS(rscdef.RowmakerDef)
		dataDesc = MS(rscdef.DataDescriptor, makes=[
			MS(rscdef.Make, table=inputTable, role="parameters", 
				rowmaker=nullRowmaker),
			MS(rscdef.Make, table=outputTable, rowmaker=nullRowmaker)],
			parent_=self.service.rd)

		data = rsc.makeData(dataDesc)
		data.tables["result"].votCasts = self._outputTableCasts
		data.addMeta("_type", "results")
		data.addMeta("info", base.makeMetaValue("OK", name="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		return svcs.SvcResult(data, {}, queryMeta)

	def _serveMetadata(self, ctx):
		metaData = self._makeMetadataData(svcs.QueryMeta.fromContext(ctx))
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml+votable")
		return resourcebased.streamVOTable(request, metaData)

	def _formatOutput(self, data, ctx):
		data.original.addMeta("info", base.makeMetaValue("OK", name="info",
			infoName="QUERY_STATUS", infoValue="OK"))
		data.original.addMeta("_type", "results")
		data.original.getPrimaryTable().votCasts = self._outputTableCasts
		return DALRenderer._formatOutput(self, data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		dataDesc = MS(rscdef.DataDescriptor, parent_=self.service.rd)
		data = rsc.makeData(dataDesc)
		data.addMeta("info", base.makeMetaValue(str(msg), name="info",
			infoValue="ERROR", infoName="QUERY_STATUS"))
		data.addMeta("_type", "results")
		return svcs.SvcResult(data, {}, svcs.QueryMeta.fromContext(ctx))

svcs.registerRenderer("siap.xml", SIAPRenderer)


class RegistryRenderer(grend.ServiceBasedRenderer):
	name = "pubreg.xml"
	urlUse = "base"
	resultType = "text/xml"

	@classmethod
	def makeAccessURL(cls, baseURL):
		# We return our alias here for consistency.
		return "%s%s/oai.xml"%(base.getConfig("web", "serverURL"),
			base.getConfig("web", "nevowRoot"))

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
		return ElementTree.tostring(etree.getroot(), "utf-8")

	def _getErrorTree(self, exception, pars):
		"""returns an ElementTree containing an OAI-PMH error response.

		If exception is one of "our" exceptions, we translate them to error messages.
		Otherwise, we reraise the exception to an enclosing
		function may "handle" it.

		Contrary to the recommendation in the OAI-PMH spec, this will only
		return one error at a time.
		"""
		from gavo.registry.model import OAI

		if isinstance(exception, registry.OAIError):
			code = exception.__class__.__name__
			code = code[0].lower()+code[1:]
			message = str(exception)
		else:
			raise exception
		return ElementTree.ElementTree(OAI.PMH[
			OAI.responseDate[datetime.datetime.now().strftime(
				utils.isoTimestampFmt)],
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
			
svcs.registerRenderer("pubreg.xml", RegistryRenderer)
