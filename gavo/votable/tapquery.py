"""
An interface to querying TAP servers (i.e., a TAP client).
"""

import datetime
import httplib
import time
import traceback
import urllib
import urlparse
from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
from xml import sax

from gavo import utils
from gavo.votable.model import VOTable as V


# Ward against typos
PENDING = "PENDING"
QUEUED = "QUEUED"
EXECUTING = "EXECUTING"
COMPLETED = "COMPLETED"
ERROR = "ERROR"
ABORTED = "ABORTED"


debug = True


class Error(utils.Error):
	"""The base class for all TAP-related exceptions.
	"""


class ProtocolError(Error):
	"""is raised when the remote server violated the local assumptions.
	"""


class WrongStatus(ProtocolError):
	"""is raised when request detects the server returned an invalid
	status.

	These are constructed with the status returnd (available as
	foundStatus) data payload of the response (available as payload).
	"""
	def __init__(self, msg, foundStatus, payload, hint=None):
		ProtocolError.__init__(self, msg, hint)
		self.args = [msg, foundStatus, payload, hint]
		self.payload, self.foundStatus = payload, foundStatus


class RemoteError(Error):
	"""is raised when the remote size signals an error.

	The content of the remote error document can be retrieved in the 
	remoteMessage attribute.
	"""
	def __init__(self, remoteMessage):
		self.remoteMessage = remoteMessage
		Error.__init__(self, 
			"Remote: "+remoteMessage,
			hint="This means that"
			" something in your query was bad according to the server."
			"  Details may be available in the Exceptions' remoteMessage"
			" attribute")
		self.args = [remoteMessage]

	def __str__(self):
		return self.remoteMessage


class RemoteAbort(Error):
	"""is raised by certain check functions when the remote side has aborted
	the job.
	"""
	def __init__(self):
		Error.__init__(self, "Aborted")
		self.args = []
	
	def __str__(self):
		return "The remote side has aborted the job"


class _FormData(MIMEMultipart):
	"""is a container for multipart/form-data encoded messages.

	This is usually used for file uploads.
	"""
	def __init__(self):
		MIMEMultipart.__init__(self, "form-data")
		self.set_param("boundary", "========== bounda r y 930 ")
		self.epilogue = ""
	
	def addFile(self, paramName, fileName, data):
		"""attaches the contents of fileName under the http parameter name
		paramName.
		"""
		msg = Message()
		msg.set_type("application/octet-stream")
		msg["Content-Disposition"] = "form-data"
		msg.set_param("name", paramName, "Content-Disposition")
		msg.set_param("filename", fileName, "Content-Disposition")
		msg.set_payload(data)
		self.attach(msg)

	def addParam(self, paramName, paramVal):
		"""adds a form parameter paramName with the (string) value paramVal
		"""
		msg = Message()
		msg["Content-Disposition"] = "form-data"
		msg.set_param("name", paramName, "Content-Disposition")
		msg.set_payload(paramVal)
		self.attach(msg)

	@classmethod
	def fromDict(cls, dict):
		self = cls()
		for key, value in dict.iteritems():
			self.addParam(key, value)
		return self


def _makeFlatParser(parseFunc):
	"""returns a "parser" class for _parseWith just calling a function on a string.

	_parseWith is designed for utils.StartEndParsers, but it's convenient
	to use it when there's no XML in the responses as well.

	So, this class wraps a simple function into a StartEndParser-compatible
	form.
	"""
	class FlatParser(object):
		def parseString(self, data):
			self.result = parseFunc(data)
		def getResult(self):
			return self.result
	return FlatParser


def _parseWith(parser, data):
	"""uses the utils.StartEndParser-compatible parser to parse the string data.
	"""
	try:
		parser.parseString(data)
		return parser.getResult()
	except (ValueError, IndexError, sax.SAXParseException):
		if debug:
			traceback.print_exc()
			f = open("server_response", "w")
			f.write(data)
			f.close()
		raise ProtocolError("Malformed response document.", hint=
			"If debug was enabled, you will find the server response in"
			" the file server_response.")


class _PhaseParser(utils.StartEndHandler):
	def _end_phase(self, name, attrs, content):
		return content


class _QuoteParser(utils.StartEndHandler):
	quote = None
	def _end_quote(self, name, attrs, content):
		if content.strip():
			self.quote = int(content)
			if self.quote<0:
				self.quote = None
	
	def getResult(self):
		return self.quote


class _ParametersParser(utils.StartEndHandler):
	def __init__(self):
		self.parameters = {}
		utils.StartEndHandler.__init__(self)

	def _end_parameter(self, name, attrs, content):
		self.parameters[attrs["id"]] = content
	
	def getResult(self):
		return self.parameters


class _AvailabilityParser(utils.StartEndHandler):
# VOSI
	available = None
	def _end_available(self, name, attrs, content):
		content = content.strip()
		if content=="true":
			self.available = True
		elif content=="false":
			self.available = False

	def getResult(self):
		return self.available


def _pruneAttrNS(attrs):
	return dict((k.split(":")[-1], v) for k,v in attrs.items())


class _CapabilitiesParser(utils.StartEndHandler):
# VOSI; each capability is a dict with at least a key interfaces.
# each interface is a dict with key type (namespace prefix not expanded; 
# change that?), accessURL, and use.
	def __init__(self):
		utils.StartEndHandler.__init__(self)
		self.capabilities = []

	def _start_capability(self, name, attrs):
		self.curCap = {"interfaces": []}
		self.curCap["standardID"] = attrs.get("standardID")

	def _end_capability(self, name, attrs, content):
		self.capabilities.append(self.curCap)
		self.curCap = None

	def _start_interface(self, name, attrs):
		attrs = _pruneAttrNS(attrs)
		self.curInterface = {"type": attrs["type"], "role": attrs.get("role")}

	def _end_interface(self,name, attrs, content):
		self.curCap["interfaces"].append(self.curInterface)
		self.curInterface = None

	def _end_accessURL(self, name, attrs, content):
		self.curInterface["accessURL"] = content.strip()
		self.curInterface["use"] = attrs.get("use")
	
	def getResult(self):
		return self.capabilities


class _TablesParser(utils.StartEndHandler):
# VOSI
	def __init__(self):
		utils.StartEndHandler.__init__(self)
		self.tables = []
		self.curCol = None
	
	def _start_table(self, name, attrs):
		self.tables.append(V.TABLE())
	
	def _start_column(self, name, attrs):
		self.curCol = V.FIELD()

	def _end_column(self, name, attrs, content):
		self.tables[-1][self.curCol]
		self.curCol = None

	def _end_description(self, attName, attrs, content):
		if self.getParentTag()=="table":
			destObj = self.tables[-1]
		elif self.getParentTag()=="column":
			destObj = self.curCol
		else:
			# name/desc of something else -- ignore
			return
		destObj[V.DESCRIPTION[content]]

	def _endColOrTableAttr(self, attName, attrs, content):
		if self.getParentTag()=="table":
			destObj = self.tables[-1]
		elif self.getParentTag()=="column":
			destObj = self.curCol
		else:
			# name/desc of something else -- ignore
			return
		destObj(**{str(attName): content.strip()})
	
	_end_name = _endColOrTableAttr
	
	def _endColAttr(self, attName, attrs, content):
		self.curCol(**{str(attName): content.strip()})

	_end_unit = _end_ucd = _endColAttr
	
	def _end_dataType(self, attName, attrs, content):
		self.curCol(datatype=content.strip())
		if attrs.has_key("arraysize"):
			self.curCol(arraysize=attrs["arraysize"])

	def getResult(self):
		return self.tables


class UWSResult(object):
	"""a container type for a result returned by an UWS service.

	It exposes id, href, and type attributes.
	"""
	def __init__(self, href, id=None, type=None):
		self.href, self.id, self.type = href, id, type


class ResultsParser(utils.StartEndHandler):
	def __init__(self):
		self.results = []
		utils.StartEndHandler.__init__(self)

	def _end_result(self, name, attrs, content):
		attrs = self.getAttrsAsDict(attrs)
		self.results.append(UWSResult(attrs["href"],
			attrs.get("id"), attrs.get("type", "simple")))
	
	def getResult(self):
		return self.results


def request(host, path, data="", customHeaders={}, method="GET",
		expectedStatus=None, encodeAsForm=False):
	"""returns a HTTPResponse object for an HTTP request to path on host.

	This function builds a new connection for every request.

	On the returned object, you cannot use the read() method.	Instead
	any data returned by the server is available in the data attribute.

	data usually is a byte string, but you can also pass a dictionary
	which then will be serialized using _FormData above.
	"""
	headers = {"connection": "close",
		"user-agent": "Python TAP library http://vo.uni-hd.de/odocs"}
	if not isinstance(data, basestring):
		if encodeAsForm:
			data = urllib.urlencode(data)
			headers["Content-Type"] = "application/x-www-form-urlencoded"
		else:
			form = _FormData.fromDict(data)
			data = form.as_string()
			headers["Content-Type"] = form.get_content_type()+'; boundary="%s"'%(
					form.get_boundary())
	headers.update(customHeaders)
	conn = httplib.HTTPConnection(host)
	conn.request(method, path, data, headers)
	resp = conn.getresponse()
	resp.data = resp.read()
	conn.close()
	if expectedStatus is not None:
		if resp.status!=expectedStatus:
			raise WrongStatus("Expected status %s, got status %s"%(
				expectedStatus, resp.status), resp.status, resp.data)
	return resp


def _makeAtomicValueGetter(methodPath, parser):
# This is for building ADQLTAPJob's properties (phase, etc.)
	def getter(self):
		destURL = self.jobPath+methodPath
		response = request(self.destHost, destURL, expectedStatus=200)
		return _parseWith(parser(), response.data)
	return getter


def _makeAtomicValueSetter(methodPath, serializer, parameterName):
# This is for building ADQLTAPJob's properties (phase, etc.)
	def setter(self, value):
		destURL = self.jobPath+methodPath
		response = request(self.destHost, destURL, 
			{parameterName: serializer(value)}, method="POST",
			expectedStatus=303)
	return setter


class _WithEndpoint(object):
	"""A helper class for classes constructed with an ADQL endpoint.
	"""
	def _defineEndpoint(self, endpointURL):
		self.endpointURL = endpointURL
		parts = urlparse.urlsplit(self.endpointURL)
		assert parts.scheme=="http"
		self.destHost = parts.hostname
		if parts.port:
			self.destHost = "%s:%s"%(self.destHost, parts.port)
		self.destPath = parts.path
		if self.destPath.endswith("/"):
			self.destPath = self.destPath[:-1]


class ADQLTAPJob(_WithEndpoint):
	"""A facade for an ADQL-based async TAP job.

	Construct it with the URL of the async endpoint and a query.
	"""
	def __init__(self, endpointURL, query, lang="ADQL", userParams={}):
		self._defineEndpoint(endpointURL)
		self.destPath = self.destPath+"/async"
		self.lang = lang
		self.query = query
		self.jobId, self.jobPath = None, None
		self.encodeAsForm = encodeAsForm
		self._createJob(userParams)

	def _canUseFormEncoding(self, userParams):
		"""returns true if userParams can be transmitted in a 
		x-www-form-urlencoded payload.
		"""
		for val in userParams.values():
			if not isinstance(val, basestring):
				return False
		return True

	def _createJob(self, userParams):
		params = {
			"REQUEST": "doQuery",
			"LANG": self.lang,
			"QUERY": self.query}
		for k,v in userParams.iteritems():
			params[k] = str(v)
		response = request(self.destHost, self.destPath, params,
			method="POST", expectedStatus=303, encodeAsForm=self.encodeAsForm)
		# The last part of headers[location] now contains the job id
		try:
			self.jobId = urlparse.urlsplit(
				response.getheader("location", "")).path.split("/")[-1]
			self.jobPath = "%s/%s"%(self.destPath, self.jobId)
		except ValueError:
			raise utils.logOldExc(
				ProtocolError("Job creation returned invalid job id"))

	def delete(self):
		"""removes the job on the remote side.
		"""
		if self.jobPath is not None:
			response = request(self.destHost, self.jobPath, method="DELETE",
				expectedStatus=303)

	def start(self):
		"""asks the remote side to start the job.
		"""
		response = request(self.destHost, self.jobPath+"/phase", 
			{"PHASE": "RUN"}, method="POST", expectedStatus=303)

	def abort(self):
		"""asks the remote side to abort the job.
		"""
		response = request(self.destHost, self.jobPath+"/phase", 
			{"PHASE": "ABORT"}, method="POST", expectedStatus=303)

	def raiseIfError(self):
		"""raises an appropriate error message if job has thrown an error or
		has been aborted.
		"""
		phase = self.phase
		if phase==ERROR:
			raise RemoteError(self.getErrorFromServer())
		elif phase==ABORTED:
			raise RemoteAbort()

	def waitForPhases(self, phases, pollInterval=1, increment=1.189207115002721,
			giveUpAfter=None):
		"""waits for the job's phase to become one of the set phases.

		This method polls.  Initially, it does increases poll times
		exponentially with increment until it queries every two minutes.

		The magic number in increment is 2**(1/4.).

		giveUpAfter, if given, is the number of iterations this method will
		do.  If none of the desired phases have been found until then,
		raise a ProtocolError.
		"""
		attempts = 0
		while True:
			curPhase = self.phase 
			if curPhase in phases:
				break
			time.sleep(pollInterval)
			pollInterval = min(120, pollInterval*increment)
			attempts += 1
			if giveUpAfter:
				if attempts>giveUpAfter:
					raise ProtocolError("None of the states in %s were reached"
						" in time."%repr(phases),
					hint="After %d attempts, phase was %s"%(attempts, curPhase))

	def run(self, pollInterval=1):
		"""runs the job and waits until it has finished.

		The function raises an exception with an error message gleaned from the
		server.
		"""
		self.start()
		self.waitForPhases(set([COMPLETED, ABORTED, ERROR]))
		self.raiseIfError()

	executionduration = property(
		_makeAtomicValueGetter("/executionduration", _makeFlatParser(float)),
		_makeAtomicValueSetter("/executionduration", str, "EXECUTIONDURATION"))

	destruction = property(
		_makeAtomicValueGetter("/destruction", _makeFlatParser(utils.parseISODT)),
		_makeAtomicValueSetter("/destruction", utils.formatISODT, "DESTRUCTION"))

	def makeJobURL(self, jobPath):
		return self.endpointURL+"/async/%s%s"%(self.jobId, jobPath)

	def _queryJobResource(self, path, parser):
		# a helper for phase, quote, etc.
		response = request(self.destHost, self.jobPath+path,
			expectedStatus=200)
		return _parseWith(parser, response.data)

	@property
	def phase(self):
		"""returns the phase the job is in according to the server.
		"""
		return self._queryJobResource("/phase", _PhaseParser())

	@property
	def quote(self):
		"""returns the estimate the server gives for the run time of the job.
		"""
		return self._queryJobResource("/quote", _QuoteParser())

	@property
	def owner(self):
		"""returns the owner of the job.
		"""
		return self._queryJobResource("/owner", _makeFlatParser(str)())

	@property
	def parameters(self):
		"""returns a dictionary mapping passed parameters to server-provided
		string representations.

		To set a parameter, use the setParameter function.  Changing the
		dictionary returned here will have no effect.
		"""
		return self._queryJobResource("/parameters", _ParametersParser())

	@property
	def allResults(self):
		"""returns a list of UWSResult instances.
		"""
		return self._queryJobResource("/results", ResultsParser())

	def openResult(self):
		"""returns a file-like object you can read the default TAP result off.

		To have the embedded VOTable returned, say
		votable.load(job.openResult()).
		"""
		return urllib.urlopen(self.makeJobURL("/results/result"))

	def setParameter(self, key, value):
		request(self.destHost, self.jobPath+"/parameters",
			data={key: value}, method="POST", expectedStatus=303)

	def getErrorFromServer(self):
		"""returns the error message the server gives, verbatim.
		"""
		return request(self.destHost, self.jobPath+"/error",
			expectedStatus=200).data

	def addUpload(self, name, data):
		"""adds uploaded tables, either from a file or as a remote URL.

		You should not try to change UPLOAD yourself (e.g., using setParameter).

		Data is either a string (i.e. a URI) or a file-like object (an upload).
		"""
		uploadFragments = []
		form = _FormData()
		if isinstance(data, basestring): # a URI
			assert ',' not in data
			assert ';' not in data
			uploadFragments.append("%s,%s"%(name, data))
		else: # Inline upload, data is a file
			uploadKey = utils.intToFunnyWord(id(data))
			form.addFile(uploadKey, uploadKey, data.read())
			uploadFragments.append("%s,param:%s"%(name, uploadKey))
		form.addParam("UPLOAD", ";".join(uploadFragments))
		request(self.destHost, self.jobPath+"/parameters", method="POST",
			data=form.as_string(), expectedStatus=303, 
			customHeaders={"content-type": 
				form.get_content_type()+'; boundary="%s"'%(form.get_boundary())})


class ADQLEndpoint(_WithEndpoint):
	"""A facade for an ADQL endpoint.

	This is only needed for inspecting server metadata (i.e., in general
	only for rather fancy applications).
	"""
	def __init__(self, endpointURL):
		self._defineEndpoint(endpointURL)
	
	def createJob(self, query, lang="ADQL-2.0", userParams={}):
		return ADQLTAPJob(self.endpointURL, query, lang, userParams)

	@property
	def available(self):
		"""returns True, False, or None (undecidable).

		None is returned when /availability gives a 404 (which is legal)
		or the returned document doesn't parse.
		"""
		try:
			response = request(self.destHost, self.destPath+"/availability",
				expectedStatus=200)
			res = _parseWith(_AvailabilityParser(), response.data)
		except WrongStatus:
			res = None
		return res
	
	@property
	def capabilities(self):
		"""returns a dictionary containing some meta info on the remote service.

		Keys to look for include title, identifier, contact (the mail address),
		and referenceURL.

		If the remote server doesn't return capabilities as expected, an
		empty dict is returned.
		"""
		return _parseWith(_CapabilitiesParser(), 
				request(self.destHost, self.destPath+"/capabilities").data)

	@property
	def tables(self):
		"""returns a sequence of table definitions for the tables accessible
		through this service.

		The table definitions come as gavo.votable.Table instances.
		"""
		return _parseWith(_TablesParser(),
				request(self.destHost, self.destPath+"/tables").data)
