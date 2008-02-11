"""
The dispatcher for the new nevow-based web interface.
"""


import cStringIO
import math
import new
import os
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

from gavo import config
from gavo import resourcecache
from gavo import utils
# need importparser to register its resourcecache
from gavo.parsing import importparser
from gavo.web import common
from gavo.web import creds
from gavo.web import product
from gavo.web import resourcebased
# need servicelist to register its resourcecache
from gavo.web import servicelist
# need scs to register its CondDescs
from gavo.web import scs
from gavo.web import jpegrenderer
from gavo.web import uploadservice
from gavo.web import vodal

from gavo.web.common import Error, UnknownURI


class DebugPage(rend.Page):

	name = "debug"

	def __init__(self, ctx, *args, **kwargs):
		self.args, self.kwargs = args, kwargs

	def data_args(self, ctx, data):
		return tuple((k, str(v)) for k, v in inevow.IRequest(ctx).args.iteritems())

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Debug page"],
		],
		T.body[
			T.h1["Here we go"],
			T.p["I was constructed with the following arguments:"],
			T.ul(render=rend.sequence, id="args", data=T.directive("args"))[
				T.li(pattern="item", render=rend.data)
			]
		]
	])


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
		<p><a href="/" n:render="rootlink">Main Page</a></p>
    </body></html>
    """)


def handleUnknownURI(ctx, failure):
	if isinstance(failure.value, common.UnknownURI):
		request = inevow.IRequest(ctx)
		request.setResponseCode(404)
		request.setHeader("content-type", "text/plain")
		request.write("The resource you requested was not found on the server.\n\n")
		request.write(failure.getErrorMessage()+"\n")
		request.finishRequest(False)
		return True


class ErrorPageDebug(rend.Page):
	implements(inevow.ICanHandleException)

	docFactory = loaders.xmlstr("""<html
    xmlns:n='http://nevow.com/ns/nevow/0.1'>
    <head><title>500 error</title>
    <style type="text/css">
    body { border: 6px solid red; padding: 1em; }
    </style>
    </head>
    <body><h1>Server error.</h1>
    <p>This is the traceback:</p>
    <pre n:render="data" n:data="failure"></pre>
    </body></html>
    """)

	def data_failure(self, ctx, data):
		return str(self.failure)

	def renderHTTP_exception(self, ctx, failure):
		if handleUnknownURI(ctx, failure):
			return appserver.errorMarker
		failure.printTraceback()
		self.failure = failure
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		return defer.maybeDeferred(self.renderHTTP, ctx).addCallback(
			lambda _: request.finishRequest(False)).addErrback(
			lambda failure: failure)


class ErrorPage(ErrorPageDebug):
	implements(inevow.ICanHandleException)

	def renderHTTP_exception(self, ctx, failure):
		if handleUnknownURI(ctx, failure):
			return appserver.errorMarker
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		msg = ("<html><head><title>Internal Error</title></head>"
			"<body><h1>Internal Error</h1><p>The error message is: %s</p>"
			"<p>If you do not know how to work around this, please contact"
			" gavo@ari.uni-heidelberg.de</p></body></html>"%failure.getErrorMessage())
		request.write(msg)
		request.finishRequest(False)


def _replaceConfigStrings(srcPath, registry):
	src = open(srcPath).read()
	src = src.replace("__site_path__", config.get("web", "nevowRoot"))
	return src


class StaticServer(static.File):
	"""is a server for various static files.

	There's only one hack in here: We register a processor for .phtml
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

_staticServer = StaticServer()


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


def _makeVanityMap():
	"""returns the default map for vanity names.

	Vanity names are shortcuts that lead to web pages.  They are not
	intended for creating, e.g., "more beautiful" IVOA identifiers.

	For now, the vanity names simply reside in a flat text file
	given in the config in the key vanitynames that works as an
	input for utils.NameMap.

	The target URLs must *not* include nevowRoot and must *not* start
	with a slash (unless you're going for special effects).
	"""
	srcF = os.path.join(config.get("webDir"), 
		config.get("web", "vanitynames"))
	return utils.NameMap(srcF)

_vanityMap = _makeVanityMap()

	
renderClasses = {
	"form": (resourcebased.getServiceRend, resourcebased.Form),
	"oai.xml": (lambda ctx, segs, cls: cls(), vodal.RegistryRenderer),
	"siap.xml": (resourcebased.getServiceRend, vodal.SiapRenderer),
	"scs.xml": (resourcebased.getServiceRend, vodal.ScsRenderer),
	"getproduct": (lambda ctx, segs, cls: cls(ctx, segs), product.Product),
	"upload": (resourcebased.getServiceRend, uploadservice.Uploader),
	"mupload": (resourcebased.getServiceRend, uploadservice.MachineUploader),
	"img.jpeg": (resourcebased.getServiceRend, jpegrenderer.JpegRenderer),
	"mimg.jpeg": (resourcebased.getServiceRend, jpegrenderer.MachineJpegRenderer),
	"debug": (lambda ctx, segs, cls: cls(ctx, segs), DebugPage),
	"reload": (lambda ctx, segs, cls: cls(ctx, segs), ReloadPage),
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

	def render_serviceURL(self, ctx, data):
		#XXX TODO: figure out how to get slots into attributes and scrap this.
		parsed = urlparse.urlparse(data["accessURL"])
		return ctx.tag(href=urlparse.urlunparse(("", "")+parsed[2:]))[
			data["title"]]

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

	def _locateRenderChild(self, ctx, segments):
		act = segments[-1]
		try:
			fFunc, cls = renderClasses[act]
			res = fFunc(ctx, segments[:-1], cls)
		except (UnknownURI, KeyError):
			res = None
		except resourcebased.RdBlocked:
			return BlockedPage(segments)
		return res

	def locateChild(self, ctx, segments):
		if os.path.exists(self.maintFile):
			return MaintPage(), ()
		if segments[:self.rootLen]!=self.rootSegments:
			return None, ()
		segments = segments[self.rootLen:]
		if not segments or segments[0]=='':
			return self, ()
		# redirect away vanity names
		if 0<len(segments)<3 and segments[0] in _vanityMap:
			root = config.get("web", "nevowRoot")
			if not root:
				root = "/"
			return url.URL.fromContext(ctx).click(root+
				_vanityMap.resolve(segments[0])), ()
		# Special case for service-specific static data
		if ".static." in segments:
			sPos = list(segments).index(".static.")
			return resourcebased.getServiceRend(ctx, segments[:sPos], 
				resourcebased.Static), segments[sPos+1:]
		# base handling
		name = segments[0]
		if hasattr(self, "child_"+name):
			res = getattr(self, "child_"+name), segments[1:]
		elif not segments or not segments[0]:
			res = self, ()
		elif segments[0]=="static":
			res = _staticServer, segments[1:]
		else:
			res = self._locateRenderChild(ctx, segments), ()
		return res


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("querulator")

if config.get("web", "errorPage")=="debug":
	appserver.DefaultExceptionHandler = ErrorPageDebug
else:
	appserver.DefaultExceptionHandler = ErrorPage
#root = ArchiveService()
