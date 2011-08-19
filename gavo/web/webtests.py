"""
A special renderer for testish things requring the full server to be up
"""

from nevow import inevow
from nevow import rend
from nevow import tags as T

from gavo.svcs import streaming
from gavo.web import common


class FooPage(rend.Page):
	"""is the most basic page conceivable.
	"""
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["A page"],
		],
		T.body[
			T.p["If you see this, you had better know why."]]])


class StreamerPage(rend.Page):
	"""is a page that delivers senseless but possibly huge streams of 
	data through streaming.py
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		dataSize = int(request.args.get("size", [300])[0])
		chunkSize = int(request.args.get("chunksize", [1000])[0])
		def writeNoise(f):
			for i in range(dataSize/chunkSize):
				f.write("x"*chunkSize)
			lastPayload = "1234567890"
			toSend = dataSize%chunkSize
			f.write(lastPayload*(toSend/10)+lastPayload[:toSend%10])
		return streaming.streamOut(writeNoise, request)


class StreamerCrashPage(rend.Page):
	"""is a page that starts streaming out data and then crashes.
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/plain")
		def writeNoise(f):
			f.buffer.chunkSize = 30
			f.write("Here is some data. (and some more, just to cause a flush)\n")
			raise Exception
		return streaming.streamOut(writeNoise, request)


class RenderCrashPage(rend.Page):
	"""is a page that crashes during render.
	"""
	def render_crash(self, ctx, data):
		raise Exception("Wanton crash")

	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["A page"],
		],
		T.body[
			T.p(render=T.directive("crash"))["You should not see this"]]])


class Tests(rend.Page):
	child_foo = FooPage()
	child_stream = StreamerPage()
	child_streamcrash = StreamerCrashPage()
	child_rendercrash = RenderCrashPage()
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["Wrong way"],
		],
		T.body[
			T.p["There is nothing here.  Trust me."]]])
