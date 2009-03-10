"""
Rendering of errors and related code.
"""

from nevow import appserver
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E
from nevow.util import log

from twisted.internet import defer

from zope.interface import implements

from gavo import base
from gavo.svcs import Error, UnknownURI, ForbiddenURI, Authenticate
from gavo.web import common


def escapeForHTML(aString):
	return aString.replace("&", "&amp;"
		).replace("<", "&lt;").replace(">", "&gt;")

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
	if isinstance(failure.value, (UnknownURI, base.RDNotFound)):
		return NotFoundPage(failure.getErrorMessage())
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
		request.write("I am not allowed to show you the resource"
			" you requested.\n\n")
		request.write(failure.getErrorMessage()+"\n")
		request.finishRequest(False)
		return True


def handleAuthentication(ctx, failure):
	if isinstance(failure.value, Authenticate):
		request = inevow.IRequest(ctx)
		request.setHeader('WWW-Authenticate', 'Basic realm="Gavo"')
		request.setResponseCode(401)
		request.write("Authorization required")
		request.finishRequest(False)



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
		return (
			"<h1>Internal Error</h1><p>The error message is: %s</p>"
			"<p>If you are seeing this, it is always a bug in our code"
			" or the data descriptions, and we would be extremely grateful"
			" for a report at"
			" gavo@ari.uni-heidelberg.de</p>"%escapeForHTML(
				failure.getErrorMessage()))

	def renderHTTP_exception(self, ctx, failure):
		if (handleUnknownURI(ctx, failure) or handleForbiddenURI(ctx, failure)
				or handleAuthentication(ctx, failure)):
			return appserver.errorMarker
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		log.msg("Arguments were %s"%request.args)
		request.write(self.errorTemplate%self.getHTML(failure))  
			# write out some HTML and hope
			# for the best (it might well turn up in the middle of random output)
		request.finishRequest(False)
		return ""


class NotFoundPage(rend.Page, common.CommonRenderers):
	def __init__(self, errMsg=None):
		self.errMsg = errMsg
		rend.Page.__init__(self)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(404)
		return rend.Page.renderHTTP(self, ctx)

	def render_explanation(self, ctx, data):
		if self.errMsg:
			return ctx.tag[self.errMsg]
		else:
			return ""

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Not found"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/builtin/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Resource Not Found (404)"],
			T.p["We're sorry, but the resource you requested could not be located."],
			T.p(class_="errmsg", render=T.directive("explanation")),
			T.p["If this message resulted from following a link from ",
				T.strong["within the data center"],
				", you have discovered a bug, and we would be"
				" extremely grateful if you could notify us."],
			T.p["If you got here following an ",
				T.strong["external link"],
				", we would be"
				" grateful for a notification as well.  We will ask the"
				" external operators to fix their links or provide"
				" redirects as appropriate."],
			T.p["In either case, you may find whatever you were looking"
				" for by inspecting our ",
				T.a(href="/")["list of published services"],
				"."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])
