"""
The dispatcher for the new nevow-based web interface.
"""


import cStringIO
import glob
import math
import new
import os
import pkg_resources
import re
import traceback
import urllib
import urlparse

import formal

from twisted.internet import defer
from twisted.python import components
# we put some calculations into threads.
from twisted.python import threadable
threadable.init()

from nevow import appserver
from nevow import context
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E
from nevow import url

from zope.interface import implements

import gavo
from gavo import config
from gavo import logger
from gavo import resourcecache
from gavo import utils
# need importparser to register its resourcecache
from gavo.parsing import importparser
from gavo.web import common
from gavo.web import creds
from gavo.web import jpegrenderer
from gavo.web import metarender
from gavo.web import product
from gavo.web import resourcebased
# need servicelist to register its resourcecache
from gavo.web import servicelist
# need scs to register its CondDescs
from gavo.web import scs
from gavo.web import soaprender
from gavo.web import uploadservice
from gavo.web import vodal
from gavo.web import weberrors

from gavo.web.common import Error, UnknownURI, ForbiddenURI, WebRedirect


class ReloadPage(common.GavoRenderMixin, rend.Page):

	modsToReload = ["gavo.web.dispatcher"]

	def __init__(self, ctx, *args, **kwargs):
		super(ReloadPage, self).__init__()
		self.modulesReloaded = []
	
	def data_reloadedModules(self, ctx, data):
		return self.modulesReloaded

	def renderHTTP(self, ctx):
		return creds.runAuthenticated(ctx, "admin", self._reload, ctx)

	def _reloadModules(self):
		for modPath in self.modsToReload:
			parts = modPath.split(".")
			exec "from %s import %s;reload(%s)"%(".".join(parts[:-1]), parts[-1],
				parts[-1])
			self.modulesReloaded.append(modPath)

	def _reload(self, ctx):
		resourcecache.clearCaches()
		self._reloadModules()
		return self._renderHTTP(ctx)
	
	docFactory = loaders.xmlstr("""<html xmlns:n='http://nevow.com/ns/nevow/0.1'>
    <head><title>Caches cleared</title>
    </head>
    <body><h1>Caches cleared</h1>
		<p>The caches were cleared successfully.</p>
		<p>Modules reloaded: 
			<span n:render="sequence" n:data="reloadedModules">
				<span n:pattern="item"><n:invisible n:render="data"/>, </span>
			</span>
		</p>
		<p>You can:</p>
		<ul>
		<li><a href="/reload" n:render="rootlink">Reload again</a></li>
		<li>Go to <a href="/" n:render="rootlink">Main Page</a></li>
		<li><a href="/__system__/services/services/overview/form" 
			n:render="rootlink">Inspect services</a></li>
		</ul>
    </body></html>
    """)


class LoginPage(rend.Page):
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


	docFactory = common.doctypedStan(
		T.html[T.head[T.title["GAVO: Credentials Info"]],
			T.body[
				T.h1["Credentials Info"],
				T.p(render=T.directive("iflogged"))["You are currently logged in"
					" as ", 
					T.span(class_="loggedUser", render=T.directive("data"),
						data=T.directive("loggedUser")),
					"."],
				T.p(render=T.directive("ifnotlogged"))["You are currently logged out"],
				T.p["Go to ",
					T.a(render=T.directive("nextURL"))["the last page"],
					" or ",
					T.a(href=config.get("web", "nevowRoot"))["DC home"],
					"."]]])
	

def _replaceConfigStrings(srcPath, registry):
	src = open(srcPath).read().decode("utf-8")
	src = src.replace("__site_path__", config.get("web", "nevowRoot"))
	src = src.replace("__site_url__", os.path.join(
		config.get("web", "serverURL")+config.get("web", "nevowRoot")))
	return src.encode("utf-8")


class StaticServer(static.File):
	"""is a server for various static files.

	There's only one hack in here: We register a processor for .shtml
	files.  In them, certain strings are replaced with *site-global*
	values.  This probably should only be used for the server URL and
	the application prefix.  Anything more dynamic should be done properly
	via renderers.
	"""
	def __init__(self, *args, **kwargs):
		if not args:
			static.File.__init__(self, os.path.join(config.get("webDir"), 
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
	"""
	builtinRoot = pkg_resources.resource_filename('gavo', "resources/web")
	def __init__(self, *args, **kwargs):
		if not args:
			static.File.__init__(self, self.builtinRoot)
		else:
			static.File.__init__(self, *args, **kwargs)


_staticServer = StaticServer()
_builtinServer = BuiltinServer()


class MaintPage(rend.Page):
	"""will be displayed during maintenance.
	"""
	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Archive Service"]
		],
		T.body[
			T.h1["Maintenance"],
			T.p["The archive service is currently shut down for maintenance."],
		]
	])


class BlockedPage(common.GavoRenderMixin, rend.Page):
	"""will be displayed when a service on a blocked resource descriptor
	is requested.
	"""
	def __init__(self, segments):
		self.segments = segments
		super(BlockedPage, self).__init__()

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Service temporarily taken down"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.h1["Service temporarily taken down"],
			T.p["The service you requested is currently under maintanence."
				" This could take from a few minutes to a day.  We are sorry for"
				" any inconvenience."],
			T.p["If the service has not come back within 24 hours, please"
				" contact ",
				T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
					"gavo@ari.uni-heidelberg.de"],
				".",]]])


class VanityLineError(Error):
	"""parse error in vanity file.
	"""
	pass


class VanityMap(object):
	"""is a container for redirects and URI rewriting.

	VanityMaps are constructed from files containing lines of the format

	<target> <key> [<option>]

	Target is a URI that must *not* include nevowRoot and must *not* start
	with a slash (unless you're going for special effects).

	Key is a single path element.  If this path element is found in the
	first segment, it is replaced with the segments in target.  This
	could be used at some point to hide the inputsDir structure even
	for user RDs, but it's a bit hard to feed the vanity map then (since
	the service would have to know about its vanity name, and we don't want
	to have to parse all RDs to come up with the VanityMap).

	<option> can be !redirect right now.  If it is, target is interpreted
	as a server-relative URI, and a redirect to it is generated, but only
	if only one or two segements are in the original query.  You can
	use this to create shortcuts with the resource dir names.  This would
	otherwise create endless loops.  This feature is a pain necessary for
	historic reasons and should probably not be used.

	Empty lines and #-on-a-line-comments are allowed in the input.
	"""

	knownOptions = set(["!redirect"])

	builtinRedirects = """
		__system__/products/products/p/get getproduct
	"""

	def __init__(self):
		self.redirects, self.mappings = {}, {}
		srcName = os.path.join(config.get("webDir"), 
			config.get("web", "vanitynames"))
		f = open(srcName)
		lineNo = 1
		for ln in f:
			try:
				self._parseLine(ln)
			except VanityLineError, msg:
				raise VanityLineError("%s, line %s: %s"%(srcName, lineNo, str(msg)))
			lineNo += 1
		f.close()
		for ln in self.builtinRedirects.split("\n"):
			self._parseLine(ln)
	
	def _parseLine(self, ln):
		ln = ln.strip()
		if not ln or ln.startswith("#"):
			return
		parts = ln.split()
		if not 1<len(parts)<4:
			raise VanityLineError("Wrong number of words in '%s'"%ln)
		option = None
		if len(parts)>2:
			option = parts.pop()
			if option not in self.knownOptions:
				raise VanityLineError("Bad option '%s'"%option)
		dest, src = parts
		if option=='!redirect':
			self.redirects[src] = dest
		else:
			self.mappings[src] = dest.split("/")

	def map(self, segments):
		"""changes the nevow-type segments list according to the mapping.

		It may raise a WebRedirect exception.
		"""
		if not segments:
			return segments
		key = segments[0]
		if key in self.redirects and len(segments)<3:
			raise WebRedirect(self.redirects[key])
		if key in self.mappings:
			segments = self.mappings[key]+list(segments[1:])
		return segments
		

_vanityMap = VanityMap()


specialChildren = {
	"oai.xml": (lambda ctx, segs, cls: cls(), vodal.RegistryRenderer),
	"debug": (lambda ctx, segs, cls: cls(ctx, segs), weberrors.DebugPage),
	"reload": (lambda ctx, segs, cls: cls(ctx, segs), ReloadPage),
	"login": (lambda ctx, segs, cls: cls(ctx), LoginPage),
}


renderClasses = {
	"custom": resourcebased.Custom,
	"static": resourcebased.Static,
	"form": resourcebased.Form,
	"feedback": resourcebased.FeedbackForm,
	"text": resourcebased.TextRenderer,
	"block": metarender.BlockRdRenderer,
	"siap.xml": vodal.SiapRenderer,
	"scs.xml": vodal.ScsRenderer,
	"upload": uploadservice.Uploader,
	"mupload": uploadservice.MachineUploader,
	"get": resourcebased.ProductRenderer,
	"img.jpeg": jpegrenderer.JpegRenderer,
	"mimg.jpeg": jpegrenderer.MachineJpegRenderer,
	"soap": soaprender.SoapRenderer,
	"info": metarender.ServiceInfoRenderer,
	"tableinfo": metarender.TableInfoRenderer,
}


class ArchiveService(common.CustomTemplateMixin, rend.Page, 
		common.GavoRenderMixin):

	def __init__(self):
		self.maintFile = os.path.join(config.get("stateDir"), "MAINT")
		self.customTemplate = os.path.join(config.get("web", "templateDir"),
			"root.html")
		rend.Page.__init__(self)
		self.rootSegments = tuple(s for s in 
			config.get("web", "nevowRoot").split("/") if s)
		self.rootLen = len(self.rootSegments)

	def data_chunkedServiceList(self, ctx, data):
		"""returns a service list alphabetically chunked.
		"""
# XXX cache this?  but if, how do we get rid of the cache on updates?
		srvList = resourcecache.getWebServiceList(None)[:]
		chunks = {}
		for srv in srvList:
			key = srv.get("title", ".")[0].upper()
			chunks.setdefault(key, []).append(srv)
		sList = [{"char": key, "chunk": val} for key, val in chunks.iteritems()]
		sList.sort(lambda a,b: cmp(a["char"], b["char"]))
		return sList

	def data_subjectServiceList(self, ctx, data):
		return resourcecache.getSubjectsList(None)

	def render_ifprotected(self, ctx, data):
		if data["owner"]:
			return ctx.tag
		else:
			return ""

	defaultDocFactory = loaders.stan(T.html[
		T.head[
			T.title["Archive Service"]
		],
		T.body[
			T.h1["Archive Service"],
			T.p["The operators of this site did not create a root.html template."
				"  So, you're seeing this fallback page."],
		]
	])

	def _locateSpecialChild(self, ctx, segments):
		"""returns a renderer for one of the special render classes above.

		For them, the URIs always have the form 
		<anything>/<action>, where action is the key
		given in specialChildren.
		"""
# XXX TODO: Do away with them, replacing them either with a child_ on
# ArchiveService or custom pages on services (Registry!).
		act = segments[-1]
		try:
			fFunc, cls = specialChildren[act]
			res = fFunc(ctx, segments[:-1], cls)
		except (UnknownURI, KeyError):
			res = None
		return res

	def _locateResourceBasedChild(self, ctx, segments):
		"""returns a standard, resource-based service renderer.

		Their URIs look like <rd id>/<service id>[/<anything].
		"""
		for srvInd in range(1, len(segments)):
			try:
				rd = resourcecache.getRd("/".join(segments[:srvInd]))
			except gavo.RdNotFound:
				continue
			try:
				subId, rendName = segments[srvInd], segments[srvInd+1]
				service = rd.get_service(subId, default=None)
				if service is None:
					raise KeyError("No such service %s"%subId)
				rendC = renderClasses[rendName]
				if service.get_requiredGroup():
					rend = creds.runAuthenticated(ctx, service.get_requiredGroup(),
					lambda service: rendC(ctx, service), service)
				else:
					rend = rendC(ctx, service)
				return rend, segments[srvInd+2:]
			except (IndexError, KeyError):
				return None, ()
		return None, ()
			
	def _hackHostHeader(self, ctx):
		"""works around host-munging of forwarders.

		This is a hack in that I hardcode port 80 for the forwarder.  Ah
		well, I don't think I have a choice there.
		"""
		request = inevow.IRequest(ctx)
		fwHost = request.getHeader("x-forwarded-host")
		if fwHost:
			request.setHost(fwHost, 80)

	if config.get("web", "enabletests"):
		from gavo.web import webtests
		child_test = webtests.Tests()

	def _realLocateChild(self, ctx, segments):
# XXX TODO: refactor this mess, clean up strange names by pulling more
# into proper services.
		self._hackHostHeader(ctx)
		if os.path.exists(self.maintFile):
			return MaintPage(), ()
		if segments[:self.rootLen]!=self.rootSegments:
			return None, ()
		segments = segments[self.rootLen:]
		if not segments or segments[0]=='':
			return self, ()

		# handle vanity names and shortcuts
		segments = _vanityMap.map(segments)

		# Special URLs (favicon.ico, TODO: robots.txt)
		if len(segments)==1 and segments[0]=="favicon.ico":
			faviconPath = config.get("web", "favicon")
			if faviconPath and faviconPath!="None" and os.path.exists(faviconPath):
				return static.File(faviconPath), ()
			else:
				return None, ()

		# base handling
		name = segments[0]
		if hasattr(self, "child_"+name):
			res = getattr(self, "child_"+name), segments[1:]
		elif not name:
			res = self, ()
		elif name=="static":
			res = _staticServer, segments[1:]
		elif name=="builtin":
			res = _builtinServer, segments[1:]
		else:
			try:
				sc = self._locateSpecialChild(ctx, segments)
				if sc:
					res = sc, ()
				else:
					res = self._locateResourceBasedChild(ctx, segments)
			except resourcebased.RdBlocked:
				return BlockedPage(segments), ()
		return res
	
	def locateChild(self, ctx, segments):
		try:
			return self._realLocateChild(ctx, segments)
		except WebRedirect, redirTo:
			root = config.get("web", "nevowRoot")
			if not root:
				root = "/"
			return url.URL.fromContext(ctx).click(root+
				str(redirTo)), ()


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("trustedquery")

if config.get("web", "errorPage")=="debug":
	appserver.DefaultExceptionHandler = weberrors.ErrorPageDebug
else:
	appserver.DefaultExceptionHandler = weberrors.ErrorPage
#root = ArchiveService()
