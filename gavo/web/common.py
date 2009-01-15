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
from gavo.base import meta
from gavo.protocols import creds


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


def loadSystemTemplate(path):
	"""returns a nevow template for system pages from path.

	path is interpreted as relative to gavo_root/web/templates (first)
	and package internal (last).  If no template is found, None is
	returned (this harmonizes with the fallback in CustomTemplateMixin).
	"""
	try:
		userPath = os.path.join(base.getConfig("rootDir"), "web/templates", path)
		if os.path.exists(userPath):
			return loaders.xmlfile(userPath)
		else:
			return loaders.xmlfile(pkg_resources.resource_filename('gavo',
				"resources/templates/"+path))
	except IOError:
		pass


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
		' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">')

	def __init__(self, rootEl, pattern=None):
		super(doctypedStan, self).__init__(T.invisible[self.DOCTYPE, 
			rootEl(xmlns="http://www.w3.org/1999/xhtml")], pattern)
