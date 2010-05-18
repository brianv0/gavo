"""
Infrastructure pages.
"""

import os

from nevow import inevow
from nevow import rend
from nevow import static
from nevow import url
import pkg_resources

from gavo import base
from gavo import svcs
from gavo.web import common
from gavo.web import grend


# monkeypatch nevow static's mime types
static.File.contentTypes[".ascii"] = "application/octet-stream"
static.File.contentTypes[".vot"] = "application/x-votable+xml"
static.File.contentTypes[".rd"] = "application/x-gavo-descriptor+xml"


class ReloadPage(grend.GavoRenderMixin, rend.Page):

	modsToReload = []

	def __init__(self, ctx):
		rend.Page.__init__(self)
		self.modulesReloaded = []
	
	def data_reloadedModules(self, ctx, data):
		return self.modulesReloaded

	def renderHTTP(self, ctx):
		return common.runAuthenticated(ctx, "admin", self._reload, ctx)

	def _reloadModules(self):
		for modPath in self.modsToReload:
			parts = modPath.split(".")
			exec "from %s import %s;reload(%s)"%(".".join(parts[:-1]), parts[-1],
				parts[-1])
			self.modulesReloaded.append(modPath)

	def _reload(self, ctx):
		base.caches.clearCaches()
		self._reloadModules()
		return self._renderHTTP(ctx)
	
	docFactory = svcs.loadSystemTemplate("reloaded.html")


class LoginPage(rend.Page, grend.GavoRenderMixin):
	"""is a page that logs people in or out.

	You should usually give a nextURL parameter in the context, the page
	the user is returned to afte login.

	If the user is already authenticated, this will do a logout (by
	sending a 403).
	"""
	def __init__(self, ctx):
		rend.Page.__init__(self)
		self.request = inevow.IRequest(ctx)
		self.nextURL = self.request.args.get("nextURL", ["/"])[0]

	def render_nextURL(self, ctx, data):
		return ctx.tag(href=self.nextURL)

	def render_iflogged(self, ctx, data):
		if self.request.getUser():
			return ctx.tag
		return ""
	
	def render_ifnotlogged(self, ctx, data):
		if not self.request.getUser():
			return ctx.tag
		return ""

	def data_loggedUser(self, ctx, data):
		return self.request.getUser()

	def doAuth(self, ctx):
		self.request.setResponseCode(401)
		self.request.setHeader('WWW-Authenticate', 'Basic realm="Gavo"')
		return rend.Page.renderHTTP(self, ctx)

	def renderHTTP(self, ctx):
		relogging = self.request.args.get("relog", None)
		if self.request.getUser():  # user is logged in...
			if relogging: # ...and wants to log out: show login dialog...
				return self.doAuth(ctx)
			else:   # ...and has just logged in: forward to destination
				return url.URL.fromContext(ctx).click(self.nextURL)
		else:  # user is not logged in
			if relogging:  #...but was and has just logged out: forward to dest
				return url.URL.fromContext(ctx).click(self.nextURL)
			else: # ... and want to log in.
				return self.doAuth(ctx)

	docFactory = svcs.loadSystemTemplate("loginout.html")


def _replaceConfigStrings(srcPath, registry):
	src = open(srcPath).read().decode("utf-8")
	src = src.replace("__site_path__", base.getConfig("web", "nevowRoot"))
	src = src.replace("__site_url__", os.path.join(
		base.getConfig("web", "serverURL")+base.getConfig("web", "nevowRoot")))
	return src.encode("utf-8")


class StaticServer(static.File):
	"""is a server for various static files.

	There's only one hack in here: We register a processor for .shtml
	files.  In them, certain strings are replaced with *site-global*
	values.  That's a nasty hack that should be replaced with ordinary,
	run-of-the-mill macros (or something like this).

	And this whole thing should be replaced with a static renderer on
	a system service.
	"""
	def __init__(self, *args, **kwargs):
		if not args:
			static.File.__init__(self, os.path.join(base.getConfig("webDir"), 
				"nv_static"))
		else:
			static.File.__init__(self, *args, **kwargs)

	processors = {
		".shtml": _replaceConfigStrings,
	}


class BuiltinServer(StaticServer):
	"""is a server for the built-in resources.

	This works via setuptool's pkg_config; the built-in resources are in
	gavo/resources in SVN.

	This is pain.  see StaticServer
	"""
	builtinRoot = pkg_resources.resource_filename('gavo', "resources/web")
	def __init__(self, *args, **kwargs):
		if not args:
			static.File.__init__(self, self.builtinRoot)
		else:
			static.File.__init__(self, *args, **kwargs)
