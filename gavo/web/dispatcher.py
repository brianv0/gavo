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

import formal

from twisted.internet import defer
from twisted.python import components

from nevow import appserver
from nevow import context
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import static
from nevow import tags as T, entities as E

from zope.interface import implements

from gavo import config
from gavo import resourcecache
# need importparser to register its resourcecache
from gavo.parsing import importparser
from gavo.web import common
from gavo.web import product
from gavo.web import resourcebased
# need servicelist to register its resourcecache
from gavo.web import servicelist
from gavo.web import siaprenderer
from gavo.web import uploadservice

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
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		msg = ("<html><head><title>Internal Error</title></head>"
			"<body><h1>Internal Error</h1><p>The error message is: %s</p>"
			"<p>If you do not know how to work around this, please contact"
			" gavo@ari.uni-heidelberg.de</p></body></html>"%failure.getErrorMessage())
		request.write(msg)
		request.finishRequest(False)



renderClasses = {
	"form": (resourcebased.getServiceRend, resourcebased.Form),
	"siap.xml": (resourcebased.getServiceRend, siaprenderer.SiapRenderer),
	"getproduct": (lambda ctx, segs, cls: cls(ctx, segs), product.Product),
	"upload": (resourcebased.getServiceRend, uploadservice.Uploader),
	"mupload": (resourcebased.getServiceRend, uploadservice.MachineUploader),
	"debug": (lambda ctx, segs, cls: cls(ctx, segs), DebugPage),
}

class ArchiveService(common.CustomTemplateMixin, rend.Page, 
		common.GavoRenderMixin):

	def __init__(self):
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
		return [{"char": key, "chunk": val} for key, val in chunks.iteritems()]

	def render_serviceURL(self, ctx, data):
		#XXX TODO: figure out how to get slots into attributes and scap this.
		return ctx.tag(href=data["accessURL"])[data["title"]]

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

	def locateChild(self, ctx, segments):
		if segments[:self.rootLen]!=self.rootSegments:
			return None, ()
		segments = segments[self.rootLen:]
		if not segments or not segments[0]:
			res = self
		else:
			name = segments[0]
			if hasattr(self, "child_"+name):
				return getattr(self, "child_"+name), segments[1:]
			
			act = segments[-1]
			try:
				fFunc, cls = renderClasses[act]
				res = fFunc(ctx, segments[:-1], cls)
			except (UnknownURI, KeyError):
				res = None
		return res, ()


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("querulator")

if config.get("web", "errorPage")=="debug":
	appserver.DefaultExceptionHandler = ErrorPageDebug
else:
	appserver.DefaultExceptionHandler = ErrorPage
#root = ArchiveService()
