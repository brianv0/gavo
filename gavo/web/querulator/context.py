""" 
This module contains the context class used to pass around data
describing the query and providing an abstraction of the input parameters.
"""

import cgi
import re
import os
import sys
import string
import urllib

from mx import DateTime

try:
	import mod_python.util
	from mod_python import apache
except ImportError:
	# So, you can't use ModpythonContext.  What did you expect?
	pass

import gavo
from gavo import config
from gavo import sqlsupport
from gavo import simbadinterface
from gavo.web import querulator


def _fixDoctype(aString):
	"""adds a transitional html doctype if none is present.
	"""
	if not aString.startswith("<!DOCTYPE"):
		aString = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"'
			' "http://www.w3.org/TR/html4/loose.dtd">')+aString
	return aString


class Context:
	"""is a model for the context the query runs in.

	This is an abstract class -- concrete derivations have to fill in
	the _initArguments, _initUser, and _initPathinfo methods.

	_initArguments has to fill out the arguments dictionary, mapping
	query arguments to lists of their values.  Empty arguments must
	be suppressed.

	_initPathinfo has to fill in the pathInfo attribute with the
	relative path to the request with no leading or trailing slashes.

	_initUser has to fill in the loggedUser attribute.

	They also have to provide 

	* a getQuerier method that returns an sqlsupport.SimpleQuerier instance.
	* a debugOutput method that has a printf-like interface and writes
	  the message into the server log.
	* a getServerURL method that returns the URL of the server.

	Ideally, it should abstract away the details of the framework needed.
	It could be subclassed to provide WsgiContext, CgiContext, etc. 

	Deriving classes should call _initEnv(environ) with a dictionary
	containing the current environment information.
	"""
	def __init__(self):
		self._initUser()
		self._initArguments()
		self._initPathinfo()
		self.uidsGivenOut = set()
		self.warnings = []
	
	def __contains__(self, element):
		return element in self.arguments

	def _initEnv(self, environ):
		gavoHome = config.get("rootDir")
		self.environment = {
			"GAVO_HOME": gavoHome,
			"GAVO_INPUTS": os.path.join(gavoHome, "inputs"),
			"QERL_TPL_ROOT": os.path.join(gavoHome, "web", "querulator", 
				"templates"),
			"MASQ_TPL_ROOT": os.path.join(gavoHome, "web", "masquerator", 
				"templates"),
			"ROOT_URL": config.get("web", "rootURL"),
			"STATIC_URL": config.get("web", "staticURL"),
		}

	def getEnv(self, key):
		return self.environment[key]

	def keys(self):
		return self.arguments.keys()

	def iteritems(self):
		return self.arguments.iteritems()

	def addArgument(self, key, value):
		if isinstance(value, list):
			self.arguments[key] = value
		else:	
			self.arguments[key] = [value]

	def addArguments(self, kvPairs):
		for key, value in kvPairs:
			self.addArgument(key, value)

	def hasArgument(self, name):
		return self.arguments.has_key(name)

	def checkArguments(self, requiredArgs):
		"""returns True if all requiredArgs are present in self.
		"""
		for name in requiredArgs:
			if not self.hasArgument(name):
				return False
		return True

	def addWarning(self, warning):
		self.warnings.append(warning)
	
	def getWarnings(self):
		return self.warnings

	def getfirst(self, name, default=None):
		return self.arguments.get(name, [default])[0]

	get = getfirst

	def getlist(self, name):
		return self.arguments.get(name, [])

	def getUser(self):
		return self.loggedUser
	
	def getPathInfo(self):
		return self.pathInfo

	def getQueryItems(self, suppress=[]):
		"""returns a list of (name, value) tuples to characterize the
		query.

		All values are serialized into strings.

		Suppress is something that one can check with in and contains
		keys that should not be included.
		"""
		items = []
		for name, value in self.iteritems():
			if name in suppress:
				continue
			if isinstance(value, list):
				for item in value:
					items.append((name, str(item)))
			else:
				items.append((name, str(value)))
		return items

	def getHiddenForm(self, suppress=[]):
		"""returns an html form body setting all relevant query parameters
		from context in hidden fields.

		This can be used to reproduce queries with different meta parameters.
		("this stuff as tar", "this stuff as votable").
		"""
		return "\n".join(['<input type="hidden" name="%s" value=%s>'%(
				name, repr(value))
			for name, value in self.getQueryItems(suppress)])

	def getQueryArgs(self, suppress=[]):
		"""returns a query tag (url?query) to reproduce this query.
		"""
		return "&".join(["%s=%s"%(name, urllib.quote(value))
			for name, value in self.getQueryItems(suppress)])

	def isAuthorizedProduct(self, embargo, owner):
		"""returns true if a product with owner and embargo may currently be
		accessed.
		"""
		return (embargo<DateTime.today() or owner==self.getUser())

	def getUid(self, hint=None):
		"""returns a string that is unique within this context suitable as
		an SQL identifier.

		Right now, this is not terribly efficient if you don't provide a
		hint, so don't go getting hundreds of these.
		"""
		nukeNumbers = string.maketrans("0123456789", "abcdefghij")
		def makeUid(hint):
			return str(id(hint)).encode("hex").translate(nukeNumbers)
		uid = makeUid(hint)
		while uid in self.uidsGivenOut or uid in self.arguments:
			uid = makeUid(uid)
		self.uidsGivenOut.add(uid)
		return uid

	def _initSesame(self):
		self.sesame = simbadinterface.Sesame(id="sim_querulator", saveNew=True)

	def getSesame(self):
		if not hasattr(self, "sesame"):
			self._initSesame()
		return self.sesame


class CGIContext(Context):
	"""is a context for CGIs.
	"""
	def __init__(self):
		self._initEnv(os.environ)
		Context.__init__(self)
		try:
			self.querier = sqlsupport.SimpleQuerier()
		except sqlsupport.DatabaseError:
			self.querier = None

	def _initArguments(self):
		"""computes the dictionary of query arguments.

		In this CGI implementation, this may only run once (in other words,
		it would be an error to instanciate more than one Context object).
		"""
		self.arguments = {}
		form = cgi.FieldStorage()
		for key in form.keys():
			self.arguments[key] = form.getlist(key)
	
	def _initPathinfo(self):
		self.pathInfo = os.environ.get("PATH_INFO", "").strip("/")

	def _initUser(self):
		"""sets the loggedUser attribute from the environment.
		"""
		self.loggedUser = None
		if 	os.environ.get("AUTH_TYPE") and os.environ.get("REMOTE_USER"):
			self.loggedUser = os.environ.get("REMOTE_USER")
	
	def doHttpResponse(self, contentType, content, moreHeaders={}, 
			statusCode=200):
		"""does a CGI http response.

		statusCode is ignored, since we're not nph.
		"""
		print "Content-type: %s"%contentType
		if contentType.startswith("text/html"):
			content = _fixDoctype(content)
		if isinstance(content, basestring):
			print "Content-length: %d"%len(content)
		print "Connection: close"
		for key, value in moreHeaders.iteritems():
			print "%s: %s"%(key, value)
		print ""
		if isinstance(content, basestring):
			sys.stdout.write(content)
		else:
			content(sys.stdout)
	
	def debugOutput(self, msg, *args):
		sys.stderr.write((msg+"\n")%args)

	def getQuerier(self):
		return self.querier
	
	def getServerURL(self):
		return "http://"+os.environ["SERVER_NAME"]

	def getRemote(self):
		return os.environ["REMOTE_ADDR"]


class ModpyContext(Context):
	"""is a context for naked modpython.
	"""
	def __init__(self, req):
		self.modpyReq = req
		self._initEnv(self.modpyReq.subprocess_env)
		Context.__init__(self)
	
	def _initArguments(self):
		self.arguments = {}
		form = mod_python.util.FieldStorage(self.modpyReq)
		for key in form.keys():
			if isinstance(form[key], basestring):
				self.arguments[key] = [form[key]]
			else:
				self.arguments[key] = form[key]
	
	def _initPathinfo(self):
		pathinfo = self.modpyReq.path_info
		if pathinfo.startswith(config.get("web", "rootURL")):
			pathinfo = pathinfo[len(config.get("web", "rootURL")):]
		self.pathInfo = pathinfo.strip("/")
	
	def _initUser(self):
		self.loggedUser = None
		req = self.modpyReq
		req.get_basic_auth_pw()
		try:
			if req.ap_auth_type and req.user:
				self.loggedUser = req.user
		except AttributeError:
			# no login info, probably
			pass
	
	def doHttpResponse(self, contentType, content, moreHeaders={},
			statusCode=200):
		"""does a http response through mod_python.
		"""
		if contentType.startswith("text/html"):
			content = _fixDoctype(content)
		req = self.modpyReq
		if isinstance(content, basestring):
			req.headers_out["Content-length"] = "%d"%len(content)
		req.content_type = contentType
		req.status = statusCode
		for key, value in moreHeaders.iteritems():
			req.headers_out[key] = value
		req.send_http_header()
		if req.method!="HEAD":
			if isinstance(content, basestring):
				req.write(content)
			else:
				content(req)
	
	def debugOutput(self, msg, *args):
		sys.stderr.write((msg+"\n")%args)
		sys.stderr.flush()
	
	def getQuerier(self):
		if not hasattr(self, "querier") or self.querier==None:
			try:
				self.querier = sqlsupport.SimpleQuerier()
			except sqlsupport.DatabaseError:
				self.querier = None
		return self.querier

	def getServerURL(self):
		try:
			return ("http://"+
				self.modpyReq.connection.base_server.server_hostname).strip("/")
		except AttributeError:
			# why would connection have no server attribute?
			return "http://bad.error"
	
	def getRemote(self):
		return self.modpyReq.connection.remote_ip


class DebugContext(CGIContext):
	"""is a context you can stuff with your own values.
	"""
	def __init__(self, args={}, pathinfo="", user=None, remoteAddr="127.0.0.1"):
		CGIContext.__init__(self)
		self.arguments = {}
		for key, arg in args.iteritems():
			if isinstance(arg, list):
				self.arguments[key] = arg
			else:
				self.arguments[key] = [arg]
		self.pathinfo = ""
		self.loggedUser = None
		self.remoteAddr = remoteAddr
	
	def doHttpResponse(self, contentType, content, moreHeaders):
		print "Content-type:", contentType
		print "Additional Headers:", moreHeaders
		print ""
		print content

	def getServerUrl(self):
		return "fake://fake.fake.fake"
	
	def getRemote(self):
		return self.remote

