"""
Common functions and classes for gavo web interfaces.
"""

import re
import os

import formal

from nevow import tags as T, entities as E
from nevow import loaders
from nevow import inevow
from nevow import util as nevowutil

from twisted.python import failure
from twisted.internet import defer

from zope.interface import implements

import gavo
from gavo import config
from gavo import record
from gavo import utils


class Error(gavo.Error):
	pass


#A sentinel for QueryMeta, mainly.
Undefined = object()


def resolvePath(rootPath, relPath):
	"""joins relPath to rootPath and makes sure the result really is
	in rootPath.
	"""
	relPath = relPath.lstrip("/")
	fullPath = os.path.realpath(os.path.join(rootPath, relPath))
	if not fullPath.startswith(rootPath):
		raise Error("I believe you are cheating -- you just tried to"
			" access %s, which I am not authorized to give you."%fullPath)
	if not os.path.exists(fullPath):
		raise Error("Invalid path %s.  This should not happen."%fullPath)
	return fullPath


class UnknownURI(Error):
	"""signifies that a http 404 should be returned to the dispatcher.
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


class doctypedStan(loaders.stan):
	"""is the stan loader with a doctype and a namespace added.
	"""

#	DOCTYPE = T.xml('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01'
#		' Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">')
#	DOCTYPE = T.xml('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"'
#		' "http://www.w3.org/TR/html4/strict.dtd">')
	DOCTYPE = T.xml('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
		' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">')

	def __init__(self, rootEl, pattern=None):
		super(doctypedStan, self).__init__(T.invisible[self.DOCTYPE, 
			rootEl(xmlns="http://www.w3.org/1999/xhtml")], pattern)

			
class CustomErrorMixin(object):
	"""is a mixin for renderers containing formal forms to emit
	custom error messages.

	This mixin expects to see "the" form as self.form and relies on
	the presence of a method _generateForm that arranges for that .
	This can usually be an alias for the form_xy method you need for
	formal (we actually pass a nevow context object to that function),
	but make sure you actually set self.form in there.

	You furthermore need to define methods:

	* _getInputData -- receives the form data and returns something
	* _handleInputData -- receives the result of _getInputData and the context
	  and returns something renderable (the result of renderHTTP)
	
	Both may return deferreds.

	You need to ctx.remember(self, inevow.ICanHandleException) in your __init__.
	"""
	implements(inevow.ICanHandleException)

	def renderHTTP(self, ctx):
		# This is mainly an extract of what we need of formal.Form.process
		# generate the form
		try:
			self._generateForm(ctx)
			request = inevow.IRequest(ctx)
			charset = nevowutil.getPOSTCharset(ctx)
			# Get the request args and decode the arg names
			args = dict([(k.decode(charset),v) for k,v in request.args.items()])
			self.form.errors.data = args
			# Iterate the items and collect the form data and/or errors.
			for item in self.form.items:
				item.process(ctx, self.form, args, self.form.errors)
			# format validation errors
			if self.form.errors:
				return self._handleInputErrors(self.form.errors.errors, ctx)
			return defer.maybeDeferred(self._getInputData, self.form.data
				).addCallback(self._handleInputData, ctx
				).addErrback(self._handleError, ctx)
		except:
			return self.renderHTTP_exception(ctx, failure.Failure())

	def renderHTTP_exception(self, ctx, failure):
		"""override for to emit custom errors for general failures.

		You'll usually want to do all writing yourself, finishRequest(False) your
		request and return appserver.errorMarker here.
		"""
		failure.printTraceback()

	def _handleInputErrors(self, errors, ctx):
		"""override to emit custom error messages for formal validation errors.
		"""
		if isinstance(errors, formal.FormError):
			msg = "Error(s) in given Parameters: %s"%"; ".join(
				[str(e) for e in errors])
		else:
			try:
				msg = errors.getErrorMessage()
			except AttributeError:
				msg = str(errors)
		return msg

	def _handleError(self, failure, ctx):
		"""use or override this to handle errors occurring during processing
		"""
		if isinstance(failure.value, gavo.ValidationError):
			return self._handleInputErrors(["Parameter %s: %s"%(
				failure.value.fieldName, failure.getErrorMessage())], ctx)
		return self.renderHTTP_exception(ctx, failure)


class GavoRenderMixin(object):
	"""is a mixin with renderers useful throughout the data center.

	Rendering of meta information:
	<tag n:render="meta">METAKEY</tag> or
	<tag n:render="metahtml">METAKEY</tag>

	Rendering internal links (important of off-root operation):
	<tag href|src="/foo" n:render="rootlink"/>

	Including standard stylesheets/js/whatever:
	<head>...<n:invisible n:render="commonhead"/>...</head>

	Rendering the sidebar (with a meta-carrying thing in data):

	<body n:data="something meta carrying" n:render="withsidebar">
	"""
	def _doRenderMeta(self, ctx, flattenerFunc, raiseOnFail=False, all=False):
		metaKey = ctx.tag.children[0]
		metaVal = self.service.getMeta(metaKey, raiseOnFail=raiseOnFail, all=all)
		if metaVal:
			if all:
				return ctx.tag.clear()[[T.li[flattenerFunc(v)] for v in metaVal]]
			else:
				return ctx.tag.clear()[flattenerFunc(metaVal)]
		else:
			return T.comment["Meta item %s not given."%metaKey]

	def render_meta(self, ctx, data):
		return self._doRenderMeta(ctx, str)
	
	def render_metahtml(self, ctx, data):
		return self._doRenderMeta(ctx, lambda c: T.xml(c.asHtml()))

	def render_metahtmlAll(self, ctx, data):
		return self._doRenderMeta(ctx, lambda c: T.xml(c.asHtml()), all=True)

	def render_rootlink(self, ctx, data):
		tag = ctx.tag
		def munge(key):
			if tag.attributes.has_key(key):
			 tag.attributes[key] = config.get("web", "nevowRoot")+tag.attributes[key]
		munge("src")
		munge("href")
		return tag

	def render_ifdata(self, ctx, data):
		if data:
			return ctx.tag
		else:
			return ""

	def render_commonhead(self, ctx, data):
		return ctx.tag[
			T.link(rel="stylesheet", href=makeSitePath("/formal.css"), 
				type="text/css"),
			T.link(rel="stylesheet", href=makeSitePath("/static/css/gavo_dc.css"), 
				type="text/css"),
			T.script(type='text/javascript', src=makeSitePath('/js/formal.js')),
			T.script(src=makeSitePath("/static/js/gavo.js"), 
				type="text/javascript"),
		]

	def render_explodableMeta(self, ctx, data):
		metaKey = ctx.tag.children[0]
		title = ctx.tag.attributes.get("title", metaKey.capitalize())
		try:
			return T.div(class_="explodable")[
				T.h4(class_="exploHead")[
					title,
					" ",
					T.a(onclick="toggleCollapsedMeta(this)", 
						class_="foldbutton")[">>"],
				],
				self._doRenderMeta(ctx, lambda c: T.xml(c.asHtml()), raiseOnFail=True)]
		except config.MetaError:
			return ""
			
	def render_withsidebar(self, ctx, data):
		oldChildren = ctx.tag.children
		ctx.tag.children = []
		return ctx.tag[
			T.div(id="sidebar")[
				T.div(class_="sidebaritem")[
					T.a(href="/", render=T.directive("rootlink"))[
						T.img(src="/static/img/logo_medium.png", class_="silentlink",
							render=T.directive("rootlink"), alt="[Gavo logo]")],
				],
				T.a(href="#body", class_="invisible")["Skip Header"],
				T.div(class_="sidebaritem")[
					T.a(href="/static/help.shtml")[
						"Help"],
				],
				T.div(render=T.directive("ifdata"), class_="sidebaritem",
					data=self.service.getMeta("_related"))[
					T.h3["Related"],
					T.ul(class_="sidebarEnum",
						render=T.directive("metahtmlAll"))["_related"],
				],
				T.div(class_="sidebaritem")[
					T.h3["Metadata"],
					T.invisible(
						render=T.directive("explodableMeta"))["description"],
					T.invisible(
						render=T.directive("explodableMeta"))["creator"],
					T.invisible(title="Created",
						render=T.directive("explodableMeta"))["creationDate"],
					T.invisible(title="Data updated",
						render=T.directive("explodableMeta"))["dateUpdated"],
					T.invisible(
						render=T.directive("explodableMeta"))["copyright"],
					T.invisible(
						render=T.directive("explodableMeta"))["reference"],
					T.invisible(title="Reference URL",
						render=T.directive("explodableMeta"))["referenceURL"],
				],
			],
			T.div(id="body")[
				T.a(name="body"),
				oldChildren
			],
		]
				

class QueryMeta(dict):
	"""is a class keeping all data *about* a query, e.g., the
	requested output format.

	It is constructed with either a nevow context (we'll look
	at the args of the embedded request) or a plain dictionary.  Note,
	however, that the values obtained from the net must be in *sequences*
	(of course, they're usually length 1).  This is what IRequest delivers,
	and there's no sense in special-casing this, even more since having
	a sequence might come in handy at some point (e.g., for sort keys).
	If you pass an empty dict, some sane defaults will be used.  You
	can get that "empty" query meta as common.emptyQueryMeta

	Not all services need to interpret all meta items; e.g., things writing
	fits files or VOTables only will ignore _FORMAT, and the dboptions
	won't make sense for many applications.

	If you're using nevow formal, you should set the formal_data item
	to the dictionary created by formal.  This will let people use
	the parsed parameters in templates.
	"""

	# a list of keys handled by query meta to be ignored in parameter
	# lists because they are used internally.  This covers everything 
	# QueryMeta interprets, but also keys by introduced by certain gwidgets
	# and the nevow infrastructure
	metaKeys = set(["_DBOPTIONS", "_FILTER", "_OUTPUT", "_charset_", "_ADDFIELD",
		"__nevow_form__", "_FORMAT", "_VERB", "_TDENC", "formal_data"])

	def __init__(self, ctxArgs):
		try:
			ctxArgs = inevow.IRequest(ctxArgs).args
		except TypeError:
			pass
		self.ctxArgs = ctxArgs
		self["formal_data"] = {}
		self._fillOutput(ctxArgs)
		self._fillOutputFilter(ctxArgs)
		self._fillDbOptions(ctxArgs)
	
	def _fillOutput(self, ctxArgs):
		"""interprets values left by the OutputFormat widget.
		"""
		self["format"] = ctxArgs.get("_FORMAT", ["HTML"])[0]
		try:
# prefer fine-grained "verbosity" over _VERB or VERB
			if ctxArgs.has_key("verbosity"):
				self["verbosity"] = int(ctxArgs["verbosity"][0])
			elif ctxArgs.has_key("_VERB"):
				self["verbosity"] = int(ctxArgs["_VERB"][0])*10
			elif ctxArgs.has_key("VERB"):
				self["verbosity"] = int(ctxArgs["VERB"][0])*10
			else:
				self.verbosity = 20
		except ValueError:
			self["verbosity"] = 20
		try:
			self["tdEnc"] = record.parseBooleanLiteral(
				ctxArgs.get("_TDENC", ["False"])[0])
		except gavo.Error:
			self["tdEnc"] = False
		self["additionalFields"] = ctxArgs.get("_ADDITEM", [])
	
	def _fillOutputFilter(self, ctxArgs):
		self["outputFilter"] = ctxArgs.get("_FILTER", ["default"])[0] or "default"

	def _fillDbOptions(self, ctxArgs):
		try:
			self["dbLimit"] = ctxArgs.get("_DBOPTIONS_LIMIT", [None])[0]
			if self["dbLimit"]:
				self["dbLimit"] = int(self["dbLimit"])
		except ValueError:
			self["dbLimit"] = 100
		self["dbSortKey"] = ctxArgs.get("_DBOPTIONS_ORDER", [None])[0]

	def overrideDbOptions(self, sortKey=Undefined, limit=Undefined):
		if sortKey is not Undefined:
			self["dbSortKey"] = sortKey
		if limit is not Undefined:
			self["dbLimit"] = int(limit)

	def asSql(self):
		"""returns the dbLimit and dbSortKey values as an SQL fragment.
		"""
		frag, pars = [], {}
		sortKey = self["dbSortKey"]
		dbLimit = self["dbLimit"]
		if sortKey:
			# Ok, we need to do some emergency securing here.  There should be
			# pre-validation that we're actually seeing a column key, but
			# just in case let's make sure we're seeing an SQL identifier.
			# (We can't rely on dbapi's escaping since we're not talking values here)
			sortKey = re.sub("[^A-Za-z_]+", "", sortKey)
			frag.append("ORDER BY %s"%sortKey)
		if dbLimit:
			frag.append("LIMIT %(_matchLimit)s")
			pars["_matchLimit"] = int(dbLimit)+1
		return " ".join(frag), pars
	

emptyQueryMeta = QueryMeta({})


class CoreResult(object):
	"""is a nevow.IContainer that has the result and also makes the input
	dataset accessible.
	"""
	implements(inevow.IContainer)

	def __init__(self, resultData, inputData, queryMeta, service=None):
		self.original = resultData
		self.queryPars = queryMeta.get("formal_data", {})
		self.inputData = inputData
		self.queryMeta = queryMeta
		self.service = service
		for n in dir(self.original):
			if not n.startswith("_"):
				setattr(self, n, getattr(self.original, n))

	def data_resultmeta(self, ctx):
		result = self.original.getPrimaryTable()
		resultmeta = {
			"itemsMatched": len(result.rows),
			"filterUsed": self.queryMeta.get("outputFilter", ""),
		}
		return resultmeta

	def data_querypars(self, ctx=None):
		return dict((k, str(v)) for k, v in self.queryPars.iteritems()
			if not k in QueryMeta.metaKeys and v and v!=[None])

	suppressedParNames = set(["submit"])
		
	def data_queryseq(self, ctx=None):
		if self.service:
			fieldDict = dict((f.get_dest(), f) 
				for f in self.service.getInputFields())
		else:
			fieldDict = {}

		def getTitle(key):
			title = None
			if key in fieldDict:
				title = fieldDict[key].get_tablehead()
			return title or key
		
		s = [(getTitle(k), v) for k, v in self.data_querypars().iteritems()
			if k not in self.suppressedParNames and not k.startswith("_")]
		s.sort()
		return s

	def data_inputRec(self, ctx=None):
		return self.inputData.getDocRec()

	def data_table(self, ctx=None):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class CustomTemplateMixin(object):
	"""is a mixin providing for customized templates.

	This works by making docFactory a property first checking if the instance has
	a customTemplate attribute evaluating to true.  If it has, its content is
	used as a resdir-relative path to a nevow XML template, if not, the
	defaultDocFactory attribute of the instance is used.
	"""
	customTemplate = None

	def getDocFactory(self):
		if self.customTemplate:
			res = loaders.xmlfile(self.customTemplate)
		else:
			res = self.defaultDocFactory
		return res
	
	docFactory = property(getDocFactory)


def makeSitePath(uri):
# XXX TODO: unify with GavoRenderMixin.render_rootlink 
	"""adapts uri for use in an off-root environment.

	uri itself needs to be server-absolute (i.e., start with a slash).
	"""
	assert uri[0]=="/"
	return config.get("web", "nevowRoot")+uri
