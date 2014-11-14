"""
Renderer not reacting too strongly on user input.

There's StaticRender just delivering certain files from within a service,
and there's FixedPageRenderer that just formats a defined template.
"""

#c Copyright 2008-2014, the GAVO project
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

__docformat__ = "restructuredtext en"

class StaticRenderer(grend.ServiceBasedPage):
	"""A renderer that just hands through files.

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
		"""The resource itself is the indexFile or the directory listing.
		"""
		# make sure there always is a slash at the end of any URL
		# that points to any sort of index file (TODO: parse the URL?)
		request = inevow.IRequest(ctx)
		basePath = request.uri.split("?")[0]
		if basePath.endswith("static/"):
			if self.indexFile:
				return static.File(self.indexFile)
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

		# leave the rest to static.File, except there's a bug in some
		# versions of is so we check of existence ourselves.
		relPath = "/".join(segments)
		if not os.path.exists(os.path.join(self.staticPath, relPath)):
			raise svcs.UnknownURI("No %s available here."%relPath)
		return static.File(os.path.join(self.staticPath, segments[0])
			), segments[1:]
		


class FixedPageRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A renderer that renders a single template.

	Use something like ``<template key="fixed">res/ft.html</template>``
	in the enclosing service to tell the fixed renderer where to get
	this template from.

	In the template, you can fetch parameters from the URL using 
	something like ``<n:invisible n:data="parameter FOO" n:render="string"/>``;
	you can also define new render and data functions on the
	service using customRF and customDF.

	This is mainly for applet/browser app support; See the
	specview.html or voplot.html templates as an example.  This is
	the place to add further render or data function for programs
	like those.

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
