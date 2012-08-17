"""
Code dealing with spectra (the actual data), in particular in the spectral
data model (sdm).
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


# MIME types we can generate from SDM-compliant data; the values are
# either keys for formats.formatData, or None if we have special
# handling below.
GETDATA_FORMATS = {
	"application/x-votable+xml": "votable",
	"application/x-votable+xml;encoding=tabledata": "votabletd",
	"text/plain": "tsv",
	"text/csv": "csv",
	"application/fits": None,
	"image/fits": None,}


_SSA_SPEC_EXCEPTIONS = {
	"Dataset.Type": "Spectrum.Type",
	"Dataset.Length ": "Spectrum.Length",
	"Dataset.TimeSI": "Spectrum.TimeSI",
	"Dataset.SpectralSI": "Spectrum.SpectralSI",
	"Dataset.FluxSI": "Spectrum.FluxSI",
}

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


################### Making SDM compliant tables (from SSA rows and
################### data descriptors making spectral data)
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


################## Serializing SDM compliant tables

def makeSDMVOT(table, **votContextArgs):
	"""returns SDM-compliant xmlstan for a table containing an SDM-compliant
	spectrum.
	"""
	table.addMeta("_votableRootAttributes", 
		'xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01"')
	return votablewrite.makeVOTable(table, **votContextArgs)


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


################## The SDM core (usable in dcc: accrefs).  Do we still
################## want this?

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
