"""
User-defined renderers.
"""

from gavo import svcs
from gavo.web import grend


class CustomRenderer(grend.ServiceBasedPage):
	"""A renderer defined in a python module.
	
	To define a custom renderer write a python module and define a
	class MainPage inheriting from gavo.web.ServiceBasedRenderer.

	This class basically is a nevow resource, i.e., you can define
	docFactroy, locateChild, renderHTTP, and so on.

	To use it, you have to define a service with the resdir-relative path
	to the module in the customPage attribute and probably a nullCore.  You
	also have to allow the custom renderer (but you may have other renderers,
	e.g., static).

	There should really be a bit more docs on this, but alas, there's
	none as yet.
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
