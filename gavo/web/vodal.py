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
from gavo import votable
from gavo.imp import formal
from gavo.imp.formal import form
from gavo.utils import ElementTree
from gavo.votable import V
from gavo.web import formrender
from gavo.web import grend
from gavo.web import streaming


MS = base.makeStruct


__docformat__ = "restructuredtext en"


class CaseSemisensitiveDict(dict):
	"""A dictionary allowing case-insensitive access to its content.

	This is used for DAL renderers which, unfortunately, are supposed
	to be case insensitive.  Since case insensitivity is at least undesirable
	for service-specific keys, we go a semi-insenstitve approach here:
	First, we try literal matches, if that does not work, we try matching
	against an all-uppercase version.

	Name clashes resulting from different names being mapped to the
	same normalized version are handled in some random way.  Don't do this.
	And don't rely on case normalization if at all possible.

	Only strings are allowed as keys here.  This class is not concerned
	with the values.
	>>> d = CaseSemisensitiveDict({"a": 1, "A": 2, "b": 3})
	>>> d["a"], d["A"], d["b"], d["B"]
	(1, 2, 3, 3)
	>>> d["B"] = 9; d["b"], d["B"]
	(3, 9)
	>>> del d["b"]; d["b"], d["B"]
	(9, 9)
	"""
	def __init__(self, *args, **kwargs):
		dict.__init__(self, *args, **kwargs)
		self.normCased = None

	def __getitem__(self, key):
		try:
			return dict.__getitem__(self, key)
		except KeyError:
			pass # try again with normalized case.
		return self._getNormCased()[key.upper()]

	def __setitem__(self, key, value):
		self.normCased = None
		dict.__setitem__(self, key, value)

	def __contains__(self, key):
		return dict.__contains__(self, key) or key.upper() in self._getNormCased()

	def _getNormCased(self):
		if self.normCased is None:
			self.normCased = dict((k.upper(), v) 
				for k, v in self.iteritems())
		return self.normCased

class DALRenderer(grend.ServiceBasedPage):
	"""is a base class for renderers for the usual IVOA DAL protocols.

	This is for simple, GET-based DAL renderers (where we allow POST as 
	well).  They work using nevow forms, but with standard-compliant error
	reporting (i.e., in VOTables).

	Since DALRenderer mixes in FormMixin, it always has the form genFrom.
	"""

	implements(inevow.ICanHandleException)

	resultType = "application/x-votable+xml"
	parameterStyle = "dal"
	urlUse = "base"

	def __init__(self, ctx, *args, **kwargs):
		reqArgs = inevow.IRequest(ctx).args
		if not "_DBOPTIONS_LIMIT" in reqArgs:
			reqArgs["_DBOPTIONS_LIMIT"] = [
				str(base.getConfig("ivoa", "dalDefaultLimit"))]
		reqArgs["_FORMAT"] = ["VOTable"]
		reqArgs["_VOTABLE_VERSION"] = ["1.1"]
		grend.ServiceBasedPage.__init__(self, ctx, *args, **kwargs)

	@classmethod
	def makeAccessURL(cls, baseURL):
		return "%s/%s?"%(baseURL, cls.name)

	@classmethod
	def isBrowseable(self, service):
		return False

	def renderHTTP(self, ctx):
		# the weird _handleInputErrors is because form.process returns
		# form errors rather than raising an exception when something is
		# wrong.  _handleInputErrors knows all is fine if it receives a None.
		return defer.maybeDeferred(self._runService, ctx
			).addCallback(self._handleInputErrors, ctx
			).addErrback(self._handleInputErrors, ctx
			).addErrback(self._handleRandomFailure, ctx)

	def _runService(self, ctx):
		contextData = CaseSemisensitiveDict()
		for key, val in inevow.IRequest(ctx).args.iteritems():
			if val:
				contextData[key] = val[-1]
		return self.runServiceWithContext(contextData, ctx
			).addCallback(self._formatOutput, ctx)

	def _writeErrorTable(self, ctx, errmsg):
		result = self._makeErrorTable(ctx, errmsg)
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		request.write(result.render()+"\n")
		return ""

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('content-disposition', 
			'attachment; filename="votable.xml"')
		data.original.addMeta("info", base.makeMetaValue(type="info", 
			infoName="QUERY_STATUS", infoValue="OK"))
		request.setHeader("content-type", self.resultType)
		return streaming.streamVOTable(request, data)

	def _handleRandomFailure(self, failure, ctx):
		base.ui.notifyFailure(failure)
		return self._writeErrorTable(ctx,
			"Unexpected failure, error message: %s"%failure.getErrorMessage())
	
	def _handleInputErrors(self, errors, ctx):
		if not errors:  # flag from form.process: All is fine.
			return ""
		def formatError(e):
			return "%s: %s"%(e.fieldName, str(e))
		try:
			msg = errors.getErrorMessage()
			if base.DEBUG:
				base.ui.notifyFailure(errors)
		except AttributeError:
			msg = "Error(s) in given Parameters: %s"%"; ".join(
				[formatError(e) for e in errors])
		return self._writeErrorTable(ctx, msg)


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

	def _writeErrorTable(self, ctx, msg):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
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
		return DALRenderer._formatOutput(self, data, ctx)


class SIAPRenderer(DALRenderer):
	"""A renderer for a the Simple Image Access Protocol.

	These have errors in the content of an info element, and they support
	metadata queries.

	It is recommended to set the following metadata items on services
	using this renderer:

		- testQuery.pos.ra, testQuery.pos.dec -- RA and Dec for a query that
			yields at least one image
		- testQuery.size.ra, testQuery.size.dec -- RoI extent for a query that 
			yields at least one image.
	"""
# XXX TODO: put more functionality into the core and then use
# UnifiedDALRenderer rather than siap.xml.
	name = "siap.xml"

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
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
			svcs.InputKey.fromColumn(f, name="quoted/INPUT:"+f.name)
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
	
	def _makeErrorTable(self, ctx, msg):
		return V.VOTABLE[
			V.RESOURCE(type="results")[
				V.INFO(name="QUERY_STATUS", value="ERROR")[
					str(msg)]]]


class UnifiedDALRenderer(DALRenderer):
	"""A renderer for new-style simple DAL protocols.

	All input processing (e.g., metadata queries and the like) are considered
	part of the individual protocol and thus left to the core.

	The error style is that of SSAP (which, hopefully, will be kept
	for the other DAL2 protocols, too).  This renderer should be used
	for SSAP (and soon SIAP, too).
	"""
	name = "dal.xml"
	parameterStyle = "pql"

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		if isinstance(data.original, tuple):  
			mime, payload = data.original
			request.setHeader("content-type", mime)
			return streaming.streamOut(lambda f: f.write(payload), request)
		else:
			request.setHeader("content-type", "text/xml+votable")
			data.original.addMeta("info", base.makeMetaValue("OK", name="info",
				infoName="QUERY_STATUS", infoValue="OK"))
			data.original.setMeta("_type", "results")
			data.original.getPrimaryTable().votCasts = self._outputTableCasts
			return DALRenderer._formatOutput(self, data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		return V.VOTABLE[
			V.RESOURCE(type="results")[
				V.INFO(name="QUERY_STATUS", value="ERROR")[
					str(msg)]]]


class RegistryRenderer(grend.ServiceBasedRenderer):
	name = "pubreg.xml"
	urlUse = "base"
	resultType = "text/xml"

	@classmethod
	def makeAccessURL(cls, baseURL):
		# We return our alias here for consistency.
		return "%s%soai.xml"%(base.getConfig("web", "serverURL"),
			base.getConfig("web", "nevowRoot"))

	def renderHTTP(self, ctx):
		# Make a robust (unchecked) pars dict for error rendering; real
		# parameter checking happens in getPMHResponse
		inData = {"args": inevow.IRequest(ctx).args}
		return self.runServiceWithContext(inData, ctx
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
			code = "badArgument" # Why the hell don't they have a serverError?
			message = "Internal Error: "+str(exception)
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
			if not isinstance(failure.value, registry.OAIError):
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


def _test():
	import doctest, vodal
	doctest.testmod(vodal)


if __name__=="__main__":
	_test()
