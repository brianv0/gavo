"""
Code dealing with spectra (the actual data), in particular in the spectral
data model (sdm).
"""

import datetime
import os
import urllib
from cStringIO import StringIO

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo import votable
from gavo.formats import fitstable
from gavo.formats import votablewrite
from gavo.protocols import products
from gavo.utils import pyfits


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


################## Special FITS hacks for SDM serialization

def _add_target_pos_cards(header, par):
	"""_SDM_HEADER_MAPPING for target.pos.
	"""
	header.update("RA_TARG", par.value.x/utils.DEG)
	header.update("DEC_TARG", par.value.y/utils.DEG)


def _add_location_cards(header, par):
	"""_SDM_HEADER_MAPPING for target.pos.
	"""
	header.update("RA", par.value.x/utils.DEG)
	header.update("DEC", par.value.y/utils.DEG)


# A mapping from utypes to the corresponding FITS keywords
# There are some more complex cases, for which a function is a value
# here; the funciton is called with the FITS header and the parameter
# in question.
_SDM_HEADER_MAPPING = {
	"datamodel": "VOCLASS",
	"length": "DATALEN",
	"type": "VOSEGT",
	"coordsys.id": "VOCSID",
	"coordsys.spaceframe.name": "RADECSYS",
	"coordsys.spaceframe.equinox": "EQUINOX",
	"coordsys.spaceframe.ucd": "SKY_UCD",
	"coordsys.spaceframe.refpos": "SKY_REF",
	"coordsys.timeframe.name": "TIMESYS",
	"coordsys.timeframe.ucd": None,
	"coordsys.timeframe.zero": "MJDREF",
	"coordsys.timeframe.refpos": None,
	"coordsys.spectralframe.refpos": "SPECSYS",
	"coordsys.spectralframe.redshift": "REST_Z",
	"coordsys.spectralframe.name": "SPECNAME",
	"coordsys.redshiftframe.name": "ZNAME",
	"coordsys.redshiftframe.refpos": "SPECSYSZ",
	"curation.publisher": "VOPUB",
	"curation.reference": "VOREF",
	"curation.publisherid": "VOPUBID",
	"curation.version": "VOVER",
	"curation.contactname": "CONTACT",
	"curation.contactemail": "EMAIL",
	"curation.rights": "VORIGHTS",
	"curation.date": "VODATE",
	"curation.publisherdid": "DS_IDPUB",
	"target.name": "OBJECT",
	"target.description": "OBJDESC",
	"target.class": "SRCCLASS",
	"target.spectralclass": "SPECTYPE",
	"target.redshift": "REDSHIFT",
	"target.varampl": "TARGVAR",
	"dataid.title": "TITLE",
	"dataid.creator": "AUTHOR",
	"dataid.datasetid": "DS_IDENT",
	"dataid.creatordid": "CR_IDENT",
	"dataid.date": "DATE",
	"dataid.version": "VERSION",
	"dataid.instrument": "INSTRUME",
	"dataid.creationtype": "CRETYPE",
	"dataid.logo": "VOLOGO",
# collection will need work when we properly implement it
	"dataid.collection": "COLLECT1",
	"dataid.contributor": "CONTRIB1",
	"dataid.datasource": "DSSOURCE",
	"dataid.bandpass": "SPECBAND",
	"derived.snr": "DER_SNR",
	"derived.redshift.value": "DER_Z",
	"derived.redshift.staterror": "DER_ZERR",
	"derived.redshift.confidence": "DER_ZCNF",
	"derived.varampl": "DER_VAR",
	"timesi": "TIMESDIM",
	"spectralsi": "SPECSDIM",
	"fluxsi": "FLUXSDIM",
	"char.fluxaxis.name": None,
	"char.fluxaxis.unit": None,
	"char.fluxaxis.ucd": None,
	"char.spectralaxis.name": None,
	"char.spectralaxis.unit": None,
	"char.spectralaxis.ucd": None,
	"char.timeaxis.name": None,
	"char.timeaxis.ucd": None,
	"char.spatialaxis.name": None,
	"char.spatialaxis.unit": None,
	"char.fluxaxis.accuracy.staterror": "STAT_ERR",
	"char.fluxaxis.accuracy.syserror": "SYS_ERR",
	"char.timeaxis.accuracy.staterror": "TIME_ERR",
	"char.timeaxis.accuracy.syserror": "TIME_SYE",
	"char.timeaxis.resolution": "TIME_RES",
	"char.fluxaxis.calibration": "FLUX_CAL",
	"char.spectralaxis.calibration": "SPEC_CAL",
	"char.spectralaxis.coverage.location.value": "SPEC_VAL",
	"char.spectralaxis.coverage.bounds.extent": "SPEC_BW",
	"char.spectralaxis.samplingprecision.": None,
	"samplingprecisionrefval.fillfactor": "SPEC_FIL",
	"char.spectralaxis.samplingprecision.SampleExtent": "SPEC BIN",
	"char.spectralaxis.accuracy.binsize": "SPEC_BIN",
	"char.spectralaxis.accuracy.staterror": "SPEC_ERR",
	"char.spectralaxis.accuracy.syserror": "SPEC_SYE",
	"char.spectralaxis.resolution": "SPEC_RES",
	"char.spectralaxis.respower": "SPEC_RP",
	"char.spectralaxis.coverage.support.extent": "SPECWID",
	"char.timeaxis.unit": "TIMEUNIT",
	"char.timeaxis.accuracy.binsize": "TIMEDEL",
	"char.timeaxis.calibration": "TIME_CAL",
	"char.timeaxis.coverage.location.value": "TMID",
	"char.timeaxis.coverage.bounds.extent": "TELAPSE",
	"char.timeaxis.coverage.bounds.start": "TSTART",
	"char.timeaxis.coverage.bounds.stop": "TSTOP",
	"char.timeaxis.coverage.support.extent": "EXPOSURE",
	"char.timeaxis.samplingprecision.samplingprecisionrefval.fillfactor": "DTCOR",
	"char.timeaxis.samplingprecision.sampleextent": "TIMEDEL",
	"char.spatialaxis.ucd": "SKY_UCD",
	"char.spatialaxis.accuracy.staterr": "SKY_ERR",
	"char.spatialaxis.accuracy.syserror": "SKY_SYE",
	"char.spatialaxis.calibration": "SKY_CAL",
	"char.spatialaxis.resolution": "SKY_RES",
	"char.spatialaxis.coverage.bounds.extent": "APERTURE",
	"char.spatialaxis.coverage.support.area": "REGION",
	"char.spatialaxis.coverage.support.extent": "AREA",
	"char.spatialaxis.samplingprecision.samplingprecisionrefval.fillfactor": 
		"SKY_FILL",
	
	# special handling through functions
	"target.pos": _add_target_pos_cards,
	"char.spatialaxis.coverage.location.value": _add_location_cards,
}

def makeBasicSDMHeader(sdmData):
	"""returns a pyfits header containing the SDM header fields common to
	standard and image serialization.
	"""
	header = pyfits.Header()
	for par in sdmData.getPrimaryTable().iterParams():
		if par.value is None or par.utype is None:
			continue
		
		mapKey = par.utype.lower().split(":")[-1]
		if mapKey.startswith("spectrum."):  # WTF?
			mapKey = mapKey[9:]

		destKey = _SDM_HEADER_MAPPING.get(mapKey, None)
		if destKey is None:
			pass
		elif callable(destKey):
			destKey(header, par)
		else:
			comment = ""
			if par.unit:
				comment = str("[%s]"%par.unit)

			# Use our serializing infrastructure here?
			value = par.value
			if isinstance(value, unicode):
				value = value.encode("ascii", "ignore")
			elif isinstance(value, datetime.datetime):
				value = value.isoformat()

			header.update(destKey, value, comment)
	
	return header


def makeSDMFITS(sdmData):
	"""returns sdmData in an SDM-compliant FITS.
	"""
	hdus = fitstable.makeFITSTable(sdmData)
	sdmHdr = hdus[1].header
	for card in makeBasicSDMHeader(sdmData).ascardlist():
		sdmHdr.update(card.key, card.value, card.comment)
	srcName = fitstable.writeFITSTableFile(hdus)
	with open(srcName) as f:
		data = f.read()
	os.unlink(srcName)
	return data


################## Serializing SDM compliant tables

def makeSDMVOT(table, **votContextArgs):
	"""returns SDM-compliant xmlstan for a table containing an SDM-compliant
	spectrum.
	"""
	table.addMeta("_votableRootAttributes", 
		'xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01"')
	return votablewrite.makeVOTable(table, **votContextArgs)


def formatSDMData(sdmData, format, queryMeta=svcs.emptyQueryMeta):
	"""returns a pair of mime-type and payload for a rendering of the SDM
	Data instance sdmData in format.
	"""
	destMime =  format or "application/x-votable+xml"
	if queryMeta["tdEnc"] and destMime=="application/x-votable+xml":
		destMime = "application/x-votable+xml;encoding=tabledata"
	formatId = GETDATA_FORMATS.get(destMime, None)

	sdmTable = sdmData.getPrimaryTable()
	sdmData.addMeta("_votableRootAttributes", 
		'xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01"')

	if formatId is None:
		# special or unknown format
		if destMime=="application/fits":
			return destMime, makeSDMFITS(sdmData)
		else:
			raise base.ValidationError("Cannot format table to %s"%destMime,
				"FORMAT")
		
	resF = StringIO()
	formats.formatData(formatId, sdmData, resF, acquireSamples=False)
	return destMime, resF.getvalue()


################## Manipulation of SDM compliant tables
# The idea here is that you can push in a table, the function does some
# magic, and it returns that table.  The getData implementation (see ssap.py)
# uses these functions to provide some spectrum transformations.  We
# may want to provide some plugin system so people can add their own
# transformations, but let's first see someone request that.

def mangle_cutout(sdmTable, low, high):
	"""returns only those rows from sdmTable for which the spectral coordinate
	is between low and high.

	Both low and high must be given.  If you actually want half-open intervals,
	do it in interface code (low=-1 and high=1e308 should do fine).
	"""
	spectralName = sdmTable.tableDef.getByUtype(
		"spec:Data.SpectralAxis.Value").name
	return rsc.TableForDef(sdmTable.tableDef,
		rows=[row for row in sdmTable.rows if low<=row[spectralName]<=high])


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
