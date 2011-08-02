"""
The SSAP core and supporting code.

"""

import urllib
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import products
from gavo.svcs import outputdef
from gavo.votable import V


RD_ID = "//ssap"

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
		inputTable = self.inputTable
		inParams =[votablewrite.makeFieldFromColumn(V.PARAM, param)
			for param in inputTable.params]
		for p in inParams:
			p.name = "INPUT:"+p.name

		emptyTable = rsc.TableForDef(self.outputTable)
		ctx = votablewrite.VOTableContext()

		vot = V.VOTABLE[
			V.RESOURCE(type="meta")[
				V.DESCRIPTION[
					base.getMetaText(service, "description")],
				V.INFO(name="QUERY_STATUS", value="OK"), [
					inParams,
					votablewrite.makeTable(ctx, emptyTable)],
				V.INFO(name="SERVICE_PROTOCOL", value="1.04")[
					"SSAP"]]]

		res =  StringIO()
		votable.write(vot, res)
		return "application/x-votable+xml", res.getvalue()

	def run(self, service, inputTable, queryMeta):
		if inputTable.getParam("REQUEST")!="queryData":
			raise base.ValidationError("Only queryData operation supported so"
				" far for SSAP.", "REQUEST")
		if inputTable.getParam("FORMAT")=="METADATA":
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
		ssaTable = rsc.TableForDef(self.queriedTable,
			connection=base.caches.getTableConn(None))
		try:
			# XXX TODO: Figure why the unquote here is required.
			accref = urllib.unquote(inputTable.getParam("accref"))
			res = list(ssaTable.iterQuery(ssaTable.tableDef, 
				"accref=%(accref)s", {"accref": accref}))
			if not res:
				raise svcs.UnknownURI("No spectrum with accref %s known here"%
					inputTable.getParam("accref"))
			ssaRow = res[0]
		finally:
			ssaTable.close()

		resData = rsc.makeData(self.sdmDD, forceSource=ssaRow)
		resData.getPrimaryTable().setMeta("description",
			"Spectrum from %s"%products.makeProductLink(accref))

		votContextArgs = {}
		if queryMeta["tdEnc"]:
			votContextArgs["tablecoding"] = "td"

		if inputTable.getParam("dm")=="sed":
			hackSDMToSED(resData)
			votContextArgs["tablecoding"] = "td"

		return ("application/x-votable+xml",
			votable.asString(makeSDMVOT(resData, **votContextArgs)))
