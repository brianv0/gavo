"""
Interface to the VO Registry.
"""

import datetime
import time
import sys

from elementtree import ElementTree

from mx import DateTime

import gavo
from gavo import config
from gavo import resourcecache
from gavo import typesystems
from gavo.web import servicelist
from gavo.web.registrymodel import OAI, VOR, VOG, DC, RI, VS, SIA, SCS,\
	OAIDC, encoding
from gavo.web.vizierexprs import getSQLKey  # getSQLKey should be moved.


supportedMetadataPrefixes = [
# (prefix, schema-location, namespace)
	("oai_dc", "http://vo.ari.uni-heidelberg.de/docs/schemata/OAI-PMH.xsd",
		"http://www.openarchives.org/OAI/2.0/oai_dc/"),
	("ivo_vor", "http://vo.ari.uni-heidelberg.de/docs/schemata/"
		"VOResource-v1.0.xsd", "http://www.ivoa.net/xml/VOResource/v1.0"),
]

class OAIError(gavo.Error):
	"""is one of the standard OAI errors.
	"""

class BadArgument(OAIError): pass
class BadResumptionToken(OAIError): pass
class BadVerb(OAIError): pass
class CannotDisseminateFormat(OAIError): pass
class IdDoesNotExist(OAIError): pass
class NoRecordsMatch(OAIError): pass
class NoMetadataFormats(OAIError): pass
class NoSetHierarchy(OAIError): pass

_isoTimestampFmt = "%Y-%m-%dT%H:%M:%SZ"


def computeIdentifier(internalResource):
	return config.get("ivoa", "rootId")+"/"+internalResource.getMeta("shortName")


def getShortNameFromIdentifier(identifier):
	prefix = config.get("ivoa", "rootId")+"/"
	if not identifier.startswith(prefix):
		raise IdDoesNotExist(identifier)
	return identifier[len(prefix):]


def getServiceRecForIdentifier(identifier):
	"""returns the record for identifier in the services table.

	identifier always has to be of the form ivoa://<dc identifier>/shortName.
	"""
# XXX TODO: Think of sth for built-in or non-service records.
	matches = servicelist.getMatchingServices(
		"shortName=%(shortName)s",
		{"shortName": getShortNameFromIdentifier(identifier)})
	if len(matches.rows)!=1:
		raise IdDoesNotExist(identifier)
	return matches.rows[0]


def getResponseHeaders(pars):
	"""returns the OAI response header for a query with pars.
	"""
	return [
		OAI.responseDate[DateTime.now().strftime(_isoTimestampFmt)],
		OAI.request(verb=pars["verb"], 
				metadataPrefix=pars.get("metadataPrefix"))]


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
	return VOG.Resource(created=str(config.getMeta("registry.created")),
		status="active", updated=getRegistryDatestamp())[
			VOR.title["%s publishing registry"%config.get("web",
				"sitename")],
			VOR.shortName[config.getMeta("registry.shortName")],
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
			VOR.rights[config.getMeta("registry.rights")],
			VOG.Harvest[
				VOR.description[config.getMeta("registry.description")],
				VOG.OAIHTTP[
					VOR.accessURL[getRegistryURL()],
				],
				VOG.maxRecords["1000000"],
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
			pars["to"], sqlPars))
	if "set" in pars:
		sqlFrags.append("services.shortName IN %%(%s)s"%(getSQLKey("set",
			servicelist.getShortNamesForSets(pars["set"]), sqlPars)))
	else:
		sqlFrags.append("services.shortName IN %%(%s)s"%(getSQLKey("set",
			servicelist.getShortNamesForSets(["ivo_managed"]), sqlPars)))
	return servicelist.getMatchingServices(
		whereClause=" AND ".join(sqlFrags), pars=sqlPars)


def getDCResourceTree(rec):
	service = resourcecache.getRd(rec["sourceRd"]).get_service(
		rec["internalId"])
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			OAIDC.dc[
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
	]


def getDCResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getDCResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]


################ Functions to generate VO Resources

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
			[VOR.subject[subject] for subject in service.getAllMeta("subject")],
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
		[getTableParamFromField(f)
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


def getInputParamFromField(dataField, rootElement=VS.param):
	"""returns a InputParam element for dataField.
	"""
	type, length = typesystems.sqltypeToVOTable(dataField.get_dbtype())
	return rootElement[
			VS.name[dataField.get_source()],
			VS.description[dataField.get_description()],
			VS.unit[dataField.get_unit()],
			VS.ucd[dataField.get_ucd()],
			VS.simpleDataType[type]]


def getTableParamFromField(dataField, rootElement=VS.column):
	"""returns a InputParam element for dataField.
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
	return [getInputParamFromField(f) for f in service.getInputFields()]

_rendererParameters = {
	"siap.xml":  ("GET",  SIA.interface,  "application/x-votable"),
	"scs.xml":   ("GET",  SCS.interface,  "application/x-votable"),
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
	try:
		params = getParamItems(service)
	except Exception, msg:
		# quite a few things can go wrong here.  Since probably nobody cares
		# about these anyway, issue a warning and go on
		gavo.logger.warning("Cannot create parameter items for service %s: %s"%(
			service.getMeta("shortName"), str(msg)))
		params = []
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


def getPlainCapabilityTree(service):
	return VOR.capability[  
		# XXX add local description item -- where should this come from?
		getInterfaceTree(service, "form"),
		# XXX local validationLevel???
	]


def getCatalogServiceResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service, getPlainCapabilityTree(service)),
	]


def getDataServiceResourceTree(rec, service):
	return VS.DataService(**getResourceArgs(rec, service))[
		getDataServiceItems(service, getPlainCapabilityTree(service)),
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
#	sys.stderr.write(">>>> Returning %s service %s\n"%(makeResource[1], 
#		service.getMeta("shortName")))
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			makeResource[0](rec, service)
		]
	]


############## End functions to generate VO Resources


def getGetRecordTree(pars, rec, treeGenerator):
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.GetRecord[
			treeGenerator(rec),
		]
	]

def getVOGetRecordTree(pars, rec):
	return getGetRecordTree(pars, rec, getVOResourceTree)

def getDCGetRecordTree(pars, rec):
	return getGetRecordTree(pars, rec, getDCResourceTree)


def getVOResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getVOResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]


def dispatchOnPrefix(pars, OAIBuilder, VORBuilder, *args):
	"""dispatches to OAIBuilder or VORBuilder depending on metadataPrefix.
	"""
	if pars.get("metadataPrefix")=="ivo_vor":
		return VORBuilder(pars, *args)
	elif pars.get("metadataPrefix")=="oai_dc":
		return OAIBuilder(pars, *args)
	else:
		if "metadataPrefix" in pars:
			raise CannotDisseminateFormat("%s metadata are not supported"%pars[
				"metadataPrefix"])
		else:
			raise BadArgument("metadataPrefix missing")


############## Toplevel tree builders


def getListIdentifiersTree(pars):
	"""returns a tree of registrymodel Elements for a ListIdentifiers response.

	We don't have ivo specific metadata in the headers, so this ignores
	the metadata prefix.
	"""
	_ = pars["metadataPrefix"]  # just make sure we bomb out if it's missing
	ns = getMetadataNamespace(pars)
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListIdentifiers[
			[# the registry itself
			OAI.header[
				OAI.identifier[config.get("ivoa", "rootId")+"/DCRegistry"],
				OAI.datestamp[getRegistryDatestamp()],
				OAI.setSpec["ivo_managed"]], # XXX TODO: use real sets
			[getResourceHeaderTree(rec) for rec in getMatchingRecords(pars)]]
		]
	]


def getIdentifyTree(pars):
	"""returns a tree of registrymodel Elements for an Identify response.
	"""
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


def dispatchListRecordsTree(pars):
	"""returns a tree of registrymodel Elements for a ListRecords response.
	"""
	return dispatchOnPrefix(pars, getDCResourceListTree,
		getVOResourceListTree)


def dispatchGetRecordTree(pars):
	"""returns a tree of registrymodel Elements for a getRecord response.
	"""
	identifier = pars["identifier"]
	return dispatchOnPrefix(pars, getDCGetRecordTree,
		getVOGetRecordTree, getServiceRecForIdentifier(identifier))


def getListMetadataFormatTree(pars):
	"""returns a tree of registrymodel Elements for a
	listMetadataFormats response.
	"""
	# identifier is not ignored since crooks may be trying to verify the
	# existence of resource in this way, even though we should be able
	# to provide both supported metadata formats for all records.
	if pars.has_key("identifier"):
		getServiceRecForIdentifier(pars["identifier"])
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListMetadataFormats[[
			OAI.metadataFormat[
				OAI.metadataPrefix[prefix],
				OAI.schema[schema],
				OAI.metadataNamespace[ns],
			] 
		for prefix, schema, ns in supportedMetadataPrefixes]]
	]


def getListSetsTree(pars):
	"""returns a tree of registrymodel Elements for a ListSets response.
	"""
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListSets[[
			# Once we have better description of sets, add stuff here
			OAI.set[
				OAI.setSpec[set["setName"]],
				OAI.setName[set["setName"]],
			]
		for set in servicelist.getSets()]]
	]


pmhHandlers = {
	"GetRecord": dispatchGetRecordTree,
	"Identify": getIdentifyTree,
	"ListIdentifiers": getListIdentifiersTree,
	"ListMetadataFormats": getListMetadataFormatTree,
	"ListRecords": dispatchListRecordsTree,
	"ListSets": getListSetsTree,
}


def getPMHResponse(pars):
	"""returns an ElementTree containing a OAI-PMH response for the query 
	described by pars.
	"""
	verb = pars["verb"]
	try:
		handler = pmhHandlers[verb]
	except KeyError:
		raise BadVerb("'%s' is an unsupported operation."%pars["verb"])
	return ElementTree.ElementTree(handler(pars).asETree())


def getErrorTree(exception, pars):
	"""returns an ElementTree containing an OAI-PMH error response.

	If exception is one of "our" exceptions, we translate them to error
	messages, if it's a key error, we assume it's a parameter error (so
	don't let them leak otherwise).  If None of all this works out, we
	reraise the exception to an enclosing function may "handle" it.

	Contrary to the recommendation in the OAI-PMH spec, this will only
	return one error at a time.
	"""
	if isinstance(exception, OAIError):
		code = exception.__class__.__name__
		code = code[0].lower()+code[1:]
		message = str(exception)
	elif isinstance(exception, KeyError):
		code = "badArgument"
		message = "Missing mandatory argument %s"%str(exception)
	else:
		raise exception
	return ElementTree.ElementTree(OAI.PMH[
		OAI.responseDate[DateTime.now().strftime(_isoTimestampFmt)],
		OAI.request(verb=pars.get("verb", "Identify"), 
				metadataPrefix=pars.get("metadataPrefix")),
		OAI.error(code=code)[
			message
		]
	].asETree())


if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	from gavo.parsing import importparser  # for registration of getRd
	print ElementTree.tostring(getPMHResponse({"verb": "ListRecords", 
		"metadataPrefix": "ivo_vor", "set": ["local", "ivo_managed"]}).getroot(), encoding)
