"""
Rendering of errors and related code.
"""

from nevow import appserver
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E

from twisted.internet import defer

from zope.interface import implements

import gavo
from gavo.web.common import Error, UnknownURI, ForbiddenURI


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

def handleUnknownURI(ctx, failure):
	if isinstance(failure.value, (UnknownURI, gavo.RdNotFound)):
		request = inevow.IRequest(ctx)
		request.setResponseCode(404)
		request.setHeader("content-type", "text/plain")
		request.write("The resource you requested was not found on the server.\n\n")
		request.write(failure.getErrorMessage()+"\n")
		request.finishRequest(False)
		return True


def handleForbiddenURI(ctx, failure):
	if isinstance(failure.value, (ForbiddenURI,)):
		request = inevow.IRequest(ctx)
		request.setResponseCode(403)
		request.setHeader("content-type", "text/plain")
		request.write("I am not allowed to render the resource you requested.\n\n")
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

	errorTemplate = ("<html><head><title>Severe Error</title></head>"
		'<body><div style="position:fixed;left:4px;top:4px;'
		'visibility:visible;overflow:visible !important;'
		'max-width:600px !important;z-index:500">'
		'<div style="border:2px solid red;'
		'width:400px !important;background:white">'
		'%s'
		'</div></div></body></html>')

	def getHTML(self, failure):
# XXX TODO: Alejandro's pgsql timeout patch somehow doesn't expose 
# TimeoutError, and I don't have time to fix this now.  So, I check the 
# exception type the rough way.
		if failure.value.__class__.__name__.endswith("TimeoutError"):
			return (
			"<h1>Database Timeout</h1><p>The database operation"
			" handling your query took too long.  This may mean that</p>"
			"<ul><li>our system is too busy (in which case you could try "
			" again later)</li>"
			"<li>your query selects too much data (in which case lowering"
			" the query limit might yield at least <em>some</em> data)</li>"
			"<li>your query is too complex or confuses our database system."
			" You could try turning off sorting or lowering the query limit.</li>"
			"</ul><p>In any case, you are most welcome to report this to"
			" <a href='mailto:gavo@ari.uni-heidelberg.de'>us</a>"
			" (please include the result link you can find on the last"
			" page).  We will be happy to try to assist you and possibly"
			" fix the problem you've hit.</p>")
		return (
			"<h1>Internal Error</h1><p>The error message is: %s</p>"
			"<p>If you do not know how to work around this, please contact"
			" gavo@ari.uni-heidelberg.de</p>"%failure.getErrorMessage())

	def renderHTTP_exception(self, ctx, failure):
		if handleUnknownURI(ctx, failure) or handleForbiddenURI(ctx, failure):
			return appserver.errorMarker
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.write(self.errorTemplate%self.getHTML(failure))  
			# write out some HTML and hope
			# for the best (it might well turn up in the middle of random output)
		request.finishRequest(False)
		return ""
