""" 
This module contains the context class used to pass around data
describing the query and providing an abstraction of the input parameters.

In the module, there are also "predefined query handlers". These are
functions that take a context and change it according to the need of
predefined queries (usually defined in htmlgenfuncs).  An example for
this is the sexagesimal cone search (see htmlgenfuncs) that provides
sexagMixedPos and SRminutes.  Its handler converts this to the predefined
RA, DEC and SR values requried for a predefined cone search.
"""

import cgi
import re
import os
import sys

from mx import DateTime

from gavo.web import querulator


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
	def _initArguments(self):
		"""computes the dictionary of query arguments.

		In this CGI implementation, this may only run once (in other words,
		it would be an error to instanciate more than one Context object).
		"""
		self.arguments = {}
		self.form = cgi.FieldStorage()
		for key in self.form.keys():
			self.arguments[key] = self.form.getlist(key)
	
	def _initPathinfo(self):
		self.pathInfo = os.environ.get("PATH_INFO", "").strip("/")

	def _initUser(self):
		"""sets the loggedUser attribute from the environment.
		"""
		self.loggedUser = None
		if 	os.environ.get("AUTH_TYPE") and os.environ.get("REMOTE_USER"):
			self.loggedUser = os.environ.get("REMOTE_USER")


