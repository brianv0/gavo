"""
The standard OAI interface.

In this module the core handling the OAI requests and the top-level handlers
for the verbs are defined.

The top-level handlers are all called run_<verb> -- any such function
is web-callable.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import time
import urllib
import urlparse

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry.common import *
from gavo.registry.model import OAI


########################### Generic Processing of PMH requests

# a mapping of OAI verbs to optional and required argument names
_ARGUMENTS = {
	"GetRecord": (["identifier", "metadataPrefix"], []),
	"ListRecords": (["metadataPrefix"], 
		["from", "until", "set", "resumptionToken"]),
	"ListIdentifiers": (["metadataPrefix"], 
		["from", "until", "set", "resumptionToken"]),
	"ListSets": ([], []),
	"Identify": ([], []),
	"ListMetadataFormats": ([], ["identifier"]),}


def runPMH(pars, builders):
	"""runs the OAI-PMH handling function.

	builders is a mapping of verbs to tuples of (oai_dc-generating-function,
	ivo_vor-generating-function, argument-building-function).

	The argument-building function takes the OAI-PMH parameter dictionary
	(that's already validated for mandatory and optional arguments) and
	returns a tuple that is then passed on to the generating functions.

	Those must returns stanxml for inclusion in an OAI.PMH element.  The
	response header is generated by this function.
	"""
	if "verb" not in pars:
		raise BadArgument("verb")
	verb = pars["verb"]

	if verb not in _ARGUMENTS:
		raise BadVerb("'%s' is an unsupported operation."%verb)
	requiredArgs, optionalArgs = _ARGUMENTS[verb]
	checkPars(pars, requiredArgs, optionalArgs)

	dcBuilder, voBuilder, getArgs = builders[verb]
	if voBuilder is None:
		contentMaker = dcBuilder
	else:
		contentMaker = lambda *args: dispatchOnPrefix(pars,
			dcBuilder, voBuilder, *args)
	return OAI.PMH[
		getResponseHeaders(pars),
		contentMaker(*getArgs(pars)),]



########################### parsing and generating resumption tokens
# In our implementation, the resumptionToken is a hex-encoded
# zlibbed query string made from the parameters, plus information
# on the offset and the time the resumption token was issued.

def makeResumptionToken(pars, nextOffset):
	"""return a resumptionToken element for resuming the query in
	pars at nextOffset.
	"""
	toEncode = pars.copy()
	toEncode["nextOffset"] = str(nextOffset)
	toEncode["queryDate"] = time.time()
	return urllib.urlencode(toEncode).encode("zlib").encode("hex"
		).replace("\n", "")


def parseResumptionToken(pars):
	"""returns a a dict realPars for an OAI-PMH parameter
	dictionary pars.

	If we believe that the registry has changed since rawToken's
	timestamp, we raise a BadResumptionToken exception.  This is
	based on gavo pub reloading the //services RD after publication.
	Not perfect, but probably adequate.

	Note that newPars will contain resumptionToken again, but as an
	offset to the query executed.
	"""
	try:
		newPars = dict(urlparse.parse_qsl(
			pars["resumptionToken"].decode("hex").decode("zlib")))
		queryDate = float(newPars.pop("queryDate"))
		offset = int(newPars.pop("nextOffset"))
	except KeyError, msg:
		raise base.ui.logOldExc(BadResumptionToken("Incomplete resumption token"))
	except Exception, msg:
		raise base.ui.logOldExc(BadResumptionToken(str(msg)))

	if newPars.get("verb", 1)!=pars.get("verb", 2):
		raise BadResumptionToken("Trying to resume with a different verb")

	if pars.get("metadataPrefix"):
#		if newPars.get("metadataPrefix")!=pars.get("metadataPrefix"):
		raise BadResumptionToken("Trying to resume with a"
			" different metadata prefix")

	if int(queryDate)<int(base.caches.getRD("//services").loadedAt):
		raise BadResumptionToken("Service table has changed")

	newPars["resumptionToken"] = offset
	return newPars

########################### Helpers for OAI handlers

def checkPars(pars, required, optional=[], 
		ignored=set(["verb", "maxRecords"])):
	"""raises exceptions for missing or illegal parameters.
	"""
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


def _getSetNames(pars):
	"""returns a set of requested set names from pars.

	This is ivo_managed if no set is specified in pars.
	"""
	return set([pars.get("set", "ivo_managed")])


def _makeArgsForListMetadataFormats(pars):
	# returns arguments for builders.getListMetadataElements.
	# identifier is not ignored since crooks may be trying to verify the
	# existence of resource in this way and we want to let them do this.
	# Of course, we support both kinds of metadata on all records.
	if pars.has_key("identifier"):
		identifiers.getResobFromIdentifier(pars["identifier"])
	return ()


def _addTemporalCondition(parVal, operator, sqlFrags, sqlPars, parName):
	"""generates a temporal condition for recTimestamp and operator out of 
	parVal.

	This is a helper to handle both from and to parameters.

	Nothing is generated if parVal is None.

	Since the Validator insists that servers enforce identical granularity
	on both arguments, this is more involved; it returns None, "time",
	or "datetime" depending on what the argument was.
	"""
	if parVal is None:
		return None

	parsed, argtype = None, None
	mat = utils.datetimeRE.match(parVal) 
	if mat:
		parsed = base.parseDefaultDatetime(parVal)
		argtype = "datetime"

	mat = utils.dateRE.match(parVal)
	if not parsed and mat:
		parsed = base.parseDefaultDate(parVal)
		# postgres comparse dates against timestamps as if the dates were for
		# midnight.  Therefore, on the upper limit, we need to fix things:
		if operator=='<=':
			parsed = parsed+datetime.timedelta(1)
			operator = '<'
		argtype = "date"

	if parsed:
		sqlFrags.append("recTimestamp %s %%(%s)s"%(
			operator,
			base.getSQLKey("temporal", parsed, sqlPars)))
		return argtype

	raise BadArgument(parName)


def _parseOAIPars(pars):
	"""returns a pair of queryFragment, parameters for a query of
	services#services according to OAI.
	"""
	sqlPars, sqlFrags = {}, []
	argTypes = set(argType for argType in [
			_addTemporalCondition(
				pars.get("from"), ">=", sqlFrags, sqlPars, "from"),
			_addTemporalCondition(
				pars.get("until"), "<=", sqlFrags, sqlPars, "until")]
			if argType)
	if len(argTypes)==2:
		raise BadArgument("from")

	return " AND ".join(sqlFrags), sqlPars


def _getSetCondition(pars, sqlPars):
	"""helps getMatchingRestups.
	"""
	if "set" in pars:
		setName = pars["set"]
	else:
		setName = "ivo_managed"
	# we should join for this, but we'd need more careful query 
	# construction then...
	return ("EXISTS (SELECT setName from dc.sets WHERE"
		" sets.resId=resources.resId"
		" AND sets.sourceRD=resources.sourceRD"
		" AND setname=%%(%s)s)"%(base.getSQLKey("set", setName, sqlPars)))


def getMatchingRows(pars, rscTableDef, getSetFilter):
	"""returns rows in rscTableDef matching the OAI parameters pars.

	The last element of the list could be an OAI.resumptionToken element.
	pars is a dictionary mapping any of the following keys to values:

		- from
		- until -- these give a range for which changed records are being returned
		- set -- maps to a sequence of set names to be matched.
		- resumptionToken -- some magic value (see OAI.resumptionToken)
		- maxRecords -- an integer literal that specifies the maximum number
		  of records returned, defaulting to [ivoa]oaipmhPageSize
	
	maxRecords is not part of OAI-PMH; it is used internally to
	turn paging on when we think it's a good idea, and for testing.

	rscTableDef has to be a table with a column recTimestamp giving the
	resource record's updated time.

	getSetFilter(pars, fillers) is a function receiving the PMH parameters
	dictionary and a dictionary of query fillers and returning, as appropriate,
	a condition that implements any conditions on sets within pars
	"""
	maxRecords = int(pars.get("maxRecords", 
		base.getConfig("ivoa", "oaipmhPagesize")))
	offset = pars.get("resumptionToken", 0)
	frag, fillers = _parseOAIPars(pars)
	frag = " AND ".join(
		f for f in [getSetFilter(pars, fillers), frag] if f)

	try:
		with base.getTableConn() as conn:
			srvTable = rsc.TableForDef(rscTableDef, connection=conn) 
			res = list(srvTable.iterQuery(rscTableDef, frag, fillers,
				limits=(
					"LIMIT %(maxRecords)s OFFSET %(offset)s", locals())))
		
		if len(res)==maxRecords:
			# there's probably more data, request a resumption token
			res.append(OAI.resumptionToken[
				makeResumptionToken(pars, offset+len(res))])
			res[-1].addChild = lambda:0

	except base.DBError:
		raise base.ui.logOldExc(BadArgument("Bad syntax in some parameter value"))
	except KeyError, msg:
		raise base.ui.logOldExc(base.Error("Internal error, missing key: %s"%msg))
	if not res:
		raise NoRecordsMatch("No resource records match your criteria.")
	return res


def getMatchingRestups(pars):
	"""returns a list of res tuples matching the OAI query arguments pars.

	See getMatchingRows for details on pars.
	"""
	td = getServicesRD().getById("resources")
	return getMatchingRows(pars, td, _getSetCondition)


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
				multiplicity="single"
				description="The raw dictionary of input parameters"/>
		</inputTable>
		"""

	outputTableXML = """<outputTable/>"""

	builders = {
		"GetRecord": (builders.getDCGetRecordElement,
			builders.getVOGetRecordElement,
			lambda pars: (identifiers.getResobFromIdentifier(pars["identifier"]),)),
		"ListRecords": (builders.getDCListRecordsElement,
			builders.getVOListRecordsElement,
			lambda pars: (getMatchingResobs(pars), _getSetNames(pars))),
		"ListIdentifiers": (builders.getListIdentifiersElement,
			builders.getListIdentifiersElement,
			lambda pars: (getMatchingRestups(pars),)),
		"ListSets": (builders.getListSetsElement, None, lambda pars: ()),
		"Identify": (builders.getIdentifyElement, None,
			lambda pars: (base.caches.getRD("//services").getById("registry"),)),
		"ListMetadataFormats": (builders.getListMetadataFormatsElement, None,
			_makeArgsForListMetadataFormats),
	}

	def runWithPMHDict(self, args):
		pars = {}
		for argName, argVal in args.iteritems():
			if len(argVal)!=1:
				raise BadArgument(argName)
			else:
				pars[argName] = argVal[0]
		
		offset = 0
		if "resumptionToken" in pars:
			pars = parseResumptionToken(pars)

		return runPMH(pars, self.builders)

	def run(self, service, inputTable, queryMeta):
		"""returns an ElementTree containing a OAI-PMH response for the query 
		described by pars.
		"""
		args = inputTable.getParam("args")
		return self.runWithPMHDict(args)
