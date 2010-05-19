"""
A renderer that queries a single field in a service.
"""

from nevow import inevow
from nevow import tags as T, entities as E
from twisted.internet import defer

from gavo import svcs
from gavo.web import common
from gavo.web import grend


class QPRenderer(grend.HTMLResultRenderMixin, 
		grend.ServiceBasedRenderer):
	"""The Query Path renderer extracts a query argument from the query path.

	Basically, whatever segments are left after the path to the renderer
	are taken and fed into the service.  The service must cooperate by
	setting a queryField property which is the key the parameter is assigned
	to.

	QPRenderers cannot do forms, of course.
	"""
	name = "qp"
	queryValue = None

	@classmethod
	def isCacheable(self, segments, request):
		return False  # That's the default, but let's be sure here...

	def renderHTTP(self, ctx):
		if not self.queryValue:
			raise svcs.UnknownURI("This page is a root page for a"
				" query-based service.  You have to give a valid value in the"
				" path.")
		data = {self.service.getProperty("queryField"): self.queryValue}
		return self.runServiceWithContext(data, ctx
			).addCallback(self._formatOutput, ctx
			).addErrback(self._handleError, ctx)
	
	def _formatOutput(self, res, ctx):
		nMatched = res.queryMeta.get("Matched", 0)
		if nMatched==0:
			raise svcs.UnknownURI("No record matching %s."%(
				self.queryValue))
		elif nMatched==1:
			self.customTemplate = self.getTemplate("resultline")
		else:
			self.customTemplate = self.getTemplate("resulttable")
		self.result = res
		return defer.maybeDeferred(super(QPRenderer, self).renderHTTP, ctx
			).addErrback(self._handleError, ctx)

	def _handleError(self, failure, ctx):
		# all errors are translated to 404s
		failure.printTraceback()
		raise svcs.UnknownURI("The query initiated by your URL failed,"
			" yielding a message '%s'."%failure.getErrorMessage())

	def locateChild(self, ctx, segments):
		# if we're here, we are the responsible resource and just stuff
		# the remaining segments into the query value
		self.queryValue = "/".join(segments)
		return self, ()

	def getTemplate(self, resultFormat):
		return common.doctypedStan(
			T.html[
				T.head(render=T.directive("commonhead"))[
					T.title(render=T.directive("meta"))['title'],],
				T.body(render=T.directive("withsidebar"))[
					T.h1(render=T.directive("meta"))['title'],
					T.div(class_="result", data=T.directive("result")) [
						T.invisible(render=T.directive(resultFormat))]]])

svcs.registerRenderer(QPRenderer)
