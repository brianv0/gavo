"""
Dispatcher and much that should go in different modules for the new
nevow-based web interface.
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

from nevow import rend
from nevow import loaders
from nevow import context
from nevow import inevow
from nevow import static
from nevow import tags as T, entities as E

from zope.interface import implements

from gavo import config
# need importparser to register its resourcecache
from gavo.parsing import importparser
from gavo.web import product
from gavo.web import resourcebased
from gavo.web.querulator import queryrun

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


class ErrorPage(rend.Page):
	implements(inevow.ICanHandleException)

	docFactory = loaders.xmlstr("""<html
    xmlns:n='http://nevow.com/ns/nevow/0.1'>
    <head><title>500 error</title>
    <style type="text/css">
    body { border: 6px solid red; padding: 1em; }
    </style>
    </head>
    <body><h1>Ouchie. Server error.</h1>
    <p>This is the traceback:</p>
    <pre n:render="data" n:data="failure"></pre>
    </body></html>
    """)

	def data_failure(self, ctx, data):
		print dir(self.failure)
		return str(self.failure)

	def renderHTTP_exception(self, ctx, failure):
		self.failure = failure
		print ">>>>>>>>>>>>>>", dir(failure)
		print failure.getErrorMessage()
		print failure.getTraceback()
		inevow.IRequest(ctx).setResponseCode(500)
		ctx2 = context.PageContext(tag=self, parent=ctx)
		return self.renderHTTP(ctx2)

error500 = ErrorPage()


renderClasses = {
	"form": resourcebased.Form,
	"getproduct": product.Product,
	"debug": DebugPage,
}

class ArchiveService(rend.Page):

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Archive Service"]
		],
		T.body[
			T.p[
				T.a(href="apfs/res/apfs_new/catquery/form")["Here"],
				" or ",
				T.a(href="maidanak/res/positions/siap/form")["Here"],
			]
		]
	])

	def locateChild(self, ctx, segments):
		ctx.remember(error500, inevow.ICanHandleException)
		if not segments or not segments[0]:
			res = self
		else:
			name = segments[0]
			if hasattr(self, "child_"+name):
				return getattr(self, "child_"+name), segments[1:]
			
			act = segments[-1]
			try:
				res = renderClasses[act](segments[:-1])
			except UnknownURI:
				res = rend.FourOhFour()
			except:
				traceback.print_exc()
				res = rend.FourOhFour()
		return res, ()

setattr(ArchiveService, 'child_formal.css', formal.defaultCSS)
setattr(ArchiveService, 'child_js', formal.formsJS)

from gavo import nullui
config.setDbProfile("querulator")

root = ArchiveService()
# wsgiApp = wsgi.createWSGIApplication(root)
