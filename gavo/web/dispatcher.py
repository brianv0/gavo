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
import sys
import traceback
import urllib
import urlparse


from twisted.internet import defer
from twisted.python import components
from twisted.python import failure
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

from gavo import base
from gavo import svcs
from gavo import registry    # for registration
from gavo.imp import formal
from gavo.web import common
from gavo.web import grend
from gavo.web import weberrors

from gavo.svcs import Error, UnknownURI, ForbiddenURI, WebRedirect


# monkeypatch nevow static's mime types
static.File.contentTypes[".ascii"] = "application/octet-stream"
static.File.contentTypes[".vot"] = "application/x-votable+xml"


class ReloadPage(grend.GavoRenderMixin, rend.Page):

	modsToReload = ["gavo.web.dispatcher"]

	def __init__(self, ctx, *args, **kwargs):
		super(ReloadPage, self).__init__()
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
		<li><a href="/__system__/services/overview/form" 
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
					T.a(href=base.getConfig("web", "nevowRoot"))["DC home"],
					"."]]])


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
	values.  This probably should only be used for the server URL and
	the application prefix.  Anything more dynamic should be done properly
	via renderers.
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
	"""
	builtinRoot = pkg_resources.resource_filename('gavo', "resources/web")
	def __init__(self, *args, **kwargs):
		if not args:
			static.File.__init__(self, self.builtinRoot)
		else:
			static.File.__init__(self, *args, **kwargs)


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


class BlockedPage(grend.GavoRenderMixin, rend.Page):
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

	Target is a path that must *not* include nevowRoot and must *not* start
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
	otherwise create endless loops.

	Empty lines and #-on-a-line-comments are allowed in the input.
	"""

	knownOptions = set(["!redirect"])

	builtinRedirects = """
		__system__/products/p/get getproduct
		__system__/services/registry/pubreg.xml oai.xml
		__system__/services/overview/external odoc
		__system__/dc_tables/show/tablenote tablenote
		__system__/dc_tables/show/tableinfo tableinfo
	"""

	def __init__(self):
		self.redirects, self.mappings = {}, {}
		for ln in self.builtinRedirects.split("\n"):
			self._parseLine(ln)
		self._loadFromFile()

	def _loadFromFile(self):
		srcName = os.path.join(base.getConfig("webDir"), 
			base.getConfig("web", "vanitynames"))
		if not os.path.isfile(srcName):
			return
		f = open(srcName)
		lineNo = 1
		for ln in f:
			try:
				self._parseLine(ln)
			except VanityLineError, msg:
				raise VanityLineError("%s, line %s: %s"%(srcName, lineNo, str(msg)))
			lineNo += 1
		f.close()

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
	"debug": (lambda ctx, segs, cls: cls(ctx, segs), weberrors.DebugPage),
	"reload": (lambda ctx, segs, cls: cls(ctx, segs), ReloadPage),
	"login": (lambda ctx, segs, cls: cls(ctx), LoginPage),
}


class ArchiveService(common.CustomTemplateMixin, rend.Page, 
		grend.GavoRenderMixin):

	def __init__(self):
		self.maintFile = os.path.join(base.getConfig("stateDir"), "MAINT")
		self.customTemplate = os.path.join(base.getConfig("web", "templateDir"),
			"root.html")
		rend.Page.__init__(self)
		self.rootSegments = tuple(s for s in 
			base.getConfig("web", "nevowRoot").split("/") if s)
		self.rootLen = len(self.rootSegments)

	def renderHTTP(self, ctx):
		return rend.Page.renderHTTP(self, ctx
			).addErrback(self._handleEscapedErrors, ctx)
	
	def _handleEscapedErrors(self, failure, ctx):
		if isinstance(failure.value, svcs.UnknownURI):
			return weberrors.NotFoundPage()
		return failure

	def data_chunkedServiceList(self, ctx, data):
		"""returns a service list alphabetically chunked.
		"""
# XXX cache this?  but if, how do we get rid of the cache on updates?
		srvList = base.caches.getWebServiceList(None)[:]
		chunks = {}
		for srv in srvList:
			key = srv.get("title", ".")[0].upper()
			chunks.setdefault(key, []).append(srv)
		sList = [{"char": key, "chunk": val} for key, val in chunks.iteritems()]
		sList.sort(lambda a,b: cmp(a["char"], b["char"]))
		return sList

	def data_subjectServiceList(self, ctx, data):
		return base.caches.getSubjectsList(None)

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

		Their URIs look like <rd id>/<service id>{/<anything>}.
		"""
		for srvInd in range(1, len(segments)-1):
			try:
				rd = base.caches.getRD("/".join(segments[:srvInd]))
			except base.RDNotFound:
				continue
			try:
				subId, rendName = segments[srvInd], segments[srvInd+1]
				service = rd.getService(subId)
				if service is None:
					raise KeyError("No such service: %s"%subId)
				rendC = svcs.getRenderer(rendName)
				if service.limitTo:
					rend = common.runAuthenticated(ctx, service.limitTo,
						lambda service: rendC(ctx, service), service)
				else:
					rend = rendC(ctx, service)
				return rend, segments[srvInd+2:]
			except (IndexError, KeyError):
				traceback.print_exc()
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

	if base.getConfig("web", "enabletests"):
		from gavo.web import webtests
		child_test = webtests.Tests()

	child_static = StaticServer()
	child_builtin = BuiltinServer()

	def _realLocateChild(self, ctx, segments):
# XXX TODO: refactor this mess, clean up strange names by pulling more
# into proper services.
		self._hackHostHeader(ctx)
		if os.path.exists(self.maintFile):
			return MaintPage(), ()
		if segments[:self.rootLen]!=self.rootSegments:
			return None, ()
		segments = segments[self.rootLen:]
		if not segments or len(segments)==1 and segments[0]=='':
			return self, ()

		# handle vanity names and shortcuts
		segments = _vanityMap.map(segments)

		# Special URLs (favicon.ico, TODO: robots.txt)
		if len(segments)==1 and segments[0]=="favicon.ico":
			faviconPath = base.getConfig("web", "favicon")
			if faviconPath and faviconPath!="None" and os.path.exists(faviconPath):
				return static.File(faviconPath), ()
			else:
				return None, ()

		# base handling
		name = segments[0]
		if name and hasattr(self, "child_"+name):
			res = getattr(self, "child_"+name), segments[1:]
		else:
			try:
				sc = self._locateSpecialChild(ctx, segments)
				if sc:
					res = sc, ()
				else:
					res = self._locateResourceBasedChild(ctx, segments)
			except grend.RDBlocked:
				return BlockedPage(segments), ()
		return res
	
	def locateChild(self, ctx, segments):
		try:
			res, segments = self._realLocateChild(ctx, segments)
		except WebRedirect, redirTo:
			root = base.getConfig("web", "nevowRoot")
			if not root:
				root = "/"
			return url.URL.fromContext(ctx).click(root+
				str(redirTo)), ()
		except ForbiddenURI, exc:
			return weberrors.ForbiddenPage(str(exc)), ()
		except UnknownURI, exc:
			return weberrors.NotFoundPage(str(exc)), ()
		except Exception, msg:
			traceback.print_exc()
			raise
		if res is None:
			return weberrors.NotFoundPage(), ()
		else:
			return res, segments


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)


if base.getConfig("web", "errorPage")=="debug":
	appserver.DefaultExceptionHandler = weberrors.ErrorPageDebug
else:
	appserver.DefaultExceptionHandler = weberrors.ErrorPage
#root = ArchiveService()
