"""
Rendering of errors and related code.
"""
import sys

from nevow import appserver
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E
from nevow.util import log

from twisted.internet import defer

from zope.interface import implements

from gavo import base
from gavo.svcs import Error, UnknownURI, ForbiddenURI, Authenticate, WebRedirect
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


# XXX TODO: handle XXX URI must die.  refactor the mess below.
def handleUnknownURI(ctx, failure):
	if isinstance(failure.value, (UnknownURI, base.RDNotFound)):
		return NotFoundPage(failure.getErrorMessage())

def handleForbiddenURI(ctx, failure):
	if isinstance(failure.value, (ForbiddenURI,)):
		return ForbiddenPage(failure.getErrorMessage())

def handleRedirect(ctx, failure):
	if isinstance(failure.value, WebRedirect):
		return RedirectPage(failure.value.args[0])


def handleAuthentication(ctx, failure):
	if isinstance(failure.value, Authenticate):
		return AuthenticatePage("Gavo")


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
			"<h1>Internal Error</h1><p>A(n) %s occurred.  The"
			" accompanying message is: %s</p>"
			"<p>If you are seeing this, it is always a bug in our code"
			" or the data descriptions, and we would be extremely grateful"
			" for a report at"
			" gavo@ari.uni-heidelberg.de</p>"%(failure.value.__class__.__name__,
				escapeForHTML(failure.getErrorMessage())))

	def renderHTTP_exception(self, ctx, failure):
		request = inevow.IRequest(ctx)
		for hdlr in [handleUnknownURI, handleForbiddenURI, handleAuthentication,
				handleRedirect]:
			res = hdlr(ctx, failure)
			if res is not None:
				return res.renderHTTP(ctx
					).addCallback(lambda res: request.finishRequest(False)
# XXX TODO: Complain about failing error renderer here
					).addErrback(lambda res: request.finishRequest(False))
		failure.printTraceback(sys.stderr)
		request.setResponseCode(500)
		log.msg("Arguments were %s"%request.args)
		request.write(self.errorTemplate%self.getHTML(failure))  
			# write out some HTML and hope
			# for the best (it might well turn up in the middle of random output)
		request.finishRequest(False)
		return ""


class BadMethodPage(rend.Page, common.CommonRenderers):
	def __init__(self, errMsg=None):
		self.errMsg = errMsg
		rend.Page.__init__(self)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(405)
		return rend.Page.renderHTTP(self, ctx)

	def render_explanation(self, ctx, data):
		if self.errMsg:
			return ctx.tag[self.errMsg]
		else:
			return ""

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Bad Method"],
			T.invisible(render=T.directive("commonhead")),
			T.style(type="text/css")[
				"p.errmsg {background-color: #cccccc;padding:5pt}"],
		],
		T.body[
			T.img(src="/builtin/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Bad Method (405)"],
			T.p["You just tried to use some HTTP method to access this resource"
				" that this resource does not support.  This probably means that"
				" this resource is for exclusive use for specialized clients."],
			T.p["You may find whatever you were really looking"
				" for by inspecting our ",
				T.a(href="/")["list of published services"],
				"."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


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
			return "No further info."

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


class ForbiddenPage(rend.Page, common.CommonRenderers):
	def __init__(self, errMsg=None):
		self.errMsg = errMsg
		rend.Page.__init__(self)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(403)
		return rend.Page.renderHTTP(self, ctx)

	def render_explanation(self, ctx, data):
		if self.errMsg:
			return ctx.tag[self.errMsg]
		else:
			return ""

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Forbidden"],
			T.invisible(render=T.directive("commonhead")),
			T.style(type="text/css")[
				"p.errmsg {background-color: #cccccc;padding:5pt}"],
		],
		T.body[
			T.img(src="/builtin/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Access denied (403)"],
			T.p["We're sorry, but the resource you requested is forbidden."],
			T.p(class_="errmsg", render=T.directive("explanation")),
			T.p["This usually means you tried to use a renderer on a service"
				" that does not support it.  If you did not come up with the"
				" URL in question yourself, complain fiercely to the GAVO staff."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class RedirectPage(rend.Page, common.CommonRenderers):
	def __init__(self, destURL):
		self.destURL = str(destURL)
	
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(301)
		request.setHeader("Location", self.destURL)
		return super(RedirectPage, self).renderHTTP(ctx)
	
	def render_destLink(self, ctx, data):
		return ctx.tag(href=self.destURL)
	
	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Redirect"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/builtin/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Moved permanently (301)"],
			T.p["The resource you requested is available from a ",
				T.a(render=T.directive("destLink"))[
			 		"different URL"],
				"."],
			T.p["You should not see this page -- either your browser or"
				" our site is broken.  Complain."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class AuthenticatePage(rend.Page, common.CommonRenderers):
	def __init__(self, realm):
		self.realm = realm
	
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(401)
		request.setHeader('WWW-Authenticate', 'Basic realm="%s"'%self.realm)
		request.setResponseCode(401)
		return super(AuthenticatePage, self).renderHTTP(ctx)
	
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["GAVO DC -- Authentication requried"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.p["The resource you are trying to access is protected."
				"  Please enter your credentials or contact"
				" the DC staff."]]])
