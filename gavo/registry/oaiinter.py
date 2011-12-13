"""
The standard OAI interface.

In this module the core handling the OAI requests and the top-level handlers
for the verbs are defined.

The top-level handlers are all called run_<verb> -- any such function
is web-callable.
"""

import datetime
import re
import time

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry.common import *
from gavo.registry.model import OAI
from gavo.utils import ElementTree


########################### Handlers for OAI verbs


def _handleVerb(pars, requiredArgs, optionalArgs,
		dcBuilder, voBuilder, getArgs=lambda pars: ()):
	"""handle an OAI PMH verb.

	This is a helper function for the run_* functions.

	requiredArgs and optionalArgs are lists of keywords of the
	given operation, dcBuilder and voBuilder are callables returning
	xmlstan for the respective operation, and getArgs is a function
	taking pars and returning an argument sequence to the builders.

	voBuilder may be None for cases where no dispatch for metadataPrefix
	is required.  In that case, dcBuilder will always be used.
	"""
	checkPars(pars, requiredArgs, optionalArgs)
	if voBuilder is None:
		contentMaker = dcBuilder
	else:
		contentMaker = lambda *args: dispatchOnPrefix(pars,
			dcBuilder, voBuilder, *args)
	return OAI.PMH[
		getResponseHeaders(pars),
		contentMaker(*getArgs(pars)),]


def run_GetRecord(pars):
	"""returns a tree of stanxml elements for a response to GetRecord.
	"""
	return _handleVerb(pars, ["identifier", "metadataPrefix"], [],
		builders.getDCGetRecordElement,
		builders.getVOGetRecordElement,
		lambda pars: (identifiers.getResobFromIdentifier(pars["identifier"]),))


def getSetNames(pars):
	"""returns a set of requested set names from pars.

	This is ivo_managed if no set is specified in pars.
	"""
	return set([pars.get("set", "ivo_managed")])


def run_ListRecords(pars):
	"""returns a tree of stanxml Elements for a response to ListRecords.
	"""
	return _handleVerb(pars, 
		["metadataPrefix"], ["from", "until", "set", "resumptionToken"],
		builders.getDCListRecordsElement,
		builders.getVOListRecordsElement,
		lambda pars: (getMatchingResobs(pars), getSetNames(pars)))


def run_ListIdentifiers(pars):
	"""returns a tree of stanxml elements for a response to ListIdentifiers.

	We don't have ivo specific metadata in the headers, so this ignores
	the metadata prefix.
	"""
	return _handleVerb(pars, 
		["metadataPrefix"], ["from", "until", "set", "resumptionToken"],
		builders.getListIdentifiersElement,
		builders.getListIdentifiersElement,
		lambda pars: (getMatchingRestups(pars),))


def run_ListSets(pars):
	"""returns a tree of stanxml Elements for a response to ListSets.
	"""
	return _handleVerb(pars, [], [],
		builders.getListSetsElement, None)


def run_Identify(pars):
	"""returns a tree of stanxml elements for a response to Identify.
	"""
	return _handleVerb(pars, [], [],
		builders.getIdentifyElement,
		None,
		lambda pars: 
			(base.caches.getRD("__system__/services").getById("registry"),))


def run_ListMetadataFormats(pars):
	"""returns a tree of stanxml elements for a response to ListMetadataFormats.
	"""
	# identifier is not ignored since crooks may be trying to verify the
	# existence of resource in this way and we want to let them do this.
	# Of course, we support both kinds of metadata on all records.
	def makeArgs(pars):
		if pars.has_key("identifier"):
			identifiers.getResobFromIdentifier(pars["identifier"])
		return ()
	return _handleVerb(pars, [], ["identifier"],
		builders.getListMetadataFormatsElement,
		None,
		makeArgs)


########################### Helpers for OAI handlers

def parseResumptionToken(rawToken):
	"""returns the offset encoded in the resumptionToken rawToken.

	See model.OAI.resumptionToken for rawToken's format.  If we believe
	that the registry has changed since rawToken's timestamp, we raise
	a BadResumptionToken exception.  This is based on gavo pub reloading
	the //services RD after publication.  Not perfect, but probably
	adequate.
	"""
	mat = re.match("(\d+);(\d+)$", rawToken)
	if not mat:
		raise BadResumptionToken("Bad syntax of resumption token")
	tokenGeneratedAt = int(mat.group(1))
	if tokenGeneratedAt<=base.caches.getRD("//services").loadedAt:
		raise BadResumptionToken("Service table has changed")
	return int(mat.group(2))


def checkPars(pars, required, optional=[], 
		ignored=set(["verb", "maxRecords"])):
	"""raises exceptions for missing or illegal parameters.
	"""
	required, optional = set(required), set(optional)
	for name in pars:
		print name, ignored, required, optional
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


def _parseOAIPars(pars):
	"""returns a pair of queryFragment, parameters for a query of
	services#services according to OAI.
	"""
	sqlPars, sqlFrags = {}, []
	if "from" in pars:
		if not utils.datetimeRE.match(pars["from"]):
			raise BadArgument("from")
		sqlFrags.append("recTimestamp >= %%(%s)s"%base.getSQLKey("from",
			pars["from"], sqlPars))
	if "until" in pars:
		if not utils.datetimeRE.match(pars["until"]):
			raise BadArgument("until")
		sqlFrags.append("recTimestamp <= %%(%s)s"%base.getSQLKey("until",
			pars["until"], sqlPars))
	if "set" in pars:
		setName = pars["set"]
	else:
		setName = "ivo_managed"
	# we should join for this, but we'd need more careful query 
	# construction then...
	sqlFrags.append("EXISTS (SELECT setName from dc.sets WHERE"
		" sets.resId=resources.resId"
		" AND sets.sourceRD=resources.sourceRD"
		" AND setname=%%(%s)s)"%(base.getSQLKey("set", setName, sqlPars)))
	return " AND ".join(sqlFrags), sqlPars


def getMatchingRestups(pars, connection=None):
	"""returns a list of res tuples matching the OAI query arguments pars.

	The last element of the list could be an OAI.resumptionToken element.

	pars is a dictionary mapping any of the following keys to values:

		- from
		- until -- these give a range for which changed records are being returned
		- set -- maps to a sequence of set names to be matched.
		- resumptionToken -- an integer literal that specifies an offset
		  into the service list
		- maxRecords -- an integer literal that specifies the maximum number
		  of records returned, defaulting to 10000
	
	maxRecords is not part of OAI-PMH; it is used internally to
	turn paging on when we think it's a good idea, and for testing.
	"""
	frag, fillers = _parseOAIPars(pars)

	maxRecords = int(pars.get("maxRecords", 10000))
	resumptionToken = 0
	if "resumptionToken" in pars:
		resumptionToken = parseResumptionToken(pars["resumptionToken"])

	try:
		srvTable = rsc.TableForDef(getServicesRD().getById("resources"),
			connection=connection) 
		res = list(srvTable.iterQuery(srvTable.tableDef, frag, fillers,
			limits=(
				"LIMIT %(maxRecords)s OFFSET %(resumptionToken)s", locals())))
		srvTable.close()
		
		if len(res)==maxRecords:
			# there's probably more data, request a resumption token
			res.append(OAI.resumptionToken["%d;%d"%(
				int(time.time()), maxRecords+resumptionToken)])
	except base.DBError:
		raise base.ui.logOldExc(BadArgument("Bad syntax in some parameter value"))
	except KeyError, msg:
		raise base.ui.logOldExc(base.Error("Internal error, missing key: %s"%msg))
	if not res:
		raise NoRecordsMatch("No resource records match your criteria.")
	return res


def getMatchingResobs(pars):
	"""returns a list of res objects matching the OAI-PMH pars.

	See getMatchingRestups for details.
	"""
	res = []
	for restup in getMatchingRestups(pars):
		if isinstance(restup, OAI.OAIElement):
			res.append(restup)
		else:
			try:
				res.append(identifiers.getResobFromRestup(restup))
			except base.NotFoundError:
				base.ui.notifyError("Could not create resource for %s"%repr(restup))
	return res


########################### The registry core

class RegistryCore(svcs.Core, base.RestrictionMixin):
	"""is a core processing OAI requests.

	Its signature requires a single input key containing the complete
	args from the incoming request.  This is necessary to satisfy the
	requirement of raising errors on duplicate arguments.

	It returns an ElementTree.

	This core is intended to work the the RegistryRenderer.
	"""
	name_ = "registryCore"

	inputTableXML = """
		<inputTable id="_pubregInput">
			<param name="args" type="raw"
				description="The raw dictionary of input parameters"/>
		</inputTable>
		"""

	outputTableXML = """<outputTable/>"""

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
			raise base.ui.logOldExc(BadArgument("verb"))
		try:
			handler = globals()["run_"+verb]
		except KeyError:
			raise base.ui.logOldExc(
				BadVerb("'%s' is an unsupported operation."%pars["verb"]))
		return ElementTree.ElementTree(handler(pars).asETree())

	def run(self, service, inputTable, queryMeta):
		"""returns an ElementTree containing a OAI-PMH response for the query 
		described by pars.
		"""
		args = inputTable.getParam("args")
		return self.runWithPMHDict(args)
