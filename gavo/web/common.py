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
from gavo import meta
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


class HtmlMetaBuilder(meta.MetaBuilder):
	def __init__(self):
		meta.MetaBuilder.__init__(self)
		self.resultTree, self.currentAtom = [[]], None

	def startKey(self, atom):
		self.resultTree.append([])
		
	def enterValue(self, value):
		val = value.getContent("html")
		if val:
			self.resultTree[-1].append(T.xml(val))

	def _isCompound(self, childItem):
		"""should return true some day for compound meta items that should
		be grouped in some way.
		"""
		return False

	def endKey(self, atom):
		children = self.resultTree.pop()
		if len(children)>1:
			childElements = []
			for c in children:
				if self._isCompound(c)>1:
					class_ = "compoundMetaItem"
				else:
					class_ = "metaItem"
				childElements.append(T.li(class_=class_)[c])
			self.resultTree[-1].append(T.ul(class_="metaEnum")[childElements])
		elif len(children)==1:
			self.resultTree[-1].append(children[0])
	
	def getResult(self):
		return self.resultTree[0]

	def clear(self):
		self.resultTree = [[]]


_htmlMetaBuilder = HtmlMetaBuilder()


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
	def _doRenderMeta(self, ctx, raiseOnFail=False, plain=False):
		metaKey = ctx.tag.children[0]
		try:
			if plain:
				ctx.tag.clear()
				return ctx.tag[self.service.getMeta(metaKey, raiseOnFail=True
					).getContent("text")]
			else:
				_htmlMetaBuilder.clear()
				ctx.tag.clear()
				return ctx.tag[T.xml(self.service.buildRepr(metaKey, _htmlMetaBuilder,
					raiseOnFail=True))]
		except gavo.NoMetaKey:
			if raiseOnFail:
				raise
			return T.comment["Meta item %s not given."%metaKey]

	def render_meta(self, ctx, data):
		return self._doRenderMeta(ctx, plain=True)
	
	def render_metahtml(self, ctx, data):
		return self._doRenderMeta(ctx)
		

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
			T.link(rel="stylesheet", href=makeSitePath("/builtin/css/gavo_dc.css"), 
				type="text/css"),
			T.script(type='text/javascript', src=makeSitePath('/js/formal.js')),
			T.script(src=makeSitePath("/builtin/js/gavo.js"), 
				type="text/javascript"),
		]

	def render_explodableMeta(self, ctx, data):
		metaKey = ctx.tag.children[0]
		title = ctx.tag.attributes.get("title", metaKey.capitalize())
		try:
			return T.div(class_="explodable")[
				T.h4(class_="exploHead")[
					T.a(onclick="toggleCollapsedMeta(this)", 
						class_="foldbutton")[title+" >>"],
				],
				self._doRenderMeta(ctx, raiseOnFail=True)]
		except gavo.MetaError:
			return ""
			
	def render_withsidebar(self, ctx, data):
		oldChildren = ctx.tag.children
		ctx.tag.children = []
		return ctx.tag[
			T.div(id="sidebar")[
				T.div(class_="sidebaritem")[
					T.a(href="/", render=T.directive("rootlink"))[
						T.img(src="/builtin/img/logo_medium.png", class_="silentlink",
							render=T.directive("rootlink"), alt="[Gavo logo]")],
				],
				T.a(href="#body", class_="invisible")["Skip Header"],
				T.div(class_="sidebaritem")[
					T.a(href="/builtin/help.shtml")[
						"Help"],
				],
				T.div(render=T.directive("ifdata"), class_="sidebaritem",
					data=self.service.getMeta("_related"))[
					T.h3["Related"],
					T.invisible(render=T.directive("metahtml"))["_related"],
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
				T.div(class_="sidebaritem", style="font-size: 62%; padding-top:5px;"
						" border-top: 1px solid grey; margin-top:40px;")[
					T.p["Please report errors and problems to ",
						T.a(href="mailto:gavo.ari.uni-heidelberg.de")["GAVO staff"],
						".  Thanks."]]
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
# Hack: malformed _VERBs result in None verbosity, which is taken to
# mean about "use fields of HTML".  Absent _VERB or VERB, on the other
# hand, means VERB=2, i.e., a sane default
			if ctxArgs.has_key("verbosity"):
				self["verbosity"] = int(ctxArgs["verbosity"][0])
			elif ctxArgs.has_key("_VERB"):
				self["verbosity"] = int(ctxArgs["_VERB"][0])*10
			elif ctxArgs.has_key("VERB"):
				self["verbosity"] = int(ctxArgs["VERB"][0])*10
			else:
				self["verbosity"] = 20
		except ValueError:
			self["verbosity"] = "HTML"
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
