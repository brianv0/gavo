"""
Interface to the VO Registry.
"""

import datetime
import time

from elementtree import ElementTree

from mx import DateTime

from gavo import config
from gavo import resourcecache
from gavo import typesystems
from gavo.parsing import importparser  # for registration of getRd
from gavo.web import servicelist
from gavo.web.registrymodel import OAI, VOR, VOG, DC, RI, VOD, SIA, SCS
from gavo.web.vizierexprs import getSQLKey  # getSQLKey should be moved.


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
	# XXX TODO: Implement this (probably last call of gavopublish
	return "2007-12-13"


def getRegistryRecord():
	return VOR.Resource(created="2007-08-24", status="active",
		updated=getRegistryDatestamp(), xsi_type="vg:Registry")[
			VOR.title["%s publishing registry"%config.get("web",
				"sitename")],
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
					VOR.email[config.getMeta("curation.contact.email")],
					VOR.telephone[config.getMeta("curation.contact.telephone")],
					VOR.address[config.getMeta("curation.contact.address")],
				],
			],
			VOR.content[
				VOR.subject["registry"],
				VOR.description["%s publishing registry"%config.get("web",
					"sitename")],
				VOR.referenceURL[getRegistryURL()],
				VOR.type["Archive"]
			],
			VOR.interface(xsi_type="WebBrowser")[
				VOR.accessURL(use="full")[
					config.get("web", "serverURL")+
					config.get("web", "nevowRoot")+
					"/__system__/services/services/q/form"]
			],
			VOG.managedAuthority[config.get("ivoa", "managedAuthority")],
		]


def getIdentifyTree(pars):
	return OAI.PMH[
		OAI.responseDate[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(metadataPrefix=pars.get("metadataPrefix", "oai_dc"),
			verb="Identify")[getRegistryURL()],
		OAI.Identify[
			OAI.repositoryName["%s publishing registry"%config.get("web",
				"serverURL")],
			OAI.baseURL[getRegistryURL()],
			OAI.protocolVersion["2.0"],
			OAI.adminEmail[config.get("operator")],
			OAI.earliestDatestamp["1970-01-01"],
			OAI.deletedRecord["no"],
			OAI.granularity["YYYY-MM-DDThh:mm:ssZ"],
		],
		OAI.description[
			getRegistryRecord(),
		],
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
		OAI.responseDate[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(verb="Identify", 
				metadataPrefix=pars.get("metadataPrefix"))
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
			DC.publisher[service.getMeta("publisher")],
		]
	]


def getStandardServiceTree(service):
	"""returns the standard items for a VOResource service description.
	"""
	return [
		VOR.title[service.getMeta("title")],
		VOR.identifier[config.get("ivoa", "rootId")+"/"+str(service.getMeta(
			"shortName"))],
		VOR.curation[
			VOR.publisher[service.getMeta("publisher")],
			VOR.creator[
				VOR.name[service.getMeta("curation.creator.name")],
				VOR.logo[service.getMeta("curation.creator.logo")],
			],
			VOR.contact[
				VOR.name[service.getMeta("curation.contact.name")],
				VOR.email[service.getMeta("curation.contact.email")],
				VOR.telephone[service.getMeta("curation.contact.telephone")],
				VOR.address[service.getMeta("curation.contact.address")],
			],
		],
		VOR.content[
			VOR.subject[service.getMeta("subject")],
			VOR.description[service.getMeta("description")],
			VOR.referenceURL[service.getMeta("referenceURL")],
			VOR.type[service.getMeta("type")],
		]
	]


def getParamFromField(dataField, rootElement=VOD.param):
	"""returns a param element for dataField.
	"""
	type, length = typesystems.sqltypeToVOTable(dataField.get_dbtype())
	return rootElement[
			VOD.description[dataField.get_description()],
			VOD.name[dataField.get_source()],
			VOD.ucd[dataField.get_ucd()],
			VOD.unit[dataField.get_unit()],
			VOD.dataType(arraysize=length)[type]]

def getParamItems(service):
	"""returns a sequence of vs:param elements for the input of service.
	"""
	return [getParamFromField(f) for f in service.getInputFields()]


rendererParameters = {
# qtype (GET/POST), xsi_type, urlComputer, resultType
# where xsi_type includes cs:ConeSearch, vs:ParamHTTP, vs:WebService,
# sia:SimpleImageAccess and potentially many others.
	"siap.xml":  ("GET",  "sia:SimpleImageAccess", "application/x-votable"),
	"scs.xml":   ("GET",  "cs:ConeSearch",         "application/x-votable"),
	"form":      ("POST", "vs:ParamHTTP",          "text/html"),
	"upload":    ("POST", "vs:ParamHTTP",          "text/html"),
	"mupload":   ("POST", "vs:ParamHTTP",          "text/plain"),
	"img.jpeg":  ("POST", "vs:ParamHTTP",          "image/jpeg"),
	"mimg.jpeg": ("GET",  "vs:ParamHTTP",          "image/jpeg"),
}

def getInterfacesTree(service):
	"""returns a sequence of the interfaces available on service.

	Unfortunately, our model is a bit at odds with the data model here,
	since, e.g., we don't really speak SIAP on the html renderers of a siap 
	service.  We try to make good by specifying the result type (which
	is silly since the html frontents can deliver VOTables) and the
	qtype (which is silly since all services respond to POST as well as
	GET).
	"""
	params = getParamItems(service)
	def getInterface(service, publication):
		qtype, xsi_type, resultType = rendererParameters[
			publication["render"]]
		use = "full"
		if qtype=="GET":
			use = "base"
		return VOR.interface(qtype=qtype, xsi_type=xsi_type)[
			VOR.accessURL(use=use)[service.getURL(publication["render"], qtype)],
			VOD.resultType[resultType],
			params,
		]
	return [getInterface(service, publication) 
		for publication in service.get_publications()]


def getSiaCapabilitiesTree(service):
	return SIA.capability[
		SIA.imageServiceType[service.getMeta("sia.type")],
			SIA.maxQueryRegionSize[
				SIA.long[service.getMeta("sia.maxQueryRegionSize.long", default=360)],
				SIA.lat[service.getMeta("sia.maxQueryRegionSize.lat", default=360)],
			],
			SIA.maxImageExtent[
				SIA.long[service.getMeta("sia.maxImageExtent.long", default=360)],
				SIA.lat[service.getMeta("sia.maxImageExtent.lat", default=360)],
			],
			SIA.maxImageSize[
				SIA.long[service.getMeta("sia.maxImageSize.long")],
				SIA.lat[service.getMeta("sia.maxImageSize.lat")],
			],
			SIA.maxFileSize[
				service.getMeta("sia.maxFileSize"),
			],
			SIA.maxRecords[
				service.getMeta("sia.maxRecords"),
			]
		]


def getResponseTableTree(service):
	return VOD.table(role="out")[
		[getParamFromField(f, rootElement=VOD.column)
			for f in service.getOutputFields(None)]
	]


def getSiapResourceTree(rec, service):
	return VOR.Resource(xsi_type="sia:SimpleImageAccess")[
		getStandardServiceTree(service),
		getInterfacesTree(service),
		getSiaCapabilitiesTree(service),
	]


def getScsResourceTree(rec, service):
	return VOR.Resource(xsi_type="scs:ConeSearch")[
		getStandardServiceTree(service),
		getInterfacesTree(service),
		getScsCapabilitiesTree(service),
	]


def getTabularServiceResourceTree(rec, service):
	return VOR.Resource(xsi_type="vs:TabularSkyService")[
		getStandardServiceTree(service),
		getInterfacesTree(service),
		getResponseTableTree(service),
	]


def getOtherServiceResourceTree(rec, service):
	return VOD.Resource[
		getStandardServiceTree(service),
		getInterfacesTree(service),
	]


resourceMakers = {
	"siap.xml": getSiapResourceTree,
	"scs.xml": getScsResourceTree,
	"form": getTabularServiceResourceTree,
}

def getVOResourceTree(rec):
	"""returns a tree for an individual resource described by the service table
	record rec.

	The trouble here is that we need to decide on the xsi type of the Resource
	record.  That's trouble because we may in principle have multiple
	conflicting interfaces on a service.  In practice, it's probably not so
	bad (who'd want to look at SIAP output?), so we simply take the first
	renderer matching a standard DAL protocol. 

	However, form renderers probably always count as TabularSkyServices,
	so in these cases we simply "upgrade" the default from OtherService
	to TabularSkyService.
	"""
	service = resourcecache.getRd(rec["sourceRd"]).get_service(
		rec["internalId"])
	makeResource = getOtherServiceResourceTree
	for pub in service.get_publications():
		if pub["render"] in resourceMakers:
			makeResource = resourceMakers[pub["render"]]
			break
		if pub["render"]=="form":
			makeResource = getTabularServiceResourceTree(rec, service)
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			makeResource(rec, service)
		]
	]


def getDCResourceListTree(pars):
	return OAI.PMH[
		OAI.responseDate[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(metadataPrefix="oai_dc", verb="ListRecords")[
			getRegistryURL()],
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getDCResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]
			

def getVOResourceListTree(pars):
	return OAI.PMH[
		OAI.responseDate[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(metadataPrefix="ivo_vor", verb="ListRecords")[
			getRegistryURL()],
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getVOResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]
			


if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	print ElementTree.tostring(getVOResourceListTree({}).asETree())
