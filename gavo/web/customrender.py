"""
User-defined renderers.
"""

from gavo import svcs
from gavo.web import grend


class CustomRenderer(grend.ServiceBasedPage):
	"""A wrapper for user-defined renderers.

	See `Writing Custom Cores`_ for details.
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
		return self.realPage.locateChild(ctx, segments)
