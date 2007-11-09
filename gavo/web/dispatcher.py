"""
The dispatcher for the new nevow-based web interface.
"""


import urllib
import re
import traceback
import math
import cStringIO
import new

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
# need importparser to register its resourcecache
from gavo.parsing import importparser
from gavo.web import common
from gavo.web import product
from gavo.web import resourcebased
from gavo.web import siapservice

from gavo.web.common import Error, UnknownURI


class DebugPage(rend.Page):
	def __init__(self, *args, **kwargs):
		self.args, self.kwargs = args, kwargs

	def data_args(self, ctx, data):
		return self.args

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
		self.failure = failure
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		return defer.maybeDeferred(self.renderHTTP, ctx).addCallback(
			lambda _: request.finishRequest(False)).addErrback(
			lambda failure: failure)


class ErrorPage(ErrorPageDebug):
	implements(inevow.ICanHandleException)

	def renderHTTP_exception(self, ctx, failure):
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		msg = ("<html><head><title>Internal Error</title></head>"
			"<body><h1>Internal Error</h1><p>The error message is: %s</p>"
			"<p>If you do not know how to work around this, please contact"
			" gavo@ari.uni-heidelberg.de</p></body></html>"%failure.getErrorMessage())
		request.write(msg)
		request.finishRequest(False)



renderClasses = {
	"form": resourcebased.Form,
	"siap": siapservice.SiapService,
	"getproduct": product.Product,
	"debug": DebugPage,
}

class ArchiveService(rend.Page, common.GavoRenderMixin):

	def __init__(self):
		rend.Page.__init__(self)
		self.rootSegments = tuple(s for s in 
			config.get("web", "nevowRoot").split("/") if s)
		self.rootLen = len(self.rootSegments)

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Archive Service"]
		],
		T.body[
			T.p[
				T.a(href="/apfs/res/apfs_new/catquery/form",
					render=T.directive("rootlink"))["Here"],
				" or ",
				T.a(href="/maidanak/res/positions/siap/form",
					render=T.directive("rootlink"))["Here"],
				" or ",
				T.a(href="/lswscans/res/positions/siap/form",
					render=T.directive("rootlink"))["Here"],
			]
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
				res = renderClasses[act](ctx, segments[:-1])
			except (UnknownURI, KeyError):
				res = None
		return res, ()


setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("querulator")

appserver.DefaultExceptionHandler = ErrorPageDebug
#root = ArchiveService()
