"""
A renderer for TAP, both sync and async.
"""

from nevow import inevow
from nevow import rend

from gavo.web import common
from gavo.web import grend
from gavo.votable import V

TAP_VERSION = "1.0"


class ErrorResource(rend.Page):
	def __init__(self, errMsg):
		self.errMsg = errMsg

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		doc = V.VOTABLE[
			V.INFO(name="QUERY_STATUS", value="ERROR")[
				self.errMsg]]
		return doc.render()


def getSyncResource(ctx, segments):
	pass
	

class TAPRenderer(grend.ServiceBasedRenderer):
	"""A renderer for the synchronous version of TAP.

	Basically, this just dispatches to the sync and async resources.
	"""
	name = "tap"

	def locateChild(self, ctx, segments):
		if ctx.args.get("VERSION", "TAP_VERSION"):
			return ErrorResource("Version mismatch; this service only supports"
				" TAP version %s."%TAP_VERSION), ()
		if segments:
			if segments[0]=='sync':
				return getSyncResource(ctx, segments[1:]), ()
			elif segments[0]=='async':
				return getAsyncResource(ctx, segments[1:]), ()
		raise UnknownURI("Bad TAP path %s"%"/".join(segments))
