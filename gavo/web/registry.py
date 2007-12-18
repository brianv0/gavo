"""
Interface to the VO Registry.
"""

import datetime
import time
import sys

from elementtree import ElementTree

from mx import DateTime

from gavo import config
from gavo import resourcecache
from gavo import typesystems
from gavo.parsing import importparser  # for registration of getRd
from gavo.web import servicelist
from gavo.web.registrymodel import OAI, VOR, VOG, DC, RI, VS, SIA, SCS,\
	encoding
from gavo.web.vizierexprs import getSQLKey  # getSQLKey should be moved.


_isoTimestampFmt = "%Y-%m-%dT%H:%M:%SZ"


def getResponseHeaders(pars):
	"""returns the OAI response header for a query with pars.
	"""
	return [
		OAI.responseDate[DateTime.now().strftime(_isoTimestampFmt)],
		OAI.request(verb=pars["verb"], 
				metadataPrefix=pars["metadataPrefix"])]


def getResourceHeaderTree(rec):
	return OAI.header [
		OAI.identifier[config.get("ivoa", "rootId")+"/"+rec["shortName"]],
		OAI.datestamp[rec["dateUpdated"].strftime("%Y-%m-%d")],
		# XXX TODO: The following is extremely inefficient
	][[OAI.setSpec[setSpec] 
		for setSpec in servicelist.getSetsForService(rec["shortName"])]]


def getRegistryURL():
	return (config.get("web", "serverURL")+
		config.get("web", "nevowRoot")+"/registry")


def getRegistryDatestamp():
	# XXX TODO: Implement this (probably last call of gavopublish)
	return "2007-12-13T12:00:00Z"


def getRegistryRecord():
	return VOG.Resource(created="2007-08-24T12:00:00Z", status="active",
		updated=getRegistryDatestamp())[
			VOR.title["%s publishing registry"%config.get("web",
				"sitename")],
			VOR.shortName["GAVO oai intf"],
			VOR.identifier[
				config.get("ivoa", "rootId")+"/DCRegistry"],
			VOR.curation[
				VOR.publisher[
					config.getMeta("curation.publisher")],
				VOR.creator[
					VOR.name[config.getMeta("curation.creator.name")],
					VOR.logo[config.getMeta("curation.creator.logo")],
				],
				VOR.contact[
					VOR.name[config.getMeta("curation.contact.name")],
					VOR.address[config.getMeta("curation.contact.address")],
					VOR.email[config.getMeta("curation.contact.email")],
					VOR.telephone[config.getMeta("curation.contact.telephone")],
				],
			],
			VOR.content[
				VOR.subject["registry"],
				VOR.description["%s publishing registry"%config.get("web",
					"sitename")],
				VOR.referenceURL[getRegistryURL()],
				VOR.type["Archive"]
			],
			VOG.full["false"],
			VOG.managedAuthority[config.get("ivoa", "managedAuthority")],
		]


def getMetadataNamespace(pars):
	"""returns an object that contains element definitions for resource
	records according to the metadataPrefix item in pars.
	"""
	return {
		"oai_dc": OAI,
		"ivo_vor": VOR,
	}[pars.get("metadataPrefix", "oai_dc")]


def getMatchingRecords(pars):
	"""returns a list of records from the service list matching pars.

	pars is a dictionary mapping any of the following keys to values:

	* from
	* to -- these give a range for which changed records are being returned
	* set -- maps to a sequence of set names to be matched.

	Functions using this probably want to interpret

	* metadataPrefix -- the format the data should be returned in.
	"""
	sqlPars, sqlFrags = {}, []
	if "from" in pars:
		sqlFrags.append("services.dateUpdated > %%(%s)s"%getSQLKey("from",
			pars["from"], sqlPars))
	if "to" in pars:
		sqlFrags.append("services.dateUpdated > %%(%s)s"%getSQLKey("to",
			pars["from"], sqlPars))
	if "set" in pars:
		sqlFrags.append("services.shortName IN %%(%s)s"%(getSQLKey("set",
			servicelist.getShortNamesForSets(pars["set"]), sqlPars)))
	else:
		sqlFrags.append("services.shortName IN %%(%s)s"%(getSQLKey("set",
			servicelist.getShortNamesForSets(["ivo_managed"]), sqlPars)))
	return servicelist.getMatchingServices(
		whereClause=" AND ".join(sqlFrags), pars=sqlPars)


def getListIdentifiersTree(pars):
	"""returns a registrymodel tree for a ListIdentifiers query.

	pars is a dictionary mapping parameters to their values.
	See getMatchingRecords for the standard ones.
	"""
	ns = getMetadataNamespace(pars)
	recs = getMatchingRecords(pars)
	return OAI.PMH[
			[getRegistryURL()],
		OAI.ListIdentifiers[
			# the registry itself
			OAI.header[
				OAI.identifier[config.get("ivoa", "rootId")+"/DCRegistry"],
				OAI.datestamp[getRegistryDatestamp()],
				OAI.setSpec["ivo_managed"],
			][ # concatenate
			[getResourceHeaderTree(rec) for rec in recs]]
		]
	]


def getDCResourceTree(rec):
	service = resourcecache.getRd(rec["sourceRd"]).get_service(
		rec["internalId"])
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			DC.title[rec["title"]],
			DC.identifier[config.get("ivoa", "rootId")+"/"+rec["shortName"]],
			DC.creator[service.getMeta("creator.name")],
			DC.contributor[service.getMeta("contributor.name")],
			DC.coverage[service.getMeta("coverage")],
			DC.description[service.getMeta("description")],
			DC.language[service.getMeta("language")],
			DC.language[service.getMeta("rights")],
			DC.publisher[service.getMeta("curation.publisher")],
		]
	]


def getServiceItems(service):
	"""returns a sequence of elements making up a plain VOResource service 
	description.

	This returns all items up to but excluding capabilities.  These need to
	be filled in by specialized functions depending on the service type.
	"""
	return [
		VOR.validationLevel(validatedBy=service.getMeta("validatedBy"))[
			service.getMeta("validationLevel")],
		VOR.title[service.getMeta("title")],
		VOR.shortName[service.getMeta("shortName")],
		VOR.identifier[config.get("ivoa", "rootId")+"/"+str(service.getMeta(
			"shortName"))],
		VOR.curation[
			VOR.publisher[service.getMeta("curation.publisher")],
			VOR.creator[
				VOR.name[service.getMeta("curation.creator.name")],
				VOR.logo[service.getMeta("curation.creator.logo")],
			],
			VOR.contact[
				VOR.name[service.getMeta("curation.contact.name")],
				VOR.address[service.getMeta("curation.contact.address")],
				VOR.email[service.getMeta("curation.contact.email")],
				VOR.telephone[service.getMeta("curation.contact.telephone")],
			],
		],
		VOR.content[
			VOR.subject[service.getMeta("subject")],
			VOR.description[service.getMeta("description")],
			VOR.source[service.getMeta("source")],
			VOR.referenceURL[service.getMeta("referenceURL", default=
				service.getURL("form", "POST"))],
			VOR.type[service.getMeta("type")],
			VOR.contentLevel[service.getMeta("contentLevel")],
			VOR.relationship[service.getMeta("relationship")],
		],
		VOR.rights[
			service.getMeta("rights"),
		],
	]


def getResponseTableTree(service):
	return VS.table(role="out")[
		[getParamFromField(f, rootElement=VS.column)
			for f in service.getOutputFields(None)]
	]


def getCatalogServiceItems(service, capabilities):
	"""returns a sequence of elements for a CatalogService based on service
	with capabilities.
	"""
	return getServiceItems(service)+[capabilities]+[
		VOR.facility[ # XXX TODO: maybe look up ivo-ids?
			service.getMeta("facility")],
		VOR.instrument[service.getMeta("instrument")],
		VS.coverage[service.getMeta("coverage")],  # XXX TODO: figure out how
			# to splice in multiple structured elements.
		getResponseTableTree(service),
	]
		

def getDataServiceItems(service, capabilities):
	"""returns a sequence of elements for a DataService based on service
	with capabilities.
	"""
	return getServiceItems(service)+[capabilities]+[
		VOR.facility[ # XXX TODO: maybe look up ivo-ids?
			service.getMeta("facility")],
		VOR.instrument[service.getMeta("instrument")],
		VS.coverage[service.getMeta("coverage")],  # XXX TODO: figure out how
			# to splice in multiple structured elements.
	]


def getParamFromField(dataField, rootElement=VS.param):
	"""returns a param element for dataField.
	"""
	type, length = typesystems.sqltypeToVOTable(dataField.get_dbtype())
	return rootElement[
			VS.name[dataField.get_source()],
			VS.description[dataField.get_description()],
			VS.unit[dataField.get_unit()],
			VS.ucd[dataField.get_ucd()],
			VS.dataType(arraysize=length)[type]]


def getParamItems(service):
	"""returns a sequence of vs:param elements for the input of service.
	"""
	return [getParamFromField(f) for f in service.getInputFields()]

_rendererParameters = {
	"siap.xml":  ("GET",  SIA.interface,  "application/x-votable"),
	"scs.xml":   ("GET",  SCS.interface,   "application/x-votable"),
	"form":      ("POST", VS.ParamHTTP,   "text/html"),
	"upload":    ("POST", VS.ParamHTTP,   "text/html"),
	"mupload":   ("POST", VS.ParamHTTP,   "text/plain"),
	"img.jpeg":  ("POST", VS.ParamHTTP,   "image/jpeg"),
	"mimg.jpeg": ("GET",  VS.ParamHTTP,   "image/jpeg"),
}

def getInterfaceTree(service, renderer):
	qtype, interfaceFactory, resultType = _rendererParameters[renderer]
	use = "full"
	if qtype=="GET":
		use = "base"
	params = getParamItems(service)
	return interfaceFactory[
		VOR.accessURL(use=use)[service.getURL(renderer, qtype)],
		VOR.securityMethod(standardId=service.getMeta("securityId")),
		VS.resultType[resultType],
		params,
	]


def getResourceArgs(rec, service):
	"""returns the mandatory attributes for constructing a Resource record
	for service in a dictionary.
	"""
	return {
		"created": service.getMeta("creationDate", default="2000-01-01T00:00:00Z"),
		"updated": rec["dateUpdated"].strftime(_isoTimestampFmt),
		"status": "active",
	}


def getSiaCapabilitiesTree(service):
	return SIA.capability[
		getInterfaceTree(service, "siap.xml"),
		SIA.imageServiceType[service.getMeta("sia.type")],
			SIA.maxQueryRegionSize[
				SIA.long[service.getMeta("sia.maxQueryRegionSize.long", default="360")],
				SIA.lat[service.getMeta("sia.maxQueryRegionSize.lat", default="360")],
			],
			SIA.maxImageExtent[
				SIA.long[service.getMeta("sia.maxImageExtent.long", default="360")],
				SIA.lat[service.getMeta("sia.maxImageExtent.lat", default="360")],
			],
			SIA.maxImageSize[
				SIA.long[service.getMeta("sia.maxImageSize.long", default="100000")],
				SIA.lat[service.getMeta("sia.maxImageSize.lat", default="1000000")],
			],
			SIA.maxFileSize[
				service.getMeta("sia.maxFileSize", default="2000000000"),
			],
			SIA.maxRecords[
				service.getMeta("sia.maxRecords", default="200000000"),
			]
		]


def getSiapResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service,
			getSiaCapabilitiesTree(service)),
	]


def getScsResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service,
			getScsCapabilitiesTree(service)),
	]


def getCatalogServiceCapabilityTree(service):
	return VOR.capability[  
		# XXX add local description item -- where should this come from?
		getIterfaceTree("service", "form"),
		# XXX local validationLevel???
	]


def getCatalogServiceResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service, []),
	]


def getDataServiceResourceTree(rec, service):
	return VS.DataService(**getResourceArgs(rec, service))[
		getDataServiceItems(service, []),
	]


resourceMakers = {
	"siap.xml": (getSiapResourceTree, "siap"),
	"scs.xml": (getScsResourceTree, "cs"),
}

def getVOResourceTree(rec):
	"""returns a tree for an individual resource described by the service table
	record rec.

	The trouble here is that we need to decide on the xsi type of the Resource
	record.  That's trouble because we may in principle have multiple
	conflicting interfaces on a service.  In practice, it's probably not so
	bad (who'd want to look at SIAP output?), so we simply take the first
	renderer matching a standard DAL protocol. 

	However, form renderers probably always count as TableServices,
	so in these cases we simply "upgrade" the default from DataService
	to TableService. XXX TODO: That's rubbish.  What about jpeg, upload?
	"""
	service = resourcecache.getRd(rec["sourceRd"]).get_service(
		rec["internalId"])
	makeResource = getDataServiceResourceTree, "data"
	for pub in service.get_publications():
		if pub["render"] in resourceMakers:
			makeResource = resourceMakers[pub["render"]]
			break
		if pub["render"]=="form":
			makeResource = (getCatalogServiceResourceTree, "tabular")
	sys.stderr.write(">>>> Returning %s service %s\n"%(makeResource[1], 
		service.getMeta("shortName")))
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			makeResource[0](rec, service)
		]
	]


def getDCResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getDCResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]
			

def getVOResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getVOResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]
			

def getIdentifyTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.Identify[
			OAI.repositoryName["%s publishing registry"%config.get("web",
				"sitename")],
			OAI.baseURL[getRegistryURL()],
			OAI.protocolVersion["2.0"],
			OAI.adminEmail[config.get("operator")],
			OAI.earliestDatestamp["1970-01-01"],
			OAI.deletedRecord["no"],
			OAI.granularity["YYYY-MM-DDThh:mm:ssZ"],
			OAI.description[
				getRegistryRecord(),
			],
		],
	]


if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	print ElementTree.tostring(getVOResourceListTree({"verb": "ListRecords", "metadataPrefix": "ivo_vor", "set": ["local", "ivo_managed"]}).asETree(), encoding)
