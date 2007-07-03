""" 
This module contains the context class used to pass around data
describing the query and providing an abstraction of the input parameters.
"""

import cgi
import re
import os
import sys

from mx import DateTime

try:
	import mod_python.util
	from mod_python import apache
except ImportError:
	# So, you can't use ModpythonContext.  What did you expect?
	pass

from gavo import sqlsupport
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
	It could be subclassed to provide WsgiContext, CgiContext, etc.  For
	now, this is for CGI.
	"""
	def __init__(self):
		self._initUser()
		self._initArguments()
		self._initPathinfo()
	
	def __contains__(self, element):
		return element in self.arguments

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

	def getfirst(self, name):
		return self.arguments.get(name, [None])[0]

	get = getfirst

	def getlist(self, name):
		return self.arguments.get(name, [])

	def getUser(self):
		return self.loggedUser
	
	def getPathInfo(self):
		return self.pathInfo
	
	def isAuthorizedProduct(self, embargo, owner):
		"""returns true if a product with owner and embargo may currently be
		accessed.
		"""
		return (embargo<DateTime.today() or owner==self.getUser())


class CGIContext(Context):
	"""is a context for CGIs.
	"""
	def __init__(self):
		Context.__init__(self)
		self.querier = sqlsupport.SimpleQuerier()

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
		self.pathInfo = self.modpyReq.path_info.strip("/")
	
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
		if not hasattr(self, "querier"):
			# We need a hack here since the environment variables probably
			# were "wrong" when config got imported.
			from gavo import config
			config.loadSettings(self.modpyReq.subprocess_env["GAVOSETTINGS"])
			self.querier = sqlsupport.SimpleQuerier()
		return self.querier

	def getServerURL(self):
		try:
			return "http://"+self.modpyReq.connection.server.server_hostname
		except AttributeError:
			# why would connection have no server attribute?
			return ""
	
	def getRemote(self):
		return self.modpyReq.connection.remote_ip
