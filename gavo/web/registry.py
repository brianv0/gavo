"""
Interface to the VO Registry.
"""

import datetime
import time

from elementtree import ElementTree

from mx import DateTime

from gavo import config
from gavo import resourcecache
from gavo.parsing import importparser  # for registration of getRd
from gavo.web import servicelist
from gavo.web.registrymodel import OAI, VOR, VOG, DC
from gavo.web.vizierexprs import getSQLKey  # getSQLKey should be moved.


def getResourceHeaderTree(rec):
	return OAI.header() [
		OAI.identifier()[config.get("ivoa", "rootId")+"/"+rec["shortName"]],
		OAI.datestamp()[rec["dateUpdated"].strftime("%Y-%m-%d")],
		# XXX TODO: The following is extremely inefficient
	][[OAI.setSpec()[setSpec] 
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
			VOR.title()["%s publishing registry"%config.get("web",
				"sitename")],
			VOR.identifier()[
				config.get("ivoa", "rootId")+"/DCRegistry"],
			VOR.curation()[
				VOR.publisher()[
					config.getMeta("curation.publisher")],
				VOR.contact()[
					VOR.name()[config.getMeta("curation.contact.name")],
					VOR.email()[config.getMeta("curation.contact.email")],
					VOR.telephone()[config.getMeta("curation.contact.telephone")],
					VOR.address()[config.getMeta("curation.contact.address")],
				],
			],
			VOR.content()[
				VOR.subject()["registry"],
				VOR.description()["%s publishing registry"%config.get("web",
					"sitename")],
				VOR.referenceURL()[getRegistryURL()],
				VOR.type()["Archive"]
			],
			VOR.interface(xsi_type="WebBrowser")[
				VOR.accessURL(use="full")[
					config.get("web", "serverURL")+
					config.get("web", "nevowRoot")+
					"/__system__/services/services/q/form"]
			],
			VOG.managedAuthority()[config.get("ivoa", "managedAuthority")],
		]


def getIdentifyTree(pars):
	return OAI.PMH()[
		OAI.responseDate()[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(metadataPrefix=pars.get("metadataPrefix", "oai_dc"),
			verb="Identify")[getRegistryURL()],
		OAI.Identify()[
			OAI.repositoryName()["%s publishing registry"%config.get("web",
				"serverURL")],
			OAI.baseURL()[getRegistryURL()],
			OAI.protocolVersion()["2.0"],
			OAI.adminEmail()[config.get("operator")],
			OAI.earliestDatestamp()["1970-01-01"],
			OAI.deletedRecord()["no"],
			OAI.granularity()["YYYY-MM-DDThh:mm:ssZ"],
		],
		OAI.description()[
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
	return OAI.PMH()[
		OAI.responseDate()[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(verb="Identify", 
				metadataPrefix=pars.get("metadataPrefix"))
			[getRegistryURL()],
		OAI.ListIdentifiers()[
			# the registry itself
			OAI.header()[
				OAI.identifier()[config.get("ivoa", "rootId")+"/DCRegistry"],
				OAI.datestamp()[getRegistryDatestamp()],
				OAI.setSpec()["ivo_managed"],
			][ # concatenate
			[getResourceHeaderTree(rec) for rec in recs]]
		]
	]


def getDCResourceTreeFor(rec):
	service = resourcecache.getRd(rec["sourceRd"]).get_service(
		rec["internalId"])
	return OAI.record()[
		getResourceHeaderTree(rec),
		OAI.metadata()[
			DC.title()[rec["title"]],
			DC.identifier()[config.get("ivoa", "rootId")+"/"+rec["shortName"]],
			DC.creator()[service.getMeta("creator")],
			DC.contributor()[service.getMeta("contributor")],
			DC.coverage()[service.getMeta("coverage")],
			DC.description()[service.getMeta("description")],
			DC.language()[service.getMeta("language")],
			DC.language()[service.getMeta("rights")],
			DC.publisher()[service.getMeta("publisher")],
		]
	]


def getDCResourceTree(pars):
	return OAI.PMH()[
		OAI.responseDate()[DateTime.now().strftime("%Y-%m-%d")],
		OAI.request(metadataPrefix="oai_dc", verb="ListRecords")[
			getRegistryURL()],
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords()[
			[getDCResourceTreeFor(rec)
				for rec in getMatchingRecords(pars)]]]
			

if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	print ElementTree.tostring(getDCResourceTree({"metadataPrefix": "ivo_vor"}).asETree())
