"""
Renderer not reacting too strongly on user input.

There's StaticRender just delivering certain files from within a service,
and there's FixedPageRenderer that just formats a defined template.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os

from nevow import flat
from nevow import inevow
from nevow import static
from nevow import tags as T

from gavo import base
from gavo import svcs
from gavo.web import grend
from gavo.web import ifpages

__docformat__ = "restructuredtext en"

class StaticRenderer(grend.ServiceBasedPage):
	"""A renderer that just hands through files.

	The standard operation here is to set a staticData property pointing
	to a resdir-relative directory used to serve files for.  Indices
	for directories are created.

	You can define a root resource by giving an indexFile property on
	the service.  Note in particular that you can use an index file
	with an extension of shtml.  This lets you use nevow templates, but
	since metadata will be taken from the global context, that's
	probably not terribly useful.  You are probably looking for the fixed
	renderer if you find yourself needing this.
	"""
	name = "static"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
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
		"""The resource itself is the indexFile or the directory listing.
		"""
		# make sure there always is a slash at the end of any URL
		# that points to any sort of index file (TODO: parse the URL?)
		request = inevow.IRequest(ctx)
		basePath = request.uri.split("?")[0]
		if basePath.endswith("static/"):
			if self.indexFile:
				return ifpages.StaticFile(self.indexFile, self.rd)
			else:
				return static.File(self.staticPath).directoryListing()

		elif basePath.endswith("static"):
			raise svcs.WebRedirect(request.uri+"/")

		else:
			raise svcs.WebRedirect(request.uri+"/static/")

	def locateChild(self, ctx, segments):
		if len(segments)==1 and not segments[0]:
			return self, ()

		if self.staticPath is None:
			raise svcs.ForbiddenURI("No static data on this service") 

		relPath = "/".join(segments)
		destName = os.path.join(self.staticPath, relPath)

		if os.path.isdir(destName):
			if not destName.endswith("/"):
				raise svcs.WebRedirect(inevow.IRequest(ctx).uri+"/")
			return static.File(destName).directoryListing(), ()

		elif os.path.isfile(destName):
			return ifpages.StaticFile(destName, self.rd), ()

		else:
			raise svcs.UnknownURI("No %s available here."%relPath)
		

class FixedPageRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A renderer that renders a single template.

	Use something like ``<template key="fixed">res/ft.html</template>``
	in the enclosing service to tell the fixed renderer where to get
	this template from.

	In the template, you can fetch parameters from the URL using 
	something like ``<n:invisible n:data="parameter FOO" n:render="string"/>``;
	you can also define new render and data functions on the
	service using customRF and customDF.

	This is, in particular, used for the data center's root page.

	The fixed renderer is intended for non- or slowly changing content.
	It is annotated as cachable, which means that DaCHS will in general
	only render it once and then cache it.  If the render functions
	change independently of the RD, use the volatile renderer.

	Built-in services for such browser apps should go through the //run 
	RD.
	"""
	name = "fixed"

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
		self.customTemplate = None
		try:
			self.customTemplate = self.service.getTemplate("fixed")
		except KeyError:
			raise base.ui.logOldExc(
				svcs.UnknownURI("fixed renderer needs a 'fixed' template"))

	def render_voplotArea(self, ctx, data):
		"""fills out the variable attributes of a voplot object with
		stuff from config.
		"""
		# Incredibly, firefox about 2.x requires archive before code.
		# so, we need to hack this.
		baseURL = base.makeAbsoluteURL("/static/voplot")
		res = flat.flatten(ctx.tag, ctx)
		return T.xml(res.replace(
			"<object", '<object archive="%s/voplot.jar"'%baseURL))

	def data_parameter(self, parName):
		"""lets you insert an URL parameter into the template.

		Non-existing parameters are returned as an empty string.
		"""
		def getParameter(ctx, data):
			return inevow.IRequest(ctx).args.get(parName, [""])[0]
		return getParameter

	@classmethod
	def isCacheable(cls, segments, request):
		return True
	
	@classmethod
	def isBrowseable(self, service):
		return True


class VolatilePageRenderer(FixedPageRenderer):
	"""A renderer rendering a single template with fast-changing results.

	This is like the fixed renderer, except that the results are not cached.
	"""
	name = "volatile"

	@classmethod
	def isCacheable(cls, segments, request):
		return False

