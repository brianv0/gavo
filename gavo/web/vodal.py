"""
Support for IVOA DAL and registry protocols.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


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
from gavo import votable
from gavo.imp import formal
from gavo.imp.formal import form
from gavo.protocols import uwsactions
from gavo.svcs import streaming
from gavo.utils import ElementTree
from gavo.votable import V
from gavo.web import common
from gavo.web import formrender
from gavo.web import grend


MS = base.makeStruct


__docformat__ = "restructuredtext en"


class DALRenderer(grend.ServiceBasedPage):
	"""is a base class for renderers for the usual IVOA DAL protocols.

	This is for simple, GET-based DAL renderers (where we allow POST as 
	well).  They work using nevow forms, but with standard-compliant error
	reporting (i.e., in VOTables).

	Since DALRenderer mixes in FormMixin, it always has the form genFrom.
	"""

	implements(inevow.ICanHandleException)

	resultType = base.votableType
	parameterStyle = "pql"
	urlUse = "base"

	def __init__(self, ctx, *args, **kwargs):
		reqArgs = inevow.IRequest(ctx).args
		if not "_DBOPTIONS_LIMIT" in reqArgs:
			reqArgs["_DBOPTIONS_LIMIT"] = [
				str(base.getConfig("ivoa", "dalDefaultLimit"))]
		reqArgs["_FORMAT"] = ["VOTable"]
		# see _writeErrorTable
		self.saneResponseCodes = False
		grend.ServiceBasedPage.__init__(self, ctx, *args, **kwargs)

	@classmethod
	def makeAccessURL(cls, baseURL):
		return "%s/%s?"%(baseURL, cls.name)

	@classmethod
	def isBrowseable(self, service):
		return False

	def renderHTTP(self, ctx):
		return defer.maybeDeferred(self._runService, ctx
			).addErrback(self._handleInputErrors, ctx
			).addErrback(self._handleRandomFailure, ctx)

	def _runService(self, ctx):
		return self.runService(inevow.IRequest(ctx).args
			).addCallback(self._formatOutput, ctx)

	def _writeErrorTable(self, ctx, errmsg, code=200, queryStatus="ERROR"):
		request = inevow.IRequest(ctx)

		# Unfortunately, most legacy DAL specs say the error messages must
		# be delivered with a 200 response code.  I hope this is going
		# to change at some point, so I let renderers order sane response
		# codes.
		if not self.saneResponseCodes:
			request.setResponseCode(code)
		result = self._makeErrorTable(ctx, errmsg, queryStatus)
		request.setHeader("content-type", base.votableType)
		votable.write(result, request)
		return "\n"

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('content-disposition', 
			'attachment; filename="votable.xml"')
		data.original.addMeta("info", base.makeMetaValue(type="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		request.setHeader("content-type", self.resultType)
		return streaming.streamVOTable(request, data)

	def _handleRandomFailure(self, failure, ctx):
		if not isinstance(failure, base.ValidationError):
			base.ui.notifyFailure(failure)
		return self._writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage(),
			500)
	
	def _handleInputErrors(self, failure, ctx):
		queryStatus = "ERROR"

		if isinstance(failure.value, base.EmptyData):
			inevow.IRequest(ctx).setResponseCode(400)
			queryStatus = "EMPTY"

		return self._writeErrorTable(ctx, failure.getErrorMessage(),
			queryStatus=queryStatus)


class SCSRenderer(DALRenderer):
	"""
	A renderer for the Simple Cone Search protocol.

	These do their error signaling in the value attribute of an
	INFO child of RESOURCE.

	You must set the following metadata items on services using
	this renderer if you want to register them:

	* testQuery.ra, testQuery.dec -- A position for which an object is present
		within 0.001 degrees.
	"""
	name = "scs.xml"

	def __init__(self, ctx, *args, **kwargs):
		reqArgs = inevow.IRequest(ctx).args
		if not "_DBOPTIONS_LIMIT" in reqArgs:
			reqArgs["_DBOPTIONS_LIMIT"] = [
				str(base.getConfig("ivoa", "dalDefaultLimit")*10)]
		if "_VOTABLE_VERSION" not in reqArgs:
			reqArgs["_VOTABLE_VERSION"] = ["1.1"]
		DALRenderer.__init__(self, ctx, *args, **kwargs)

	def _writeErrorTable(self, ctx, msg, code=200, queryStatus="ERROR"):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", base.votableType)
		votable.write(V.VOTABLE11[
			V.DESCRIPTION[base.getMetaText(self.service, "description")],
			V.INFO(ID="Error", name="Error",
					value=str(msg).replace('"', '\\"'))], request)
		request.write("\n")
		return ""

	def _formatOutput(self, data, ctx):
		"""makes output SCS 1.02 compatible or causes the service to error out.

		This comprises mapping meta.id;meta.main to ID_MAIN and
		pos.eq* to POS_EQ*.
		"""
		ucdCasts = {
			"meta.id;meta.main": {"ucd": "ID_MAIN", "datatype": "char", 
				"arraysize": "*"},
			"pos.eq.ra;meta.main": {"ucd": "POS_EQ_RA_MAIN", 
				"datatype": "double"},
			"pos.eq.dec;meta.main": {"ucd": "POS_EQ_DEC_MAIN", 
				"datatype": "double"},
		}
		realCasts = {}
		table = data.original.getPrimaryTable()
		for ind, ofield in enumerate(table.tableDef.columns):
			if ofield.ucd in ucdCasts:
				realCasts[ofield.name] = ucdCasts.pop(ofield.ucd)
		if ucdCasts:
			return self._writeErrorTable(ctx, "Table cannot be formatted for"
				" SCS.  Column(s) with the following new UCD(s) were missing in"
				" output table: %s"%', '.join(ucdCasts))

		# allow integers as ID_MAIN [HACK -- this needs to become saner.
		# conditional cast functions?]
		idCol = table.tableDef.getColumnByUCD("meta.id;meta.main")
		if idCol.type in set(["integer", "bigint", "smallint"]):
			realCasts[idCol.name]["castFunction"] = str
		table.votCasts = realCasts

		# as an extension, allow people to select different output formats
		# (this is a bit of a hack and should be revised after a while; this
		# currently is completely undocumented)
		if "FORMAT" in data.queryMeta.ctxArgs:
			from gavo.web import serviceresults
			return serviceresults.getFormat(
				data.queryMeta.ctxArgs["FORMAT"])._formatOutput(data, ctx)
		return DALRenderer._formatOutput(self, data, ctx)


class SIAPRenderer(DALRenderer):
	"""A renderer for a the Simple Image Access Protocol.

	These have errors in the content of an info element, and they support
	metadata queries.

	For registration, services using this renderer must set the following
	metadata items:

		- sia.type -- one of Cutout, Mosaic, Atlas, Pointed, see SIAP spec
	
	You should set the following metadata items:

		- testQuery.pos.ra, testQuery.pos.dec -- RA and Dec for a query that
			yields at least one image
		- testQuery.size.ra, testQuery.size.dec -- RoI extent for a query that 
			yields at least one image.
	
	You can set the following metadata items (there are defaults on them
	that basically communicate there are no reasonable limits on them):

	 - sia.maxQueryRegionSize.(long|lat)
	 - sia.maxImageExtent.(long|lat)
	 - sia.maxFileSize
	 - sia.maxRecord (default dalHardLimit global meta)
	"""
# XXX TODO: put more functionality into the core and then use
# UnifiedDALRenderer rather than siap.xml.
	name = "siap.xml"

	def __init__(self, ctx, *args, **kwargs):
		reqArgs = inevow.IRequest(ctx).args
		reqArgs["_VOTABLE_VERSION"] = ["1.1"]
		if "_TDENC" not in reqArgs:
			reqArgs["_TDENC"] = ["True"]
		DALRenderer.__init__(self, ctx, *args, **kwargs)

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		try:
			metadataQuery = args["FORMAT"][0].lower()=="metadata"
		except (IndexError, KeyError):
			metadataQuery = False
		if metadataQuery:
			return self._serveMetadata(ctx)

		return DALRenderer.renderHTTP(self, ctx)

	_outputTableCasts = {
		"pixelScale": {"datatype": "double", "arraysize": "*"},
		"wcs_cdmatrix": {"datatype": "double", "arraysize": "*"},
		"wcs_refValues": {"datatype": "double", "arraysize": "*"},
		"bandpassHi": {"datatype": "double"},
		"bandpassLo": {"datatype": "double"},
		"bandpassRefval": {"datatype": "double"},
		"wcs_refPixel": {"datatype": "double", "arraysize": "*"},
		"wcs_projection": {"arraysize": "3", "castFunction": lambda s: s[:3]},
		"mime": {"ucd": "VOX:Image_Format"},
		"accref": {"ucd": "VOX:Image_AccessReference"},
	}

	def _makeMetadataData(self, queryMeta):
		inputFields = [
			svcs.InputKey.fromColumn(f, name=utils.QuotedName("INPUT:"+f.name))
			for f in self.service.getInputKeysFor(self)]
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
		data.setMeta("_type", "results")
		data.addMeta("info", base.makeMetaValue("OK", type="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		return svcs.SvcResult(data, {}, queryMeta)

	def _serveMetadata(self, ctx):
		metaData = self._makeMetadataData(svcs.QueryMeta.fromContext(ctx))
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml+votable")
		return streaming.streamVOTable(request, metaData)

	def _formatOutput(self, data, ctx):
		data.original.setMeta("_type", "results")
		data.original.getPrimaryTable().votCasts = self._outputTableCasts
		return DALRenderer._formatOutput(self, data, ctx)
	
	def _makeErrorTable(self, ctx, msg, queryStatus="ERROR"):
		return V.VOTABLE11[
			V.RESOURCE(type="results")[
				V.INFO(name="QUERY_STATUS", value=queryStatus)[
					str(msg)]]]


class UnifiedDALRenderer(DALRenderer):
	"""A renderer for new-style simple DAL protocols.

	All input processing (e.g., metadata queries and the like) are considered
	part of the individual protocol and thus left to the core.

	The error style is that of SSAP (which, hopefully, will be kept
	for the other DAL2 protocols, too).  This renderer should be used
	for SSAP (and soon SIAP, too).  The trouble is that then, we'll
	need to dispatch the registry capabilities in some other way.

	To define actual renderers, inherit from this and set the name attribute
	(plus _outputTableCasts if necessary).

	In the docstring, document what additional meta is used in the 
	renderer's capability element.
	"""
	parameterStyle = "pql"

	_outputTableCasts = {}

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		if isinstance(data.original, tuple):  
			# core returned a complete document (mime and string)
			mime, payload = data.original
			request.setHeader("content-type", mime)
			return streaming.streamOut(lambda f: f.write(payload), request)
		else:
			request.setHeader("content-type", "text/xml+votable")
			data.original.setMeta("_type", "results")
			data.original.getPrimaryTable().votCasts = self._outputTableCasts
			return DALRenderer._formatOutput(self, data, ctx)
	
	def _makeErrorTable(self, ctx, msg, queryStatus="ERROR"):
		return V.VOTABLE11[
			V.RESOURCE(type="results")[
				V.INFO(name="QUERY_STATUS", value=queryStatus)[
					str(msg)]]]


class SSAPRenderer(UnifiedDALRenderer):
	"""A renderer for the simple spectral access protocol.

	For registration, you must set the following metadata on services 
	using the ssap.xml renderer:

	 - ssap.dataSource -- survey, pointed, custom, theory, artificial
	 - ssap.testQuery -- a query string that returns some data; REQUEST=queryData
	   is added automatically
	
	Other SSA metadata includes:

	 - ssap.creationType -- archival, cutout, filtered, mosaic,
	   projection, spectralExtraction, catalogExtraction (defaults to archival)
	 - ssap.complianceLevel -- set to "query" when you don't deliver
	   SDM compliant spectra; otherwise don't say anything, DaCHS will fill
	   in the right value.

	Services with this renderer can have a datalink property; if present, it
	must point to a datalink service producing SDM-compliant spectra; this
	is for doing cutouts and similar.
	"""
	name = "ssap.xml"


class RegistryRenderer(grend.ServiceBasedPage):
	"""A renderer that works with registry.oaiinter to provide an OAI-PMH
	interface.

	The core is expected to return a stanxml tree.
	"""
	name = "pubreg.xml"
	urlUse = "base"
	resultType = "text/xml"

	def renderHTTP(self, ctx):
		# Make a robust (unchecked) pars dict for error rendering; real
		# parameter checking happens in getPMHResponse
		inData = {"args": inevow.IRequest(ctx).args}
		return self.runService(inData, 
			queryMeta=svcs.QueryMeta.fromNevowArgs(inData["args"])
			).addCallback(self._renderResponse, ctx
			).addErrback(self._renderError, ctx, inData["args"])

	def _renderResponse(self, svcResult, ctx):
		return self._renderXML(svcResult.original, ctx)

	def _renderXML(self, stanxml, ctx):
# XXX TODO: this can be pretty large -- do we want async operation
# here?  Stream this?
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		return utils.xmlrender(stanxml,
			"<?xml-stylesheet href='/static/xsl/oai.xsl' type='text/xsl'?>")

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
			code = "badArgument" # Why the hell don't they have a serverError?
			message = "Internal Error: "+str(exception)
		return OAI.PMH[
			OAI.responseDate[datetime.datetime.utcnow().strftime(
				utils.isoTimestampFmt)],
			OAI.request(verb=pars.get("verb", ["Identify"])[0], 
					metadataPrefix=pars.get("metadataPrefix", [None])[0]),
			OAI.error(code=code)[
				message
			]
		]

	def _renderError(self, failure, ctx, pars):
		try:
			if not isinstance(failure.value, 
					(registry.OAIError, base.ValidationError)):
				base.ui.notifyFailure(failure)
			return self._renderXML(self._getErrorTree(failure.value, pars),
				ctx)
		except:
			base.ui.notifyError("Cannot create registry error document")
			request = inevow.IRequest(ctx)
			request.setResponseCode(400)
			request.setHeader("content-type", "text/plain")
			request.write("Internal error.  Please notify site maintainer")
			request.finishRequest(False)
		return appserver.errorMarker


class _DatalinkRendererBase(grend.ServiceBasedPage):
	"""the base class of the two datalink renderers.
	"""
	urlUse = "base"

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		return self.runService(request.args, ctx
			).addCallback(self._formatData, request
			).addErrback(self._reportError, request)
	
	def _formatData(self, svcResult, request):
		# the core returns mime, data or a resource.  So, if it's a pair,
		# to something myself, else let twisted sort it out
		data = svcResult.original

		if isinstance(data, tuple):
# XXX TODO: the same thing is in formrender.  Refactor; since this is
# something most renderers should be able to do, ServiceBasedPage would be
# a good place
			mime, payload = data
			request.setHeader("content-type", mime)
			request.setHeader('content-disposition', 
				'attachment; filename=result%s'%common.getExtForMime(mime))
			return streaming.streamOut(lambda f: f.write(payload), 
				request)

		else:
			return data

	def _reportError(self, failure, request):
		base.ui.notifyFailure(failure)
		request.setHeader("content-type", "text/plain")
		if isinstance(failure.value, base.Error):
			request.setResponseCode(422)
		else:
			request.setResponseCode(500)
		return utils.safe_str(failure.value)+"\n"


class DatalinkGetDataRenderer(_DatalinkRendererBase):
	"""A renderer for data processing by datalink cores.

	This must go together with a datalink core, nothing else will do.

	This renderer will actually produce the processed data.  It must be
	complemented by the dlmeta renderer which allows retrieving metadata.
	"""
	name = "dlget"


class DatalinkGetMetaRenderer(_DatalinkRendererBase):
	"""A renderer for data processing by datalink cores.

	This must go together with a datalink core, nothing else will do.

	This renderer will return the links and services applicable to
	one or more pubDIDs.

	See `Datalink Cores`_ for more information.
	"""
	name = "dlmeta"
	resultType = "application/x-votable+xml;content=datalink"


def _test():
	import doctest, vodal
	doctest.testmod(vodal)


if __name__=="__main__":
	_test()
