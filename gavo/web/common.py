"""
Common code for the nevow based interface.
"""

import os

import pkg_resources

from nevow import tags as T, entities as E
from nevow import loaders
from nevow import inevow
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http
from twisted.internet import defer


from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.protocols import creds


def getfirst(ctx, key, default):
	"""returns the first value of key in the nevow context ctx.
	"""
	return utils.getfirst(inevow.IRequest(ctx).args, key, default)


class HTMLMetaBuilder(meta.MetaBuilder):
	def __init__(self, macroPackage=None):
		meta.MetaBuilder.__init__(self)
		self.resultTree, self.currentAtom = [[]], None
		self.macroPackage = macroPackage

	def startKey(self, atom):
		self.resultTree.append([])
		
	def enterValue(self, value):
		val = value.getContent("html", self.macroPackage)
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


class CustomTemplateMixin(object):
	"""is a mixin providing for customized templates.

	This works by making docFactory a property first checking if
	the instance has a customTemplate attribute evaluating to true.
	If it has and it is referring to a string, its content is used
	as an absolute path to a nevow XML template.  If it has and
	it is not a string, it will be used as a template directly
	(it's already "loaded"), else defaultDocFactory attribute of
	the instance is used.
	"""
	customTemplate = None

	def getDocFactory(self):
		if not self.customTemplate:
			return self.defaultDocFactory
		elif isinstance(self.customTemplate, basestring):
			if not os.path.exists(self.customTemplate):
				return self.defaultDocFactory
			return loaders.xmlfile(self.customTemplate)
		else:
			return self.customTemplate
	
	docFactory = property(getDocFactory)


def runAuthenticated(ctx, reqGroup, fun, *args):
	"""returns the value of fun(*args) if the logged in user is in reqGroup,
	requests authentication otherwise.
	"""
	request = inevow.IRequest(ctx)
	if creds.hasCredentials(request.getUser(), request.getPassword(), reqGroup):
		return fun(*args)
	else:
		request.setHeader('WWW-Authenticate', 'Basic realm="Gavo"')
		request.setResponseCode(http.UNAUTHORIZED)
		return "Authorization required"


class doctypedStan(loaders.stan):
	"""is the stan loader with a doctype and a namespace added.
	"""

	DOCTYPE = T.xml('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
		' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n')

	def __init__(self, rootEl, pattern=None):
		super(doctypedStan, self).__init__(T.invisible[self.DOCTYPE, 
			rootEl(xmlns="http://www.w3.org/1999/xhtml")], pattern)


class CommonRenderers(object):
	"""A base for renderer mixins within the DC.

	Including standard stylesheets/js/whatever:
	<head>...<n:invisible n:render="commonhead"/>...</head>
	"""

	def render_commonhead(self, ctx, data):
		return ctx.tag[
			T.link(rel="stylesheet", href=base.makeSitePath("/formal.css"), 
				type="text/css"),
			T.link(rel="stylesheet", href=base.makeSitePath(
				"/builtin/css/gavo_dc.css"), type="text/css"),
			T.script(src=base.getConfig("web", "mochiURL"),
				type="text/javascript"),
			T.script(type='text/javascript', src=base.makeSitePath(
				'/js/formal.js')),
			T.script(src=base.makeSitePath("/builtin/js/gavo.js"), 
				type="text/javascript"),
			T.meta(**{"http-equiv": "Content-type", 
				"content": "text/html;charset=UTF-8"}),
		]


def bailIfNotModified(request, changeStamp):
	"""raises a NotChanged exception if request contains an if-modified-since
	header, changeDate is non-None and earlier than i-m-s.

	ChangeStamp is a unix timestamp (in GMT) and may be None (in which
	case this function is a no-op.
	"""
	if (not changeStamp
			or "if-modified-since" not in request.received_headers
			or request.method!="GET"
			or request.isSponsor):
		return
	try:
		thresh = utils.parseRFC2616Date(
			request.received_headers["if-modified-since"])
	except:  # never fail on messy input here
		thresh = datetime.datetime(1990, 1, 1)
	if thresh>=changeStamp:
		raise svcs.NotModified()
