"""
Default error displays for the data center and error helper code.

Everything in here must render synchronuosly.

You probably should not construct anything in this module directly
but rather just raise the appropriate exceptions from svcs.
"""

import sys
import urlparse

from nevow import context
from nevow import inevow
from nevow import loaders
from nevow import rend
from nevow import tags as T, entities as E
from twisted.internet import defer
from twisted.python import failure
from twisted.python import log
from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.web import common


def escapeForHTML(aString):
	return aString.replace("&", "&amp;"
		).replace("<", "&lt;").replace(">", "&gt;")


class ErrorPage(rend.Page, common.CommonRenderers):
	"""A base for error handling pages.

	The idea is that you set the "handles" class attribute to 
	the exception you handle.  The exception has to match exactly, i.e.,
	no isinstancing is done.

	You also must set status to the HTTP status code the error should
	return.

	All error pages have a failure attribute that's a twisted failure
	with all the related mess (e.g., tracebacks).

	You have the status and message data methods.
	"""
	handles = None
	status = 500

	def __init__(self, error):
		self.failure = error

	def data_status(self, ctx, data):
		return str(self.status)

	def data_message(self, ctx, data):
		return self.failure.getErrorMessage()

	def render_message(self, ctx, data):
		return ctx.tag(class_="errmsg")[self.failure.getErrorMessage()]

	def render_rdlink(self, ctx, data):
		if hasattr(self.failure.value, "rd") and self.failure.value.rd:
			rdURL = base.makeAbsoluteURL("/browse/%s"%
				self.failure.value.rd.sourceId)
			return T.p(class_="rdbacklink")["Also see the ",
				T.a(href=rdURL)["resources provided by this RD"],
				"."]
		return ""

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(self.status)
		return rend.Page.renderHTTP(self, ctx)


class NotFoundPage(ErrorPage):
	handles = svcs.UnknownURI
	status = 404

	def renderHTTP_notFound(self, ctx):
		return self.renderHTTP(ctx)

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Not found"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Resource Not Found (404)"],
			T.p["We're sorry, but the resource you requested could not be located."],
			T.p(render=T.directive("message")),
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
				T.a(href="/")["list of published services"], "."],
			T.p(render=T.directive("rdlink")),
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class OtherNotFoundPage(NotFoundPage):
	handles = base.NotFoundError


class RDNotFoundPage(NotFoundPage):
	handles = base.RDNotFound


class ForbiddenPage(ErrorPage):
	handles = svcs.ForbiddenURI
	status = 403

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Forbidden"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Access denied (403)"],
			T.p["We're sorry, but the resource you requested is forbidden."],
			T.p(render=T.directive("message")),
			T.p["This usually means you tried to use a renderer on a service"
				" that does not support it.  If you did not come up with the"
				" URL in question yourself, complain fiercely to the GAVO staff."],
			T.p(render=T.directive("rdlink")),
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class RedirectPage(ErrorPage):
	handles = svcs.WebRedirect
	status = 301

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		args = urlparse.urlparse(request.uri).query
		if args:
			self.destURL = self.failure.value.dest+"?"+args
		else:
			self.destURL = self.failure.value.dest
		request.setHeader("location", str(self.destURL))
		return ErrorPage.renderHTTP(self, ctx)
	
	def render_destLink(self, ctx, data):
		return ctx.tag(href=self.destURL)
	
	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Redirect"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
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


class AuthenticatePage(ErrorPage):
	handles = svcs.Authenticate
	status = 401

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('WWW-Authenticate', 
			'Basic realm="%s"'%str(self.failure.value.realm))
		return ErrorPage.renderHTTP(self, ctx)
	
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["GAVO DC -- Authentication requried"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.p["The resource you are trying to access is protected."
				"  Please enter your credentials or contact"
				" the DC staff."]]])


class BadMethodPage(ErrorPage):
	handles = svcs.BadMethod
	status = 405

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Bad Method"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
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


class NotAcceptable(ErrorPage):
	handles = base.DataError
	status = 406

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Not Acceptable"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Not Acceptable (406)"],
			T.p["The server cannot generate the data you requested."
				"  The associated message is:"],
			T.p(render=T.directive("message")),
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class ErrorDisplay(ErrorPage):
	handles = base.ReportableError
	status = 500

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Error"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Server-side Error (500)"],
			T.p(render=T.directive("message")),
			T.p["This usually means we've fouled up, and there's no"
				" telling whether we've realized that already.  So, chances are"
				" we'd be grateful if you told us at the address given below."
				" Thanks."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])
# HTML mess for last-resort type error handling.
errorTemplate = (
		'<body><div style="position:fixed;left:4px;top:4px;'
		'visibility:visible;overflow:visible !important;'
		'max-width:600px !important;z-index:500">'
		'<div style="border:2px solid red;'
		'width:400px !important;background:white">'
		'%s'
		'</div></div></body></html>')

def _formatFailure(failure):
	return errorTemplate%(
		"<h1>Internal Error</h1><p>A(n)"
		" %s exception occurred.  The"
		" accompanying message is: '%s'</p>"
		"<p>If you are seeing this, it is always a bug in our code"
		" or the data descriptions, and we would be extremely grateful"
		" for a report at"
		" gavo@ari.uni-heidelberg.de</p>"%(failure.value.__class__.__name__,
			escapeForHTML(failure.getErrorMessage())))


class InternalServerErrorPage(ErrorPage):
	"""A catch-all page served when no other error page seemed responsible.
	"""
	handles = base.Error  # meaningless, no isinstance done here
	status = 500

	def data_excname(self, ctx, data):
		log.err(self.failure, _why="Uncaught exception")
		return self.failure.value.__class__.__name__

	def renderInnerException(self, ctx):
		"""called when rendering already has started.

		We don't know where we're sitting, so we try to break out as well
		as we can.
		"""
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)  # probably too late, but log still profits.
		request.write(_formatFailure(self.failure))
		request.finishRequest(False)
		return ""

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		base.ui.notifyFailure(self.failure)
		base.ui.notifyInfo("Arguments of failed request: %s"%
			repr(request.args))
		if request.startedWriting:
			# exception happened while rendering a page.
			return self.renderInnerException(ctx)
		else:
			return ErrorPage.renderHTTP(self, ctx)

	docFactory = common.doctypedStan(T.html[
			T.head[T.title["GAVO DC -- Uncaught Exception"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.img(src="/static/img/logo_medium.png", style="position:absolute;"
				"right:0pt"),
			T.h1["Server Error (500)"],
			T.p["Your action has caused a(n) ",
				T.span(render=str, data=T.directive("excname")),
				" exception to occur.  As additional info, the failing code"
				" gave:"],
			T.p(render=T.directive("message")),
			T.p["This is always a bug in our software, and we would really"
				" be grateful for a report to the contact address below,"
				" preferably with a description of what you were trying to do,"
				" including any data pieces if applicable.  Thanks."],
			T.hr,
			T.address[T.a(href="mailto:gavo@ari.uni-heidelberg.de")[
				"gavo@ari.uni-heidelberg.de"]],
		]])


class PanicPage(rend.Page):
	"""The last-resort page when some error handler failed.
	"""
	implements(inevow.ICanHandleException)

	def renderHTTP_exception(self, ctx, failure):
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		base.ui.notifyFailure(failure)
		base.ui.notifyInfo("Arguments were %s"%request.args)
			# write out some HTML and hope
			# for the best (it might well turn up in the middle of random output)
		request.write(
			"<html><head><title>Severe Error</title></head>"+
			_formatFailure(failure)+
			"</html>")


_getErrorPage = utils.buildClassResolver(
	baseClass=ErrorPage, 
	objects=globals().values(),
	instances=False, 
	key=lambda obj: obj.handles, 
	default=InternalServerErrorPage)


class DCExceptionHandler(object):
	"""The toplevel exception handler.
	"""
# Since something here is broken in nevow, this isn't really used.
	implements(inevow.ICanHandleException, inevow.ICanHandleNotFound)

	def renderHTTP_exception(self, ctx, error):
		ctx.remember(PanicPage) # have last resort in place when we fail
		if error is None:
			error = failure.Failure()
		def panic(failure):
			return PanicPage(failure), ()
		return _getErrorPage(error.value.__class__)(error)

	def renderHTTP_notFound(self, ctx):
		try:
			raise svcs.UnknownURI("locateChild returned None")
		except svcs.UnknownURI:
			return NotFoundPage(failure.Failure())

	def renderInlineException(self, ctx, error):
		# We can't really do that.  Figure out how to break out of this.
		log.err(error, _why="Inline exception")
		return ('<div style="border: 1px dashed red; color: red; clear: both">'
			'[[ERROR]]</div>')


def getDCErrorPage(error):
	"""returns stuff for root.ErrorCatchingNevowSite.
	"""
# This should be replaced by remembering DCExceptionHandler when
# some day we fix nevow.
	if error is None:
		error = failure.Failure()
	return _getErrorPage(error.value.__class__)(error)
