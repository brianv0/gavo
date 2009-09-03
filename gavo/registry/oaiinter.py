"""
The standard OAI interface.

In this module the core handling the OAI requests and the top-level handlers
for the verbs are defined.

The top-level handlers are all called run_<verb> -- any such function
is web-callable.
"""

import datetime

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry import servicelist
from gavo.registry.common import *
from gavo.registry.model import OAI
from gavo.utils import ElementTree


########################### Handlers for OAI verbs


def run_GetRecord(pars):
	"""returns a tree of stanxml elements for a response to GetRecord.
	"""
	checkPars(pars, ["identifier", "metadataPrefix"], [])
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.GetRecord[
			dispatchOnPrefix(pars, 
				builders.getDCResourceElement,
				builders.getVOResourceElement,
				identifiers.getResobFromIdentifier(pars["identifier"]))]]


def getSetNames(pars):
	"""returns a set of requested set names from pars.

	This is ivo_managed if no set is specified in pars.
	"""
	return set([pars.get("set", "ivo_managed")])


def run_ListRecords(pars):
	"""returns a tree of stanxml Elements for a response to ListRecords.
	"""
	checkPars(pars, ["metadataPrefix"], ["from", "until", "set"])
	return 	OAI.PMH[
		getResponseHeaders(pars),
		dispatchOnPrefix(pars,
			builders.getDCListRecordsElement,
			builders.getVOListRecordsElement,
			getMatchingResobs(pars), getSetNames(pars))]


def run_ListSets(pars):
	"""returns a tree of stanxml Elements for a response to ListSets.
	"""
	checkPars(pars, [])
	return OAI.PMH[
		getResponseHeaders(pars),
		builders.getListSetsElement(),
	]


def run_Identify(pars):
	"""returns a tree of stanxml elements for a response to Identify.
	"""
	checkPars(pars, [])
	return OAI.PMH[
		getResponseHeaders(pars),
		builders.getIdentifyElement(
			base.caches.getRD("__system__/services").getById("registry")),
	]


def run_ListIdentifiers(pars):
	"""returns a tree of stanxml elements for a response to ListIdentifiers.

	We don't have ivo specific metadata in the headers, so this ignores
	the metadata prefix.
	"""
	checkPars(pars, ["metadataPrefix"], ["from", "until", "set"])
	return OAI.PMH[
		getResponseHeaders(pars),
		builders.getListIdentifiersElement(getMatchingRestups(pars)),
	]


def run_ListMetadataFormats(pars):
	"""returns a tree of stanxml elements for a response to ListMetadataFormats.
	"""
	# identifier is not ignored since crooks may be trying to verify the
	# existence of resource in this way and we want to let them do this.
	# Of course, we support both kinds of metadata on all records.
	checkPars(pars, [], ["identifier"])
	if pars.has_key("identifier"):
		identifiers.getResobForIdentifier(pars["identifier"])
	return OAI.PMH[
		getResponseHeaders(pars),
		builders.getListMetadataFormatsElement(),
	]


########################### Helpers for OAI handlers

def checkPars(pars, required, optional=[], ignored=set(["verb"])):
	"""raises exceptions for missing or illegal parameters.
	"""
	if "resumptionToken" in pars:
		raise BadResumptionToken(pars["resumptionToken"])
	required, optional = set(required), set(optional)
	for name in pars:
		if name not in ignored and name not in required and name not in optional:
			raise BadArgument(name)
	for name in required:
		if name not in pars:
			raise BadArgument(name)


def getResponseHeaders(pars):
	"""returns the OAI response header for a query with pars.
	"""
	return [
		OAI.responseDate[datetime.datetime.utcnow().strftime(
			utils.isoTimestampFmt)],
		OAI.request(verb=pars["verb"], 
				metadataPrefix=pars.get("metadataPrefix"))]


def dispatchOnPrefix(pars, OAIBuilder, VORBuilder, *args):
	"""returns a resource factory depending on the metadataPrefix in pars.

	This is either OAIBuilder for an oai_dc prefix or VORBuilder for an
	ivo_vor builder.  The builders simply are factories for the resource
	factories; they get passed args.  

	Invalid metadataPrefixes are detected here and lead to exceptions.
	"""
	if pars.get("metadataPrefix")=="ivo_vor":
		return VORBuilder(*args)
	elif pars.get("metadataPrefix")=="oai_dc":
		return OAIBuilder(*args)
	else:
		if "metadataPrefix" in pars:
			raise CannotDisseminateFormat("%s metadata are not supported"%pars[
				"metadataPrefix"])
		else:
			raise BadArgument("metadataPrefix missing")


def getMatchingRestups(pars):
	"""returns a list of res tuples matching the OAI query arguments pars.

	pars is a dictionary mapping any of the following keys to values:

	* from
	* to -- these give a range for which changed records are being returned
	* set -- maps to a sequence of set names to be matched.
	"""
	sqlPars, sqlFrags = {}, []
	if "from" in pars:
		if not utils.dateRE.match(pars["from"]):
			raise BadArgument("from")
		sqlFrags.append("dateUpdated >= %%(%s)s"%base.getSQLKey("from",
			pars["from"], sqlPars))
	if "until" in pars:
		if not utils.dateRE.match(pars["until"]):
			raise BadArgument("until")
		sqlFrags.append("dateUpdated <= %%(%s)s"%base.getSQLKey("until",
			pars["until"], sqlPars))
	if "set" in pars:
		setName = pars["set"]
	else:
		setName = "ivo_managed"
	sqlFrags.append("setName=%%(%s)s"%(base.getSQLKey("set", 
		setName, sqlPars)))
	try:
		res = servicelist.queryServicesList(
			whereClause=" AND ".join(sqlFrags), pars=sqlPars)
	except sqlsupport.DatabaseError:
		raise BadArgument("Bad syntax in some parameter value")
	except KeyError, msg:
		traceback.print_exc()
		raise base.Error("Internal error, missing key: %s"%msg)
	if not res:
		raise NoRecordsMatch()
	return res


def getMatchingResobs(pars):
	return [identifiers.getResobFromRestup(restup)
		for restup in getMatchingRestups(pars)]


########################### The registry core

class RegistryCore(svcs.Core):
	"""is a core processing OAI requests.

	Its signature requires a single input key containing the complete
	args from the incoming request.  This is necessary to satisfy the
	requirement of raising errors on duplicate arguments.

	It returns an ElementTree.

	This core is intended to work the the RegistryRenderer.
	"""
	name_ = "registryCore"

	def completeElement(self):
		if self.inputDD is not base.Undefined:
			raise base.StructureError("RegistryCores have a fixed"
				" inputDD that you may not override.")
		self.inputDD = base.parseFromString(svcs.InputDescriptor, """
			<inputDD>
				<table id="_pubregInput">
					<column name="args" type="raw"
						description="The raw dictionary of input parameters"/>
				</table>
				<make table="_pubregInput"/>
			</inputDD>""")
		if self.outputTable is base.Undefined:
			self.outputTable = base.makeStruct(svcs.OutputTableDef)
		self._completeElementNext(RegistryCore)

	def runWithPMHDict(self, args):
		pars = {}
		for argName, argVal in args.iteritems():
			if len(argVal)!=1:
				raise BadArgument(argName)
			else:
				pars[argName] = argVal[0]
		try:
			verb = pars["verb"]
		except KeyError:
			raise BadArgument("verb")
		try:
			handler = globals()["run_"+verb]
		except KeyError:
			raise BadVerb("'%s' is an unsupported operation."%pars["verb"])
		return ElementTree.ElementTree(handler(pars).asETree())

	def run(self, service, inputData, queryMeta):
		"""returns an ElementTree containing a OAI-PMH response for the query 
		described by pars.
		"""
		args = inputData.getPrimaryTable().rows[0]["args"]
		return self.runWithPMHDict(args)

svcs.registerCore(RegistryCore)
