"""
A simple client of OAI-http.

This includes both some high-level functions and rudimentary parsers
that can serve as bases for more specialized parsers.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cPickle as pickle
import hashlib
import os
import re
import urllib
from cStringIO import StringIO
from xml import sax
from xml.sax import saxutils

from gavo import base
from gavo import svcs
from gavo import utils


class FailedQuery(Exception):
	def __init__(self, msg, code="?", value="?"):
		Exception.__init__(self, msg)
		self.code, self.value = code, value


class NoRecordsMatch(Exception):
	pass


class PrefixIsTaken(Exception):
	pass

# Canonical prefixes, i.e., essentially fixed prefixes for certain
# namespaces.  This is all an ugly nightmare, but this is what you
# get for having namespace prefixes in attributes.

class CanonicalPrefixes(object):
	"""a self-persisting dictionary of the prefixes we use in our
	OAI interface.

	CanonicalPrefixes objects are constructed with the name of a
	pickle file containing a list of (prefix, uri) pairs.

	This reproduces some code from stanxml.NSRegistry, but we want that
	stuff as instance method here, not as class method.
	"""
	def __init__(self, pickleName):
		self.pickleName = pickleName
		self._registry = {}
		self._reverseRegistry = {}
		self._loadData()

	def registerPrefix(self, prefix, ns, save=True):
		if prefix in self._registry:
			if ns!=self._registry[prefix]:
				raise PrefixIsTaken(prefix)
			return
		self._registry[prefix] = ns
		if ns in self._reverseRegistry and self._reverseRegistry[ns]!=prefix:
			raise ValueError("Namespace %s already has prefix %s, will"
				" not clobber with %s"%(ns, self._reverseRegistry[ns], prefix))
		self._reverseRegistry[ns] = prefix
		if save:
			self._saveData()
	
	def registerPrefixOrMakeUp(self, prefix, ns):
		"""registers prefix for ns or, if prefix is already taken, makes
		up a new prefix for the namespace URI ns.
		"""
		try:
			self.registerPrefix(prefix, ns)
		except PrefixIsTaken:
			origPrefix, uniquer = prefix, 0
			while True:
				try:
					prefix = origPrefix+str(uniquer)
					self.registerPrefix(prefix, ns)
				except PrefixIsTaken:
					uniquer += 1
				else:
					break

	def getPrefixForNS(self, ns):
		try:
			return self._reverseRegistry[ns]
		except KeyError:
			raise svcs.NotFoundError(ns, "XML namespace",
				"registry of XML namespaces.")

	def haveNS(self, ns):
		return self._reverseRegistry.has_key(ns)

	def getNSForPrefix(self, prefix):
		try:
			return self._registry[prefix]
		except KeyError:
			raise base.NotFoundError(prefix, "XML namespace prefix",
				"registry of prefixes.")

	def iterNS(self):
		return self._registry.iteritems()

	def _fillFromPairs(self, pairs):
		"""fills the instance from a list of prefix, uri pairs.

		Pairs is what is stored in the pickle.
		"""
		for prefix, uri in pairs:
			self.registerPrefix(prefix, uri, save=False)
		
	def _bootstrap(self):
		"""sets up our canonical prefixes from DaCHS' (stanxml) namespace 
		registry.
		"""
		from gavo import api  #noflake: hope most prefixes are registred after that
		from gavo.utils import stanxml
		self._fillFromPairs(stanxml.NSRegistry._registry.iteritems())
		self._saveData()

	def _loadData(self):
		try:
			with open(self.pickleName) as f:
				self._fillFromPairs(pickle.load(f))
		except IOError: # most likely, the file does not exist yet
			base.ui.notifyWarning("Starting new canonical prefixes")
			self._bootstrap()

	def _saveData(self):
		toPersist = list(sorted(self._registry.iteritems()))
		try:
			with open(self.pickleName+".tmp", "w") as f:
				pickle.dump(toPersist, f)
			os.rename(self.pickleName+".tmp", self.pickleName)
		except IOError, msg:
			base.ui.notifyWarning("Could not persist canonical prefixes: %s"%
				msg)


def getCanonicalPrefixes():
	return CanonicalPrefixes(os.path.join(base.getConfig("cacheDir"),
		"rrOaiPrefixes.pickle"))


class OAIErrorMixin(object):
	def _end_error(self, name, attrs, content):
		if attrs["code"]=="noRecordsMatch":
			raise NoRecordsMatch()
		raise FailedQuery("Registry bailed with code %s, value %s"%(
			attrs["code"], content), attrs["code"], content)


class IdParser(utils.StartEndHandler, OAIErrorMixin):
	"""A parser for simple OAI-PMH headers.

	Records end up as a list of dictionaries in the recs attribute.
	"""
	resumptionToken = None

	def __init__(self, initRecs=None):
		utils.StartEndHandler.__init__(self)
		if initRecs is None:
			self.recs = []
		else:
			self.recs = initRecs

	def getResult(self):
		return self.recs

	def _end_identifier(self, name, attrs, content):
		self.recs[-1]["id"] = content
	
	def _end_datestamp(self, name, attrs, content):
		try:
			self.recs[-1]["date"] = utils.parseISODT(content)
		except ValueError:  # don't fail just because of a broken date
			self.recs[-1]["date"] = None
	
	def _start_header(self, name, attrs):
		self.recs.append({})

	def _end_resumptionToken(self, name, attrs, content):
		if content.strip():
			self.resumptionToken = content


class RecordParser(IdParser, OAIErrorMixin):
	"""A simple parser for ivo_vor records.

	This only pulls out a number of the most salient items; more will 
	probably follow as needed.
	"""
	def _end_title(self, name, attrs, content):
		if self.getParentTag()=="Resource":
			self.recs[-1][name] = content

	def _end_email(self, name, attrs, content):
		if self.getParentTag()=="contact":
			self.recs[-1]["contact.email"] = content

	def _end_name(self, name, attrs, content):
		if self.getParentTag()=="creator":
			self.recs[-1].setdefault(name, []).append(content)

	def _end_subject(self, name, attrs, content):
		self.recs[-1].setdefault(name, []).append(content)

	def _handleContentChild(self, name, attrs, content):
		if self.getParentTag()=="content":
			self.recs[-1][name] = content

	_end_description = _end_source = _end_referenceURL = \
		_handleContentChild

	def _end_datestamp(self, name, attrs, content):
		# nuke IdParser implementation, we take our date from ri:Resource
		pass

	def _startResource(self, name, attrs):
		self.recs.append({})

	def _end_Resource(self, name, attrs, content):
		self.recs[-1]["date"] = utils.parseISODT(attrs["updated"])

	def _end_accessURL(self, name, attrs, content):
		self.recs[-1].setdefault(name, []).append(content)


class OAIRecordsParser(sax.ContentHandler, OAIErrorMixin):
	"""a SAX ContentHandler generating tuples of some record-level metadata
	and pre-formatted XML of simple implementation of the OAI interface.

	canonicalPrefixes is a CanonicalPrefixesInstance built from
	res/canonicalPrefixes.pickle

	Note that we *require* that records actually carry ivo_vor metadata.
	"""
	# attribute names the values of which should be disambiguated to
	# reduce the likelihood of clashes when ids are reused between documents.
	# (see _normalizeAttrs)
	_referringAttributeNames = set(["id", "ref",
		"coord_system_id"])

	resumptionToken = None

	def __init__(self, canonicalPrefixes=None):
		self.canonicalPrefixes = canonicalPrefixes or getCanonicalPrefixes()
		sax.ContentHandler.__init__(self)
		self.buffer = None
		self.writer = None
		self.rowdicts = []
		self.prefixMap = {}
		self.prefixesToTranslate = {}

	def startPrefixMapping(self, prefix, uri):
		self.prefixMap.setdefault(prefix, []).append(uri)

		# Here, we make sure we find a globally unique prefix for every
		# namespace URI.  canonicalPrefixes makes sure this unique prefix
		# is persistent and later available to the OAI interface
		if not self.canonicalPrefixes.haveNS(uri):
			self.canonicalPrefixes.registerPrefixOrMakeUp(prefix, uri)
		
		canonPrefix = self.canonicalPrefixes.getPrefixForNS(uri)
		if prefix!=canonPrefix or prefix in self.prefixesToTranslate:
			self.prefixesToTranslate.setdefault(prefix, []).append(canonPrefix)
	
	def endPrefixMapping(self, prefix):
		self.prefixMap[prefix].pop()
		if prefix in self.prefixesToTranslate:
			self.prefixesToTranslate[prefix].pop()
			if not self.prefixesToTranslate[prefix]:
				del self.prefixesToTranslate[prefix]

	def startElementNS(self, namePair, ignored, attrs):
		ns, name = namePair
		if ns is not None:
			name = self.canonicalPrefixes.getPrefixForNS(ns)+":"+name
		if attrs:
			attrs = self._normalizeAttrs(attrs)

		if name in self.startHandlers:
			self.startHandlers[name](self, name, attrs)

		if self.writer:
			self.writer.startElement(name, attrs)

		self._lastChars = []
	
	def endElementNS(self, namePair, name):
		ns, name = namePair
		if ns is not None:
			name = self.canonicalPrefixes.getPrefixForNS(ns)+":"+name
		if self.writer:
			self.writer.endElement(name)
		if name in self.endHandlers:
			self.endHandlers[name](self, name)
	
	def characters(self, stuff):
		if self.writer:
			self.writer.characters(stuff)
		# Hack, see _getLastContent
		self._lastChars.append(stuff)

	def normalizeNamespace(self, name):
		"""fixes the namespace prefix of name if necessary.

		name must be a qualified name, i.e., contain exactly one colon.

		"normalize" here means make sure the prefix matches our canonical prefix
		and change it to the canonical one if necessary.
		"""
		prefix, base = name.split(":")
		if prefix not in self.prefixesToTranslate:
			return name
		return self.prefixesToTranslate[prefix][-1]+":"+base

	def _normalizeAttrs(self, attrs):
		"""fixes attribute name and attribute value namespaces if necessary.

		It also always checks for xsi:type and fixes namespaced attribute
		values as necessary.

		See also normalizeNamespace.
		"""
		newAttrs = {}
		for ns, name in attrs.keys():
			value = attrs[(ns, name)]
			if ns is None:
				newName = name
			else:
				newName = self.canonicalPrefixes.getPrefixForNS(ns)+":"+name

			if newName=="xsi:type":
				if ":" in value:
					value = self.normalizeNamespace(value)
			
			# to uniqueify id/ref-pairs, prepend an md5-digest of the ivoid
			# to selected ids.  This isn't guaranteed to always work, but
			# if someone is devious enough to cause collisions here, they
			# deserve no better.
			if newName in self._referringAttributeNames:
				value = value+hashlib.md5(self.ivoid).hexdigest()

			newAttrs[newName] = value

		return newAttrs

	def _getLastContent(self):
		"""returns the entire character content since the last XML event.
		"""
		return "".join(self._lastChars)

	def notifyError(self, err):
		self._errorOccurred = True

	def shipout(self, role, record):
		# see _end_identifier for an explanation of the following condition
		if self.ivoid is None:
			return
		# see our docstring on why we need the following
		if not self.metadataSeen:
			return
		if self._errorOccurred:
			return

		# _start_header sets _isDeleted
		if self._isDeleted:
			return
		self.rowdicts.append((role, record))

	def _start_oai_header(self, name, attrs):
		self._isDeleted = attrs.get("status", "").lower()=="deleted"

	def _start_oai_record(self, name, attrs):
		self._errorOccurred = False
		self.curXML = StringIO()
		self.writer = saxutils.XMLGenerator(self.curXML, "utf-8")
		self.writer.startDocument()
		self.ivoid, self.updated = None, None
		self.metadataSeen = False
		self.oaiSets = set()

	def _start_ri_Resource(self, anme, attrs):
		self.metadataSeen = True

	def _end_oai_record(self, name):
		if self.writer is not None:
			self.writer.endDocument()
			# yeah, we decode the serialized result right away; it's easier
			# to store character streams in the DB the way I'm doing things.
			oaixml = self.curXML.getvalue().decode("utf-8")
			# unfortunately, XMLGenerator insists on adding an XML declaration,
			# which I can't have here.  I remove it manually
			if oaixml.startswith("<?xml"):
				oaixml = oaixml[oaixml.index("?>")+2:]
			self.shipout("oairecs", {
				"ivoid": self.ivoid,
				"updated": self.updated,
				"oaixml": oaixml})
		self.writer = None
		self.curXML = None

	def _end_oai_setSpec(self, name):
		self.oaiSets.add(self._getLastContent())

	def _end_oai_identifier(self, name):
		self.ivoid = self._getLastContent().lower()

	def _end_oai_resumptionToken(self, name):
		self.resumptionToken = self._getLastContent()

	def _start_oai_error(self, name, attrs):
		self._errorAttrs = attrs

	def _end_oai_error(self, name):
		self._end_error(name, self._errorAttrs, self._getLastContent())

	def getResult(self):
		return self.rowdicts

	startHandlers = {
		"oai:record": _start_oai_record,
		"oai:header": _start_oai_header,
		"ri:Resource": _start_ri_Resource,
		"oai:error": _start_oai_error,
	}
	endHandlers = {
		"oai:record": _end_oai_record,
		"oai:setSpec": _end_oai_setSpec,
		"oai:resumptionToken": _end_oai_resumptionToken,
		"oai:identifier": _end_oai_identifier,
		"oai:error": _end_oai_error,
	}


class ServerProperties(object):
	"""A container for what an OAI-PMH server gives in response to
	identify.
	"""
	repositoryName = None
	baseURL = None
	protocolVersion = None
	adminEmails = ()
	earliestDatestamp = None
	deletedRecord = None
	granularity = None
	repositoryName = None
	compressions = ()

	def __init__(self):
		self.adminEmails = []
		self.compressions = []
		self.descriptions = []

	def set(self, name, value):
		setattr(self, name, value)
	
	def add(self, name, value):
		getattr(self, name).append(value)


class IdentifyParser(utils.StartEndHandler, OAIErrorMixin):
	"""A parser for the result of the identify operation.

	The result (an instance of ServerProperties) is in the serverProperties
	attribute.
	"""
	resumptionToken = None

	def getResult(self):
		return self.serverProperties

	def _start_Identify(self, name, attrs):
		self.serverProperties = ServerProperties()

	def _endListThing(self, name, attrs, content):
		self.serverProperties.add(name+"s", content.strip())

	_end_adminEmail = _end_compression \
		= _endListThing

	def _endStringThing(self, name, attrs, content):
		self.serverProperties.set(name, content.strip())

	_end_repositoryName = _end_baseURL = _end_protocolVersion \
		= _end_granularity = _end_deletedRecord = _end_earliestDatestamp \
		= _end_repositoryName = _endStringThing


class OAIQuery(object):
	"""A container for queries to OAI interfaces.

	Construct it with the oai endpoint and the OAI verb, plus some optional
	query attributes.  If you want to retain or access the raw responses
	of the server, pass a contentCallback function -- it will be called
	with a byte string containing the payload of the server response if
	it was parsed successfully.  Error responses cannot be obtained in
	this way.

	The OAIQuery is constructed with OAI-PMH parameters (verb, startDate,
	endDate, set, metadataPrefix; see the OAI-PMH docs for what they mean,
	only verb is mandatory).  In addition, you can pass granularity,
	which is the granularity
	"""
	startDate = None
	endDate = None
	set = None
	registry = None
	metadataPrefix = None

	# maxRecords is mainly used in test_oai; that's why there's no
	# constructor parameter for it
	maxRecords = None

	def __init__(self, registry, verb, startDate=None, endDate=None, set=None,
			metadataPrefix="ivo_vor", identifier=None, contentCallback=None, 
			granularity=None):
		self.registry = registry
		self.verb, self.set = verb, set
		self.startDate, self.endDate = startDate, endDate
		self.identifier = identifier
		self.metadataPrefix = metadataPrefix
		self.contentCallback = contentCallback
		self.granularity = granularity
		if not self.granularity:
			self.granularity = "YYYY-MM-DD"

	def getKWs(self, **moreArgs):
		"""returns a dictionary containing query keywords for OAI interfaces
		from what's specified on the command line.
		"""
		kws = {"verb": self.verb} 
		if self.metadataPrefix:
			kws["metadataPrefix"] = self.metadataPrefix
		kws.update(moreArgs)
		
		if self.granularity=='YY-MM-DD':
			dateFormat = "%Y-%m-%d"
		else:
			dateFormat = "%Y-%m-%dT%H:%M:%SZ"
		if self.startDate:
			kws["from"] = self.startDate.strftime(dateFormat)
		if self.endDate:
			kws["until"] = self.endDate.strftime(dateFormat)

	 	if self.set:
			kws["set"] = self.set
		if self.maxRecords:
			kws["maxRecords"] = str(self.maxRecords)

		if self.identifier:
			kws["identifier"] = self.identifier

		if "resumptionToken" in kws:
			kws = {"resumptionToken": kws["resumptionToken"],
				"verb": kws["verb"]}
		return kws

	def doHTTP(self, **moreArgs):
		"""returns the result of parsing the current query plus
		moreArgs to the current registry.

		The result is returned as a string.
		"""
		srcURL = self.registry.rstrip("?"
			)+"?"+self._getOpQS(**self.getKWs(**moreArgs))
		base.ui.notifyInfo("OAI query %s"%srcURL)
		f = utils.urlopenRemote(srcURL)
		res = f.read()
		f.close()
		return res

	def _getOpQS(self, **args):
		"""returns a properly quoted HTTP query part from its (keyword) arguments.
		"""
		# we don't use urllib.urlencode to not encode empty values like a=&b=val
		qString = "&".join("%s=%s"%(k, urllib.quote(v)) 
			for k, v in args.iteritems() if v)
		return "%s"%(qString)

	def talkOAI(self, parserClass):
		"""processes an OAI dialogue for verb using the IdParser-derived 
		parserClass.
		"""
		res = self.doHTTP(verb=self.verb)
		handler = parserClass()
		try:
			xmlReader = sax.make_parser()
			xmlReader.setFeature(sax.handler.feature_namespaces, True)
			xmlReader.setContentHandler(handler)
			xmlReader.parse(StringIO(res))
			if self.contentCallback:
				self.contentCallback(res)
		except NoRecordsMatch:
			return []
		oaiResult = handler.getResult()

		while handler.resumptionToken is not None:
			resumptionToken = handler.resumptionToken
			handler = parserClass(oaiResult)
			try:
				res = self.doHTTP(verb=self.verb,
					resumptionToken=resumptionToken)
				sax.parseString(res, handler)
				if self.contentCallback:
					self.contentCallback(res)
			except NoRecordsMatch:
				break

		return oaiResult


def getIdentifiers(registry, startDate=None, endDate=None, set=None,
		granularity=None):
	"""returns a list of "short" records for what's in the registry specified
	by args.
	"""
	q = OAIQuery(registry, verb="ListIdentifiers", startDate=startDate,
		endDate=endDate, set=set)
	return q.talkOAI(IdParser)


def getRecords(registry, startDate=None, endDate=None, set=None,
		granularity=None):
	"""returns a list of "long" records for what's in the registry specified
	by args.

	parser should be a subclass of RecordParser; otherwise, you'll miss
	resumption and possibly other features.
	"""
	q = OAIQuery(registry, verb="ListRecords", startDate=startDate,
		endDate=endDate, set=set, granularity=granularity)
	return q.talkOAI(RecordParser)


def _addCanonicalNSDecls(xmlLiteral):
	"""adds XML namespace declarations for namespace prefixes we
	suspect in xmlLiteral.
	
	This is an ugly hack based on REs necessary because in the OAIRecordsParser
	we discard the namespace declarations.  It won't work with CDATA
	sections, and it'll make a hash of things if namespace declarations are
	already present.  However, for the use case of making the mutilated
	resource records coming out of the OAIRecordsParser valid, it will just
	do.

	Without an XML schema and a full parse (which of course is impossible
	without the necessary declarations), this is, really, not possible.  But
	the whole idea of canonical namespace prefixes is a mess, and so we
	hack along; in particular, we accept any string of the form \w+: within
	what looks like an XML tag as a namespace.  Oh my.
	"""
	prefixesUsed = set()
	for elementContent in re.finditer("<[^>]+>", xmlLiteral):
		prefixesUsed |= set(re.findall("([a-zA-Z_]\w*):[a-zA-Z_]", 
			elementContent.group()))

	cp = getCanonicalPrefixes()
	nsDecls = " ".join('xmlns:%s=%s'%(
			pref, utils.escapeAttrVal(cp.getNSForPrefix(pref)))
		for pref in prefixesUsed)
	return re.sub("<([\w:-]+)", r"<\1 "+nsDecls, xmlLiteral, 1)
	

def getRecord(registry, identifier):
	"""returns the XML form of an OAI-PMH record for identifier from
	the OAI-PMH endpoint at URL registry.

	This uses the OAIRecordsParser which enforces canonical prefixes,
	and the function will add their declarations as necessary.  This also means
	that evil registry records could be broken by us.
	"""
	q = OAIQuery(registry, verb="GetRecord", identifier=identifier)
	res = q.talkOAI(OAIRecordsParser)
	dest, row = res[0]
	assert dest=='oairecs'
	return _addCanonicalNSDecls(row["oaixml"])


def parseRecord(recordXML):
	"""returns some main properties from an XML-encoded VOResource record.

	recordXML can be an OAI-PMH response or just a naked record.  If multiple
	records are contained in recordXML, only the first will be returned.

	What's coming back is a dictionary as produced by RecordParser.
	"""
	handler = RecordParser()
	sax.parseString(recordXML, handler)
	return handler.recs[0]


def getServerProperties(registry):
	"""returns a ServerProperties instance for registry.

	In particular, you can retrieve the granularity argument that
	actually matches the registry from the result's granularity attribute.
	"""
	q = OAIQuery(registry, verb="Identify", metadataPrefix=None)
	return q.talkOAI(IdentifyParser)
