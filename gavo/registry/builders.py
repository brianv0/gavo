"""
Functions returning xmlstan for various OAI/VOR documents.

This comprises basic VOResource elements; capabilities and interfaces
(i.e. everything to do with renderers) are in registry.capabilities.
"""

import traceback
import warnings

from gavo import base
from gavo import utils
from gavo.base import meta
from gavo.registry import capabilities
from gavo.registry import identifiers
from gavo.registry import servicelist
from gavo.registry.common import *
from gavo.registry.model import (OAI, VOR, VOG, DC, RI, VS, SIA, SCS, OAIDC)


SF = meta.stanFactory
_defaultSet = set(["ivo_managed"])

# XXX TODO: Figure out a smart way to superficially validate result
# trees (e.g., "have a title", etc.).  Forcing thing into the 
# ModelBasedBuilder doesn't seem too smart.


################## ModelBasedBuilders for simple metadata handling

_vrResourceBuilder = meta.ModelBasedBuilder([
	('title', SF(VOR.title)),
	('shortName', SF(VOR.shortName)),
	('identifier', SF(VOR.identifier)),
	(None, SF(VOR.curation), [
		('publisher', SF(VOR.publisher), (), {
				"ivo_id": "ivo-id"}),
		('creator', SF(VOR.creator), [
			('name', SF(VOR.name)),
			('logo', SF(VOR.logo)),]),
		('contributor', SF(VOR.contributor), (), {
				"ivo_id": "ivo-id"}),
		('date', SF(VOR.date), (), {
				"role": "role"}),
		('version', SF(VOR.version)),
		('contact', SF(VOR.contact), [
			('name', SF(VOR.name), (), {
				"ivo_id": "ivo-id"}),
			('address', SF(VOR.address)),
			('email', SF(VOR.email)),
			('telephone', SF(VOR.telephone)),]),]),
	(None, SF(VOR.content), [
		('subject', SF(VOR.subject)),
		('description', SF(VOR.description)),
		('source', SF(VOR.source)),
		('referenceURL', SF(VOR.referenceURL)),
		('type', SF(VOR.type)),
		('contentLevel', SF(VOR.contentLevel)),]),
])


_dcBuilder = meta.ModelBasedBuilder([
	('title', SF(DC.title)),
	('identifier', SF(DC.identifier)),
	('creator', None, [
		('name', SF(DC.creator))]),
	('contributor', None, [
		('name', SF(DC.contributor))]),
	('description', SF(DC.description)),
	('language', SF(DC.language)),
	('rights', SF(DC.rights)),
	('publisher', SF(DC.publisher)),
	])


_oaiHeaderBuilder = meta.ModelBasedBuilder([
	('identifier', SF(OAI.identifier)),
	('datetimeUpdated', SF(OAI.datestamp)),
	('sets', SF(OAI.setSpec))])


_orgMetaBuilder = meta.ModelBasedBuilder([
	('facility', meta.stanFactory(VOR.facility)),# XXX TODO: look up ivo-ids?
	('instrument', meta.stanFactory(VOR.instrument)),
])


def getResourceArgs(resob):
	"""returns the mandatory attributes for constructing a Resource record
	for service in a dictionary.
	"""
	return {
		"created": base.getMetaText(resob, "creationDate", propagate=True),
		"updated": base.getMetaText(resob, "recTimestamp", propagate=True),
		"status": base.getMetaText(resob, "status"),
	}


def getOAIHeaderElementForRestup(restup):
	status = None
	if restup["deleted"]:
		status = "deleted"
	return OAI.header(status=status)[
		OAI.identifier[identifiers.computeIdentifierFromRestup(restup)],
		OAI.datestamp[restup["recTimestamp"].strftime("%Y-%m-%d")],
		[
			OAI.setSpec[setName] 
				for setName in servicelist.getSetsForService(restup["shortName"])]]


###################### Direct children of OAI.PMH

def getIdentifyElement(registryService):
	"""returns OAI Identify stanxml.

	registryService is the registry we're identifying, i.e. typically
	__system__/services#registry
	"""
	return OAI.Identify[
		OAI.repositoryName["%s publishing registry"%base.getConfig("web",
			"sitename")],
		OAI.baseURL[registryService.getURL("pubreg.xml")],
		OAI.protocolVersion["2.0"],
		OAI.adminEmail[base.getConfig("operator")],
		OAI.earliestDatestamp["1970-01-01T00:00:00Z"],
		OAI.deletedRecord["transient"],
		OAI.granularity["YYYY-MM-DDThh:mm:ssZ"],
		OAI.description[
			getVORMetadataElement(registryService),
		],
	]


def getListIdentifiersElement(restups):
	"""returns an OAI ListIdentifiers element for the rec tuples recs.
	"""
	return OAI.ListIdentifiers[
		[getOAIHeaderElementForRestup(restup) for restup in restups],
	]


def getListMetadataFormatsElement():
	return OAI.ListMetadataFormats[[
		OAI.metadataFormat[
			OAI.metadataPrefix[prefix],
			OAI.schema[schema],
			OAI.metadataNamespace[ns],
		] for prefix, schema, ns in METADATA_PREFIXES]
	]


def getListSetsElement():
	return OAI.ListSets[[
		# XXX TODO: Add some kind of description, in particular when we define
		# real local sets.
		OAI.set[
			OAI.setSpec[set["setName"]],
			OAI.setName[set["setName"]],
		]
	for set in servicelist.getSets()]]


def getResourceElement(resob, setNames, metadataMaker):
	"""helps get[VO|DC]ResourceElement.
	"""
	status = None
	if base.getMetaText(resob, "status")=="deleted":
		status = "deleted"
	return OAI.record[
		OAI.header(status=status)[
			_oaiHeaderBuilder.build(resob)],
		OAI.metadata[
			metadataMaker(resob, setNames)
		]
	]


def getDCMetadataElement(resob, setNames):
	return OAIDC.dc[_dcBuilder.build(resob)]


def getDCResourceElement(resob, setNames=_defaultSet):
	return getResourceElement(resob, setNames, getDCMetadataElement)


def getDCListRecordsElement(resobs, setNames, 
		makeRecord=getDCResourceElement):
	"""returns stanxml for ListRecords in dublin core format.

	resobs is a sequence of res objects.  
	makeRecord(resob, setNames) -> stanxml is a function that returns
	an OAI.record element.  For ivo_vor metadata prefixes, this is overridden.
	by getVOListRecordsElement.
	"""
	recs = OAI.ListRecords()
	for resob in resobs:
		try:
			recs[makeRecord(resob, setNames)]
		except base.NoMetaKey, msg:
			warnings.warn("Cannot create registry record for %s#%s"
			" because mandatory meta %s is missing"%(
				resob.rd.sourceId, resob.id, msg))
		except Exception, msg:
			traceback.print_exc()
			warnings.warn("Cannot create registry record %s.  Reason: %s"%(
				resob, msg))
	return recs


def getDCGetRecordElement(resob):
	return OAI.GetRecord[
		getDCResourceElement(resob)]


################### VOResource metadata element creation

class ResourceMaker(object):
	"""A base class for the generation of VOResource elements.

	These have a resType attribute specifying which resource type
	they work for.	These types are computed by the getResourceType
	helper function.

	The makeResource function below tries the ResourceMakers in turn
	for the "best" one that matches.

	If you create new ResourceMakers, you will have to enter them
	*in the correct sequence* in the _resourceMakers list below.

	ResourceMaker instances are called with a resob argument and a set
	of set names.  You will want to override the _makeResource(resob)
	-> xmlstan method and probably the resourceClass element.
	"""
	resourceClass = VOR.Resource
	resType = None

	def _makeResource(self, resob, setNames):
		return self.resourceClass(**getResourceArgs(resob))[
			VOR.validationLevel(validatedBy=str(resob.getMeta("validatedBy")))[
				resob.getMeta("validationLevel")],
			_vrResourceBuilder.build(resob),]
	
	def __call__(self, resob, setNames):
		return self._makeResource(resob, setNames)


class ServiceResourceMaker(ResourceMaker):
	"""A ResourceMaker adding rights and capabilities.
	"""
	resourceClass = VOR.Service
	resType = "nonTabularService"

	def _makeResource(self, service, setNames):
		return ResourceMaker._makeResource(self, service, setNames)[
			VOR.rights[service.getMeta("rights")], [
				capabilities.getCapabilityElement(pub)
				for pub in service.getPublicationsForSet(setNames)]]


class DataServiceResourceMaker(ServiceResourceMaker):
	"""A ResourceMaker for DataServices (i.e., services with instrument, facility
	and coverage).

	We don't have any of those, so resType is None.
	"""
	resourceClass = VS.DataService
	resType = None

	def _makeResource(self, service, setNames):
		return ServiceResourceMaker._makeResource(self, service, setNames)[
			_orgMetaBuilder.build(service),
			VS.coverage[service.getMeta("coverage")]]


class TabularServiceResourceMaker(DataServiceResourceMaker):
	"""a base class for Catalog und TableServices.

	This is necessary because coverage meta has this cumbersome location.

	Override the _getCoverage method (returning xmlstan) to actually
	fill in coverage.
	"""
	def _getCoverage(self, service):
		return None

	def _makeResource(self, service, setNames):
		return DataServiceResourceMaker._makeResource(self, service, setNames)[
			VS.table(role="out")[
				self._getCoverage(service),
				[capabilities.getTableParamFromColumn(f)
					for f in service.getAllOutputFields()]]]


class CatalogServiceResourceMaker(TabularServiceResourceMaker):
	resourceClass = VS.CatalogService
	resType = "catalogService"

	def _getCoverage(self, service):
		return None # XXX TODO: insert actual coverage.


class TableServiceResourceMaker(TabularServiceResourceMaker):
	resourceClass = VS.TableService
	resType = "tableService"
# This is basically like catalog service except there's no coverage.
# We rely on the service classifier to never classify a service as
# tableService when there's coverage (since that would generate invalid
# XML).


class RegistryResourceMaker(ResourceMaker):
	resourceClass = VOG.Resource
	resType = "registry"

	def _makeResource(self, registry, setNames):
		return ResourceMaker._makeResource(self, registry, setNames) [
				VOG.Harvest[
					VOR.description[registry.getMeta("harvest.description")],
					VOG.OAIHTTP(role="std", version="1.0")[
						VOR.accessURL[registry.getURL("pubreg.xml")],
					],
					VOG.maxRecords[registry.getMeta("maxRecords")],
				],
				VOG.full[registry.getMeta("full")],
				VOG.managedAuthority[base.getConfig("ivoa", "authority")],
			]


class OrgResourceMaker(ResourceMaker):
	resourceClass = VOR.Organisation
	resType = "organization"
	def _makeResource(self, registry, setNames):
		return ResourceMaker._makeResource(self, registry, setNames) [
			_orgMetaBuilder.build(registry)]


class AuthResourceMaker(ResourceMaker):
	resourceClass = VOG.Authority
	resType = "authority"
	def _makeResource(self, registry, setNames):
		return ResourceMaker._makeResource(self, registry, setNames) [
			VOG.managingOrg[registry.getMeta("managingOrg")]]


class DeletedResourceMaker(ResourceMaker):
	resType = "deleted"
	def _makeResource(self, res, setNames):
		return []


_getResourceMaker = utils.buildClassResolver(ResourceMaker, 
	globals().values(), instances=True, 
	key=lambda obj: obj.resType)



def getVORMetadataElement(resob, setNames=_defaultSet):
	return _getResourceMaker(getResType(resob))(resob, setNames)


def getVOResourceElement(resob, setNames=_defaultSet):
	"""returns a stanxml for Resource in VOR format.

	There's trouble here in that we have set management on the level of
	renderers (capabilities).  Thus, to come up with capabilities for
	a given ivorn, we have to know what set is queried.  However,
	OAI GetRecord doesn't specify sets.  So, we provide a default
	set of ivo_managed, assuming that the registry is only interested
	in records actually VO-registred.  This may fly into our face,
	but I can't see a way around it given the way our services are
	described.
	"""
	return getResourceElement(resob, setNames, getVORMetadataElement)


def getVOListRecordsElement(resobs, setNames):
	return getDCListRecordsElement(resobs, setNames, 
		getVOResourceElement)


def getVOGetRecordElement(resob):
	return OAI.GetRecord[
		getVOResourceElement(resob)]
		
