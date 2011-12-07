"""
A simple client of OAI-http.

This includes both some high-level functions and rudimentary parsers
that can serve as bases for more specialized parsers.
"""

import urllib
from xml import sax


from gavo import base
from gavo import utils


class FailedQuery(Exception):
	pass


class NoRecordsMatch(Exception):
	pass


class IdParser(utils.StartEndHandler):
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

	def _end_identifier(self, name, attrs, content):
		self.recs[-1]["id"] = content
	
	def _end_datestamp(self, name, attrs, content):
		self.recs[-1]["date"] = utils.parseISODT(content)
	
	def _start_header(self, name, attrs):
		self.recs.append({})

	def _end_error(self, name, attrs, content):
		if attrs["code"]=="noRecordsMatch":
			raise NoRecordsMatch()
		raise FailedQuery("Registry bailed with code %s, value %s"%(
			attrs["code"], content))

	def _end_resumptionToken(self, name, attrs, content):
		if content.strip():
			self.resumptionToken = content


class RecordParser(IdParser):
	"""A simple parser for ivo_vor records.
	"""
	def _end_title(self, name, attrs, content):
		if self.getParentTag()=="Resource":
			self.recs[-1][name] = content

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



class OAIQuery(object):
	"""A container for queries to OAI interfaces.
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
			metadataPrefix="ivo_vor"):
		self.registry = registry
		self.verb, self.set = verb, set
		self.startDate, self.endDate = startDate, endDate
		self.metadataPrefix = metadataPrefix

	def getKWs(self, **moreArgs):
		"""returns a dictionary containing query keywords for OAI interfaces
		from what's specified on the command line.
		"""
		kws = {"verb": self.verb, "metadataPrefix": self.metadataPrefix}
		kws.update(moreArgs)
		# XXX TODO: allow for different granularities
		if self.startDate:
			kws["from"] = self.startDate.strftime("%Y-%m-%dT%H:%M:%S")
		if self.endDate:
			kws["until"] = self.endDate.strftime("%Y-%m-%dT%H:%M:%S")
	 	if self.set:
			kws["set"] = self.set
		if self.maxRecords:
			kws["maxRecords"] = str(self.maxRecords)
		return kws

	def doHTTP(self, **moreArgs):
		"""returns the result of parsing the current query plus
		moreArgs to the current registry.

		The result is returned as a string.
		"""
		f = utils.urlopenRemote(
			self.registry+"?"+self._getOpQS(**self.getKWs(**moreArgs)))
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
		"""processes an OAI dialogue for verb using the IdParser-derived parserClass.
		"""
		res = self.doHTTP(metadataPrefix="ivo_vor", verb=self.verb)
		handler = parserClass()
		try:
			sax.parseString(res, handler)
		except NoRecordsMatch:
			return []
		recs = handler.recs
		while handler.resumptionToken is not None:
			resumptionToken = handler.resumptionToken
			handler = parserClass(recs)
			try:
				sax.parseString(self.doHTTP(metadataPrefix="ivo_vor", verb=self.verb,
					resumptionToken=resumptionToken),
					handler)
			except NoRecordsMatch:
				break
		return recs


def getIdentifiers(registry, startDate=None, endDate=None, set=None):
	"""returns a list of "short" records for what's in the registry specified
	by args.
	"""
	q = OAIQuery(registry, verb="ListIdentifiers", startDate=startDate,
		endDate=endDate, set=set)
	return q.talkOAI(IdParser)


def getRecords(registry, startDate=None, endDate=None, set=None):
	"""returns a list of "long" records for what's in the registry specified
	by args.

	parser should be a subclass of RecordParser; otherwise, you'll miss
	resumption and possibly other features.
	"""
	q = OAIQuery(registry, verb="ListRecords", startDate=startDate,
		endDate=endDate, set=set)
	return q.talkOAI(RecordParser)


