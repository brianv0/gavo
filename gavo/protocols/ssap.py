"""
The SSAP core and supporting code.

"""

import urllib
from cStringIO import StringIO

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import products
from gavo.svcs import outputdef
from gavo.votable import V


RD_ID = "//ssap"


# getdata format identifiers to formats.formatData keys.  Special
# handling for FITS variants below, noted by None values here.
GETDATA_FORMATS = {
	"application/x-votable+xml": "votable",
	"application/x-votable+xml;encoding=tabledata": "votabletd",
	"text/plain": "tsv",
	"text/csv": "csv",
	"application/fits": None,
	"image/fits": None,}


def getRD():
	return base.caches.getRD(RD_ID)


class SSAPCore(svcs.DBCore):
	"""A core doing SSAP queries.

	This core knows about metadata queries, version negotiation, and 
	dispatches on REQUEST.  Thus, it may return formatted XML data
	under certain circumstances.
	"""
	name_ = "ssapCore"

	ssapVersion = "1.04"

	outputTableXML = """
		<outputTable verbLevel="30">
			<FEED source="//ssap#coreOutputAdditionals"/>
		</outputTable>"""

	def _makeMetadata(self, service):
		metaTD = self.outputTable.change(id="results")
		for param in metaTD.params:
			param.name = "OUTPUT:"+param.name
		dd = base.makeStruct(rscdef.DataDescriptor, parent_=self.rd,
			makes=[base.makeStruct(rscdef.Make, table=metaTD,
				rowmaker=base.makeStruct(rscdef.RowmakerDef))])
		dd.setMetaParent(service)

		for inP in self.inputTable.params:
			dd.feedObject("param", inP.change(name="INPUT:"+inP.name))

		dd.setMeta("_type", "meta")
		dd.addMeta("info", base.makeMetaValue(
			"", name="info", infoName="QUERY_STATUS", infoValue="OK"))
		dd.addMeta("info", base.makeMetaValue(
			"SSAP", name="info", infoName="SERVICE_PROTOCOL", infoValue="1.04"))

		data = rsc.makeData(dd)
		
		return "application/x-votable+xml", votablewrite.getAsVOTable(data)

	def run(self, service, inputTable, queryMeta):
		requestType = (inputTable.getParam("REQUEST") or "").upper()
		if requestType=="QUERYDATA":
			return self._runQueryData(service, inputTable, queryMeta)
		elif requestType=="GETDATA":
			return self._runGetData(service, inputTable, queryMeta)
		elif requestType=="GETTARGETNAMES":
			return self._runGetTargetNames(service, inputTable, queryMeta)
		else:
			raise base.ValidationError("Missing or invalid value for REQUEST.",
				"REQUEST")

	def _runGetData(self, service, inputTable, queryMeta):
		tablesourceId = service.getProperty("tablesource", None)
		if tablesourceId is None:
			raise base.ValidationError("No getData support on %s"%
				service.getMeta("identifier"), "REQUEST", hint="Only SSAP"
				" services with a tablesource property support getData")
		tablesourceDD = service.rd.getById(tablesourceId)

		pubDID = inputTable.getParam("PUBDID")
		if pubDID is None:
			raise base.ValidationError("PUBDID mandatory for getData", "PUBDID")
		
		sdmData = makeSDMDataForPUBDID(pubDID, self.queriedTable, 
			tablesourceDD)

		return formatSDMData(sdmData, inputTable, queryMeta)
			

	def _runGetTargetNames(self, service, inputTable, queryMeta):
		with base.getTableConn()  as conn:
			table = rsc.TableForDef(self.queriedTable, create=False,
				role="primary", connection=conn)
			destTD = base.makeStruct(outputdef.OutputTableDef, 
				parent_=self.queriedTable.parent,
				id="result", onDisk=False,
				columns=[self.queriedTable.getColumnByName("ssa_targname")])
			res = rsc.TableForDef(destTD, rows=table.iterQuery(destTD, "",
				distinct=True))
			res.noPostprocess = True
			return res

	def _runQueryData(self, service, inputTable, queryMeta):
		format = inputTable.getParam("FORMAT") or ""
		if format.lower()=="metadata":
			return self._makeMetadata(service)

		limits = [q for q in 
				(inputTable.getParam("MAXREC"), inputTable.getParam("TOP"))
			if q]
		if not limits:
			limits = [base.getConfig("ivoa", "dalDefaultLimit")]
		limit = min(min(limits), base.getConfig("ivoa", "dalHardLimit"))
		queryMeta["dbLimit"] = limit

		res = svcs.DBCore.run(self, service, inputTable, queryMeta)
		if len(res)==limit:
			res.addMeta("info", base.makeMetaValue(type="info", 
				value="Exactly %s rows were returned.  This means"
				" your query probably reached the match limit.  Increase MAXREC."%limit,
				infoName="QUERY_STATUS", infoValue="OVERFLOW"))

		# add shitty namespace for utypes.  sigh.
		res.addMeta("_votableRootAttributes",
			'xmlns:ssa="http://www.ivoa.net/xml/DalSsap/v1.0"')

		res.addMeta("info", base.makeMetaValue("SSAP",
			type="info",
			infoName="SERVICE_PROTOCOL", infoValue=self.ssapVersion))
		return res


_SSA_SPEC_EXCEPTIONS = {
	"Dataset.Type": "Spectrum.Type",
	"Dataset.Length ": "Spectrum.Length",
	"Dataset.TimeSI": "Spectrum.TimeSI",
	"Dataset.SpectralSI": "Spectrum.SpectralSI",
	"Dataset.FluxSI": "Spectrum.FluxSI",
}


def makeSDMVOT(table, **votContextArgs):
	"""returns SDM-compliant xmlstan for a table containing an SDM-compliant
	spectrum.
	"""
	table.addMeta("_votableRootAttributes", 
		'xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01"')
	return votablewrite.makeVOTable(table, **votContextArgs)


def getSpecForSSA(utype):
	"""returns a utype from the spectrum data model for a utype of the ssa
	data model.

	For most utypes, this just removes a prefix and adds spec:Spectrum.  Heaven
	knows why these are two different data models anyway.  There are some
	(apparently random) differences, though.

	For convenience, utype=None is allowed and returned as such.
	"""
	if utype is None:
		return None
	localName = utype.split(":")[-1]
	specLocal = _SSA_SPEC_EXCEPTIONS.get(localName, "Spectrum."+localName)
	return "spec:"+specLocal


_SDM_TO_SED_UTYPES = {
	"spec:Data.SpectralAxis.Value": "sed:Segment.Points.SpectralCoord.Value",
	"spec:Data.FluxAxis.Value": "sed:Segment.Points.Flux.Value",
}

def hackSDMToSED(data):
	"""changes some utypes to make an SDM compliant data instance look a bit
	like one compliant to the sed data model.

	This is a quick hack to accomodate specview.  When there's a usable
	SED data model and we have actual data for it, add real support
	for it like there's for SDM.
	"""
	data.setMeta("utype", "sed:SED")
	table = data.getPrimaryTable()
	table.setMeta("utype", "sed:Segment")
	# copy the table definition to avoid clobbering the real attributes.
	# All this sucks.  At some point we'll want real SED support
	table.tableDef = table.tableDef.copy(table.tableDef.parent)
	for col in table.tableDef:
		if col.utype in _SDM_TO_SED_UTYPES:
			col.utype = _SDM_TO_SED_UTYPES[col.utype]
	for param in table.tableDef.params:
		if param.utype in _SDM_TO_SED_UTYPES:
			param.utype = _SDM_TO_SED_UTYPES[param.utype]


def formatSDMData(sdmData, inputTable, queryMeta):
	"""returns a pair of mime-type and payload for a rendering of the SDM
	Data instance sdmData replying to the request given in inputTable.
	"""
	destMime = inputTable.getParam("FORMAT") or "application/x-votable+xml"
	if queryMeta["tdEnc"] and destMime=="application/x-votable+xml":
		destMime = "application/x-votable+xml;encoding=tabledata"
	formatId = GETDATA_FORMATS.get(destMime, None)

	sdmTable = sdmData.getPrimaryTable()
	sdmData.addMeta("_votableRootAttributes", 
		'xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01"')

	if formatId is None:
		# special or unknown format
		raise base.ValidationError("Cannot format table to %s"%destMime)

	resF = StringIO()
	formats.formatData(formatId, sdmData, resF, acquireSamples=False)
	return (destMime, resF.getvalue())


def makeSDMDataForSSARow(ssaRow, spectrumData):
	"""returns a rsc.Data instance containing an SDM compliant spectrum
	for the spectrum described by ssaRow.

	spectrumData is a data element making a primary table containing
	the spectrum data from an SSA row (typically, this is going to be
	the tablesource property of an SSA service).
	"""
	resData = rsc.makeData(spectrumData, forceSource=ssaRow)
	resTable = resData.getPrimaryTable()
	resTable.setMeta("description",
		"Spectrum from %s"%products.makeProductLink(ssaRow["accref"]))
	# fudge accref  into a full URL
	resTable.setParam("accref",
		products.makeProductLink(resTable.getParam("accref")))
	return resData


def makeSDMDataForPUBDID(pubDID, ssaTD, spectrumData):
	"""returns a rsc.Table instance containing an SDM compliant spectrum
	for pubDID from ssaTable.

	ssaTD is the definition of a table containg the SSA metadata, 
	spectrumData is a data element making a primary table containing
	the spectrum data from an SSA row (typically, this is going to be
	the tablesource property of an SSA service).
	"""
	with base.getTableConn() as conn:
		ssaTable = rsc.TableForDef(ssaTD, connection=conn)
		matchingRows = list(ssaTable.iterQuery(ssaTable.tableDef, 
			"ssa_pubdid=%(pubdid)s", {"pubdid": pubDID}))
		if not matchingRows:
			raise svcs.UnknownURI("No spectrum with pubdid %s known here"%
				inputTable.getParam("pubdid"))
	return makeSDMDataForSSARow(matchingRows[0], spectrumData)


class SDMCore(svcs.Core):
	"""A core for making (VO)Tables according to the Spectral Data Model.

	Here, the input table consists of the accref of the table to be generated.
	The data child of an SDMVOTCore prescribes how to come up with the
	table.  The output table is the (primary) table of the data instance.

	You'll want to use these with the sdm renderer; it knows some little
	tricks we still need to add some attributes across the VOTable, and it will
	know how to create FITS files some day.
	"""
	name_ = "sdmCore"
	inputTableXML = """<inputTable id="inFields">
			<inputKey name="accref" type="text" required="True"
				description="Accref of the data within the SSAP table."/>
			<inputKey name="dm" type="text" description="Data model to
				generate the table for (sdm or sed)">sdm</inputKey>
		</inputTable>"""
	_queriedTable = base.ReferenceAttribute("queriedTable",
		default=base.Undefined, description="A reference to the SSAP table"
			" to search the accrefs in", copyable=True)
	_sdmDD = base.StructAttribute("sdmDD", default=base.Undefined,
		childFactory=rscdef.DataDescriptor,
		description="A data instance that builds the SDM table.  You'll need"
		" a custom or embedded grammar for those that accepts an SDM row"
		" as input.", copyable=True)

	def onElementComplete(self):
		self._onElementCompleteNext(SDMCore)
		if self.sdmDD.getMeta("utype", default=None) is None:
			self.sdmDD.setMeta("utype", "spec:Spectrum")

	def run(self, service, inputTable, queryMeta):
		with base.getTableConn() as conn:
			ssaTable = rsc.TableForDef(self.queriedTable, connection=conn)
			try:
				# XXX TODO: Figure out why the unquote here is required.
				accref = urllib.unquote(inputTable.getParam("accref"))
				res = list(ssaTable.iterQuery(ssaTable.tableDef, 
					"accref=%(accref)s", {"accref": accref}))
				if not res:
					raise svcs.UnknownURI("No spectrum with accref %s known here"%
						inputTable.getParam("accref"))
				ssaRow = res[0]
			finally:
				ssaTable.close()

		resData = makeSDMDataForSSARow(ssaRow, self.sdmDD)

		votContextArgs = {}
		if queryMeta["tdEnc"]:
			votContextArgs["tablecoding"] = "td"

		# This is for VOSpec, in particular the tablecoding; I guess once
		# we actually support the sed DM, this should go, and the
		# specview links should use sed dcc sourcePaths.
		if inputTable.getParam("dm")=="sed":
			hackSDMToSED(resData)
			votContextArgs["tablecoding"] = "td"

		return ("application/x-votable+xml",
			votable.asString(makeSDMVOT(resData, **votContextArgs)))


class SSAPProcessCore(SSAPCore):
	"""Temporary Hack; delete when ccd700 is ported to a sane infrastructure.
	"""
	name_ = "ssapProcessCore"
