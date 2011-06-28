"""
Renderer not reacting too strongly on user input.

There's StaticRender just delivering certain files from within a service,
and there's FixedPageRenderer that just formats a defined template.
"""

import os

from nevow import inevow
from nevow import static

from gavo import base
from gavo import svcs
from gavo.web import grend
from gavo.web import formrender


class StaticRenderer(formrender.FormMixin, grend.ServiceBasedPage):
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


class FixedPageRenderer(grend.CustomTemplateMixin, grend.ServiceBasedPage):
	"""A renderer that renders a single template.

	The file is given in the service's fixed template.

	You can fetch parameters from the URL using the parameter data function.

	See the specview.html template as an example.
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

