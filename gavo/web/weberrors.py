"""
Default error displays for the data center and error helper code.

Everything in here must render synchronuosly.

You probably should not construct anything in this module directly
but rather just raise the appropriate exceptions from svcs.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import urlparse

from nevow import inevow
from nevow import rend
from nevow import tags as T
from twisted.internet import defer
from twisted.python import failure
from twisted.python import log
from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import config
from gavo.web import common


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
	titleMessage = "Unspecified Error"
	beforeMessage = "We're sorry, but something didn't work out:"
	afterMessage = T.p["This generic text shouldn't be here.  The"
		" child class should override afterMessage."]
	_footer = "delete this when done"

	def __init__(self, error):
		self.failure = error

	def data_status(self, ctx, data):
		return str(self.status)

	def data_message(self, ctx, data):
		return self.failure.getErrorMessage()

	def render_beforeMessage(self, ctx, data):
		return ctx.tag[self.beforeMessage]

	def render_afterMessage(self, ctx, data):
		return ctx.tag[self.afterMessage]

	def render_message(self, ctx, data):
		return ctx.tag(class_="errmsg")[self.failure.getErrorMessage()]

	def render_hint(self, ctx, data):
		if (hasattr(self.failure.value, "hint") and self.failure.value.hint):
			return ctx.tag[T.strong["Hint: "], 
				self.failure.value.hint]
		return ""

	def render_rdlink(self, ctx, data):
		if hasattr(self.failure.value, "rd") and self.failure.value.rd:
			rdURL = base.makeAbsoluteURL("/browse/%s"%
				self.failure.value.rd.sourceId)
			return T.p(class_="rdbacklink")["Also see the ",
				T.a(href=rdURL)["resources provided by this RD"],
				"."]
		return ""
	
	def render_titlemessage(self, ctx, data):
		return ctx.tag["%s -- %s"%(
			base.getConfig("web", "sitename"), self.titleMessage)]
	
	def render_footer(self, ctx, data):
		return ctx.tag[
			T.hr,
			T.address[T.a(href="mailto:%s"%config.getMeta(
					"contact.email").getContent())[
				config.getMeta("contact.email").getContent()]]]

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(self.status)
		return rend.Page.renderHTTP(self, ctx)
	
	docFactory = common.doctypedStan(T.html[
		T.head(render=T.directive("commonhead"))[
			T.title(render=T.directive("titlemessage"))],
		T.body[
			T.img(src="/static/img/logo_medium.png", class_="headlinelogo",
				style="position:absolute;right:5pt"),
			T.h1[
				T.invisible(render=T.directive("titlemessage")),
				" (",
				T.invisible(data=T.directive("status"), render=T.directive("string")),
				")"],
			T.p(render=T.directive("beforeMessage")),
			T.div(class_="errors", render=T.directive("message")),
			T.div(render=T.directive("afterMessage")),
			T.invisible(render=T.directive("footer"))]])



class NotFoundPage(ErrorPage):
	handles = svcs.UnknownURI
	status = 404
	titleMessage = "Not Found"
	beforeMessage = ("We're sorry, but the resource you"
		" requested could not be located.")
	afterMessage = [
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
			T.p(render=T.directive("rdlink"))]

	def renderHTTP_notFound(self, ctx):
		return self.renderHTTP(ctx)


class NotFoundPageWithFancyMessage(NotFoundPage):
	"""A NotFoundPage with a message that's taken from a piece of stan.
	"""
	def __init__(self, message):
		self.message = message
	
	def render_message(self, ctx, data):
		return ctx.tag[self.message]
	
	def render_rdlink(self, ctx, data):
		return ""


class OtherNotFoundPage(NotFoundPage):
	handles = base.NotFoundError


class RDNotFoundPage(NotFoundPage):
	handles = base.RDNotFound


class ForbiddenPage(ErrorPage):
	handles = svcs.ForbiddenURI
	status = 403
	titleMessage = "Forbidden"
	beforeMessage = "We're sorry, but the resource you requested is forbidden."
	afterMessage = T.div[
		T.p["This usually means you tried to use a renderer on a service"
			" that does not support it.  If you did not come up with the"
			" URL in question yourself, complain fiercely to the staff of ",
			T.invisible(render=T.directive("getconfig"))["[web]sitename"],
			"."],
		T.p(render=T.directive("rdlink"))]


class RedirectBase(ErrorPage):
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		# add request arguments if they are not already included in the
		# URL we're redirecting to:
		self.destURL = self.failure.value.dest
		if '?' not in self.destURL:
			args = urlparse.urlparse(request.uri).query
			if args:
				self.destURL = self.failure.value.dest+"?"+args
		request.setHeader("location", str(self.destURL))
		return ErrorPage.renderHTTP(self, ctx)
	
	def render_destLink(self, ctx, data):
		return ctx.tag(href=self.destURL)
	

class RedirectPage(RedirectBase):
	handles = svcs.WebRedirect
	status = 301
	titleMessage = "Moved Permanently"
	beforeMessage = ["The resource you requested is available from a ",
				T.a(render=T.directive("destLink"))[
			 		"different URL"],
				"."]
	afterMessage = T.p["You should not see this page -- either your browser or"
				" our site is broken.  Complain."]


class SeeOtherPage(RedirectBase):
	handles = svcs.SeeOther
	status = 303
	titleMessage = "See Other"
	beforeMessage = ["Please turn to a ",
				T.a(render=T.directive("destLink"))[
			 		"different URL"],
				" to go on."]
	afterMessage = T.p["You should not see this page -- either your browser or"
				" our site is broken.  Complain."]


class AuthenticatePage(ErrorPage):
	handles = svcs.Authenticate
	status = 401
	titleMessage = "Authentication Required"

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader('WWW-Authenticate', 
			'Basic realm="%s"'%str(self.failure.value.realm))
		return ErrorPage.renderHTTP(self, ctx)
	
	docFactory = svcs.loadSystemTemplate("unauth.html")


class BadMethodPage(ErrorPage):
	handles = svcs.BadMethod
	status = 405
	titleMessage = "Bad Method"
	beforeMessage = (
		"You just tried to use some HTTP method to access this resource"
		" that this resource does not support.  This probably means that"
		" this resource is for exclusive use for specialized clients.")
	afterMessage = T.p["You may find whatever you were really looking"
				" for by inspecting our ",
				T.a(href="/")["list of published services"],
				"."]


class NotAcceptable(ErrorPage):
	handles = base.DataError
	status = 406
	titleMessage = "Not Acceptable"
	beforeMessage = ("The server cannot generate the data you requested."
				"  The associated message is:")
	afterMessage = ""


class ErrorDisplay(ErrorPage):
	handles = base.ReportableError
	status = 500
	titleMessage = "Error"
	beforeMessage = ("A piece of code failed:")
	afterMessage = [T.p["Problems of this sort usually mean we considered"
		" the possibility of something like this happening; if the above"
		" doesn't give you sufficient hints to fix the problem, please"
		" complain to the address given below."],
		T.p(render=T.directive("hint"))]

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
	res = errorTemplate%(
		"<h1>Internal Error</h1><p>A(n)"
		" %s exception occurred.  The"
		" accompanying message is: '%s'</p>"
		"<p>If you are seeing this, it is always a bug in our code"
		" or the data descriptions, and we would be extremely grateful"
		" for a report at"
		" %s</p>"%(failure.value.__class__.__name__,
			common.escapeForHTML(failure.getErrorMessage()),
			config.getMeta("contact.email").getContent()))
	return res.encode("ascii", "ignore")


class InternalServerErrorPage(ErrorPage):
	"""A catch-all page served when no other error page seemed responsible.
	"""
	handles = base.Error  # meaningless, no isinstance done here
	status = 500
	titleMessage = "Uncaught Exception"
	beforeMessage = T.p["Your action has caused a(n) ",
				T.span(render=str, data=T.directive("excname")),
				" exception to occur.  As additional info, the failing code"
				" gave:"],
	afterMessage = T.p["This is always a bug in our software, and we would really"
				" be grateful for a report to the contact address below,"
				" preferably with a description of what you were trying to do,"
				" including any data pieces if applicable.  Thanks."]

	def data_excname(self, ctx, data):
		return self.failure.value.__class__.__name__

	def renderInnerException(self, ctx):
		"""called when rendering already has started.

		We don't know where we're sitting, so we try to break out as well
		as we can.
		"""
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)  # probably too late, but log still profits.
		data = _formatFailure(self.failure)
		if isinstance(data, unicode):
			data = data.encode("utf-8", "ignore")
		request.write(data)
		request.finishRequest(False)
		return ""

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		base.ui.notifyFailure(self.failure)
		base.ui.notifyInfo("Arguments of failed request: %s"%
			repr(request.args)[:2000])
		if getattr(self.failure.value, "hint", None):
			base.ui.notifyDebug("Exception hint: %s"%self.failure.value.hint)
		if getattr(request, "startedWriting", False):
			# exception happened while rendering a page.
			return self.renderInnerException(ctx)
		else:
			return ErrorPage.renderHTTP(self, ctx)



def _writePanicInfo(ctx, failure, secErr=None):
	"""write some panic-type stuff for failure and finishes the request.
	"""
	request = inevow.IRequest(ctx)
	request.setResponseCode(500)
	base.ui.notifyFailure(failure)
	base.ui.notifyInfo("Arguments were %s"%request.args)
		# write out some HTML and hope
		# for the best (it might well turn up in the middle of random output)
	request.write(
		"<html><head><title>Severe Error</title></head><body>")
	try:
		request.write(_formatFailure(failure))
	except:
		request.write("<h1>Ouch</h1><p>There has been an error that in"
			" addition breaks the toplevel error catching code.  Complain.</p>")
	base.ui.notifyError("Error while processing failure: %s"%secErr)
	request.write("</body></html>")
	request.finishRequest(False)


getErrorPage = utils.buildClassResolver(
	baseClass=ErrorPage, 
	objects=globals().values(),
	instances=False, 
	key=lambda obj: obj.handles, 
	default=InternalServerErrorPage)


def getDCErrorPage(error):
	"""returns stuff for root.ErrorCatchingNevowSite.
	"""
# This should be replaced by remembering DCExceptionHandler when
# some day we fix nevow.
	if error is None:
		error = failure.Failure()
	return getErrorPage(error.value.__class__)(error)


def _finishErrorProcessing(ctx, error):
	"""finishes ctx's request.
	"""
# this is also intended as a hook when something weird happens during
# error processing.  When everything's fine, you should end up here.
	request = inevow.IRequest(ctx)
	request.finishRequest(False)
	return ""


class DCExceptionHandler(object):
	"""The toplevel exception handler.
	"""
# Since something here is broken in nevow, this isn't really used.
	implements(inevow.ICanHandleException, inevow.ICanHandleNotFound)

	def renderHTTP_exception(self, ctx, error):
		try:
			handler = getDCErrorPage(error)
			return defer.maybeDeferred(handler.renderHTTP, ctx
				).addCallback(lambda ignored: _finishErrorProcessing(ctx, error)
				).addErrback(lambda secErr: _writePanicInfo(ctx, error, secErr))
		except:
			base.ui.notifyError("Error while handling %s error:"%error)
			_writePanicInfo(ctx, error)

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
