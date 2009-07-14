"""
Common functions and classes for services and cores.
"""

import re
import os
import urllib


from nevow import tags as T, entities as E
from nevow import inevow

import pkg_resources

from zope.interface import implements

from gavo import base
from gavo.base import meta
from gavo.imp import formal


class Error(base.Error):
	pass


class UnknownURI(Error):
	"""signifies that a HTTP 404 should be returned by the dispatcher.
	"""

class ForbiddenURI(Error):
	"""signifies that a HTTP 403 should be returned by the dispatcher.
	"""

class Authenticate(Error):
	"""signifies that a HTTP 401 should be returned by the dispatcher.
	"""

class WebRedirect(Error):
	"""causes the dispatcher to redirect the client to the URL in the exception's
	value.
	"""


def parseServicePath(serviceParts):
	"""returns a tuple of resourceDescriptor, serviceName.

	A serivce id consists of an inputsDir-relative path to a resource 
	descriptor, a slash, and the name of a service within this descriptor.

	This function returns a tuple of inputsDir-relative path and service name.
	It raises a gavo.Error if sid has an invalid format.  The existence of
	the resource or the service are not checked.
	"""
	return "/".join(serviceParts[:-1]), serviceParts[-1]


class QueryMeta(dict):
	"""is a class keeping all data *about* a query, e.g., the
	requested output format.

	It is constructed with a plain dictionary (constructors for nevow contexts
	and requests are below).
	
	The dictionary maps to values directly, so nevow request.args need
	to be adapted (which is done in the constructor below).

	If you pass an empty dict, some sane defaults will be used.  You
	can get that "empty" query meta as common.emptyQueryMeta, but make
	sure you don't mutate it.

	QueryMetas constructed from request will have the user and password
	items filled out.

	If you're using nevow formal, you should set the formal_data item
	to the dictionary created by formal.  This will let people use
	the parsed parameters in templates.
	"""
	
	# a set of keys handled by query meta to be ignored in parameter
	# lists because they are used internally.  This covers everything 
	# QueryMeta interprets, but also keys by introduced by certain gwidgets
	# and the nevow infrastructure
	metaKeys = set(["_DBOPTIONS", "_FILTER", "_OUTPUT", "_charset_", "_ADDITEM",
		"__nevow_form__", "_FORMAT", "_VERB", "_TDENC", "formal_data",
		"_SET"])
	# a set of keys that has sequences as values (needed for construction
	# from nevow request.args)
	listKeys = set(["_ADDITEM", "_DBOPTIONS_ORDER"])

	def __init__(self, initArgs=None):
		if initArgs is None:
			initArgs = {}
		self.ctxArgs = initArgs
		self["formal_data"] = {}
		self["user"] = self["password"] = None
		self._fillOutput(initArgs)
		self._fillDbOptions(initArgs)
		self._fillSet(initArgs)
	
	def _fillOutput(self, args):
		"""interprets values left by the OutputFormat widget.
		"""
		self["format"] = args.get("_FORMAT", "HTML")
		try:
# prefer fine-grained "verbosity" over _VERB or VERB
# Hack: malformed _VERBs result in None verbosity, which is taken to
# mean about "use fields of HTML".  Absent _VERB or VERB, on the other
# hand, means VERB=2, i.e., a sane default
			if "verbosity" in args:
				self["verbosity"] = int(args["verbosity"])
			elif "_VERB" in args:  # internal verb parameter
				self["verbosity"] = int(args["_VERB"])*10
			elif "VERB" in args:   # verb parameter for SCS and such
				self["verbosity"] = int(args["VERB"])*10
			else:
				self["verbosity"] = 20
		except ValueError:
			self["verbosity"] = "HTML"  # VERB given, but not an int.
		try:
			self["tdEnc"] = base.parseBooleanLiteral(args.get("_TDENC", "False"))
		except base.LiteralParseError:
			self["tdEnc"] = False
		self["additionalFields"] = args.get("_ADDITEM", [])

	def _fillSet(self, args):
		"""interprets the output of a ColumnSet widget.
		"""
		self["columnSet"] = None
		if "_SET" in args:
			self["columnSet"] = args["_SET"]

	def _fillDbOptions(self, args):
		self["dbLimit"] = base.getConfig("db", "defaultLimit")
		try:
			if "_DBOPTIONS_LIMIT" in args:
				self["dbLimit"] = int(args["_DBOPTIONS_LIMIT"])
		except ValueError:  # leave default limit
			pass
		self["dbSortKeys"] = [s.strip() for s in args.get("_DBOPTIONS_ORDER", [])
			if s.strip()]

	def overrideDbOptions(self, sortKeys=None, limit=None):
		if sortKeys is not None:
			self["dbSortKeys"] = sortKeys
		if limit is not None:
			self["dbLimit"] = int(limit)

	def asSQL(self):
		"""returns the dbLimit and dbSortKey values as an SQL fragment.
		"""
		frag, pars = [], {}
		sortKeys = self["dbSortKeys"]
		dbLimit = self["dbLimit"]
		if sortKeys:
			# Ok, we need to do some emergency securing here.  There should be
			# pre-validation that we're actually seeing a column key, but
			# just in case let's make sure we're seeing an SQL identifier.
			# (We can't rely on dbapi's escaping since we're not talking values here)
			frag.append("ORDER BY %s"%(",".join(
				re.sub("[^A-Za-z_]+", "", key) for key in sortKeys)))
		if dbLimit:
			frag.append("LIMIT %(_matchLimit)s")
			pars["_matchLimit"] = int(dbLimit)+1
		return " ".join(frag), pars

	@classmethod
	def fromRequest(cls, request):
		"""constructs a QueryMeta from a nevow request.
		"""
		args = {}
		for key, value in request.args.iteritems():
			if key in cls.listKeys:
				args[key] = value
			else:
				if value:
					args[key] = value[0]
		res = cls(args)
		res["user"], res["password"] = request.getUser(), request.getPassword()
		return res
	
	@classmethod
	def fromContext(cls, ctx):
		"""constructs a QueryMeta from a nevow context.
		"""
		return cls.fromRequest(inevow.IRequest(ctx))


emptyQueryMeta = QueryMeta()
