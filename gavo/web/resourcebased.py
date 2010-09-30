"""
The form renderer and related code.
"""

# XXX TODO: break this up.

import cStringIO
import imp
import mutex
import new
import os
import sys
import time
import traceback
import urllib
import urlparse


from nevow import context
from nevow import flat
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from nevow import url
from nevow import util

from twisted.internet import defer
from twisted.internet import threads

from zope.interface import implements

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo.imp import formal
from gavo.imp.formal import form
from gavo.base import typesystems
from gavo.web import common
from gavo.web import grend
from gavo.web import producttar
from gavo.web import serviceresults
from gavo.web import streaming

from gavo.svcs import Error, UnknownURI, ForbiddenURI


class StaticRenderer(grend.FormMixin, grend.ServiceBasedPage):
	"""is a renderer that just hands through files.

	The standard operation here is to set a staticData property pointing
	to a resdir-relative directory used to serve files for.  Indices
	for directories are created.

	You can define a root resource by giving an indexFile property on
	the service.
	"""
	name = "static"

	def __init__(self, ctx, service):
		try:
			self.indexFile = os.path.join(service.rd.resdir, 
				service.getProperty("indexFile"))
		except KeyError:
			self.indexFile = None
		try:
			self.staticPath = os.path.join(service.rd.resdir, 
				service.getProperty("staticData"))
		except KeyError:
			self.staticPath = None

	@classmethod
	def isBrowseable(self, service):
		return service.getProperty("indexFile", None) 

	def renderHTTP(self, ctx):
		if inevow.ICurrentSegments(ctx)[-1]!='':
			# force a trailing slash on the "index"
			request = inevow.IRequest(ctx)
			request.redirect(request.URLPath().child(''))
			return ''
		if self.indexFile:
			return static.File(self.indexFile)
		else:
			raise svcs.UnknownURI("No matching resource")
	
	def locateChild(self, ctx, segments):
		if segments==('',) and self.indexFile:
			return self, ()
		elif self.staticPath is None:
			raise svcs.ForbiddenURI("No static data on this service") 
		else:
			if segments[-1]=="static": # no trailing slash given
				segments = ()            # -- swallow the segment
			return static.File(self.staticPath), segments

svcs.registerRenderer(StaticRenderer)


class FixedPageRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A renderer that always returns a single file.

	The file is given in the service's fixed template.
	"""
	name = "fixed"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
		self.customTemplate = None
		try:
			self.customTemplate = self.service.templates["fixed"]
		except KeyError:
			raise base.ui.logOldExc(
				svcs.UnknownURI("fixed renderer needs a 'fixed' template"))

	@classmethod
	def isCacheable(cls, segments, request):
		return True
	
	@classmethod
	def isBrowseable(self, service):
		return True

svcs.registerRenderer(FixedPageRenderer)


class TextRenderer(grend.ServiceBasedPage):
	"""is a renderer that runs the service, expects back a string and
	displays that as text/plain.

	I don't think this is useful, but it's convenient for tests.
	"""
	name = "text"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
	
	def renderHTTP(self, ctx):
		d = self.runServiceWithContext(inevow.IRequest(ctx).args, ctx
			).addCallback(self._runService, queryMeta, ctx
			).addCallback(self._doRender, ctx)
		return d

	def _doRender(self, coreOutput, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/plain")
		request.write(str(coreOutput.original))
		return request.finishRequest(False) or ""
	

class CustomRenderer(grend.ServiceBasedPage):
	"""is a wrapper for user-defined renderers.

	The services defining this must have a customPage field. 
	It must be a tuple (page, (name, file, pathname, descr)), where page is
	a nevow resource constructible like a renderer (i.e., receiving a
	context and a service).  They will, in general, have locateChild
	overridden.

	(name, file, pathname, descr) is the result of load_module and is used
	in the special child "_reload" that will cause a reload of the
	underlying module and an assignment of its MainPage to realPage
	(like importparser does on the first import).
	"""
	name = "custom"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
		if not self.service.customPage:
			raise svcs.UnknownURI("No custom page defined for this service.")
		pageClass, self.reloadInfo = service.customPageCode
		self.realPage = pageClass(ctx, service)

	@classmethod
	def isBrowseable(self, service):
		return True  # this may be somewhat broad.

	def _reload(self, ctx):
		mod = imp.load_module(*self.reloadInfo)
		pageClass = mod.MainPage
		self.service.customPageCode = (pageClass, self.reloadInfo)
		return url.here.curdir()

	def renderHTTP(self, ctx):
		return self.realPage.renderHTTP(ctx)
	
	def locateChild(self, ctx, segments):
		if segments and segments[0]=="_reload":
			return common.runAuthenticated(ctx, "", self._reload, ctx), ()
		return self.realPage.locateChild(ctx, segments)

svcs.registerRenderer(CustomRenderer)
