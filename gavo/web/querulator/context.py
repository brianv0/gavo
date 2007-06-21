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

from gavo import coords
from gavo.web import querulator


def _getSimbadPositions(identifier):
	"""returns ra and dec from Simbad for identifier.

	It raises a KeyError if Simbad doesn't know identifier.
	"""
	from gavo import simbadinterface
	data = simbadinterface.Sesame().query(identifier)
	if not data:
		raise KeyError(identifier)
	return float(data["RA"]), float(data["dec"])

def _handleSexagesimalCone(context):
	"""converts arguments provided by htmlgenfuncs.sexagConeSearch to
	predefined simple cone search arguments.
	"""
	if context.checkArguments(["sexagMixedPos", "SRminutes"]):
		mat = re.match("(.*)([+-].*)", context.getfirst("sexagMixedPos"))
		try:
			ra, dec = coords.hourangleToDeg(mat.group(1)), coords.dmsToDeg(
				mat.group(2))
		except (AttributeError, ValueError):
			try:
				ra, dec = _getSimbadPositions(context.getfirst("sexagMixedPos"))
			except KeyError:
				raise querulator.Error("Sexagesimal mixed positions must"
					" have a format like hh mm ss[.ddd] [+-]dd mm ss[.mmm] (the"
					" sign is important).  %s does not appear to be of this format,"
					" and also cannot be resolved by Simbad."%repr(
						context.getfirst("sexagMixedPos")))
		try:
			sr = float(context.getfirst("SRminutes"))/60
		except ValueError:
			raise querulator.Error("Search radius must be given as arcminutes"
				" float. %s is invalid."%repr(context.getfirst("SRminutes")))
		context.addArguments([("RA", ra), ("DEC", dec), ("SR", sr)])


_predefinedQueryHandlers = [
	_handleSexagesimalCone,
]


class Context:
	"""is a collection of context parameters for responding to a query.

	Ideally, it should abstract away the details of the framework needed.
	It could be subclassed to provide WsgiContext, CgiContext, etc.  For
	now, this is for CGI.

	The Context also calls the predefined query handlers at the end
	of its construction.
	"""
	def __init__(self):
		self._initUser()
		self._initArguments()
	
	def _initUser(self):
		"""sets the loggedUser attribute from the environment.
		"""
		self.loggedUser = None
		if 	os.environ.get("AUTH_TYPE") and os.environ.get("REMOTE_USER"):
			self.loggedUser = os.environ.get("REMOTE_USER")

	def _initArguments(self):
		"""computes the dictionary of query arguments.

		In this CGI implementation, this may only run once (in other words,
		it would be an error to instanciate more than one Context object).
		"""
		self.arguments = {}
		self.form = cgi.FieldStorage()
		for key in self.form.keys():
			self.arguments[key] = self.form.getlist(key)
		self._handlePredefinedArguments()
	
	def _handlePredefinedArguments(self):
		"""fills the arguments dictionary with additional keys for predefined
		queries.

		This is done by calling the handlers in _predefinedQueryHandlers.
		These then change or add arguments.  
		"""
		for handler in _predefinedQueryHandlers:
			handler(self)

	def __contains__(self, element):
		return element in self.arguments

	def keys(self):
		return self.arguments.keys()

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

	def checkArguments(context, requiredArgs):
		"""returns True if all requiredArgs are present in self.
		"""
		for name in requiredArgs:
			if not context.hasArgument(name):
				return False
		return True

	def getfirst(self, name):
		return self.arguments.get(name, [None])[0]
	
	def getlist(self, name):
		return self.arguments.get(name, [])

	def getUser(self):
		return self.loggedUser
