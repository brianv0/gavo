"""
A special renderer for testish things requring the full server to be up
"""

from nevow import inevow
from nevow import rend
from nevow import tags as T

from gavo.web import common
from gavo.web import streaming

class FooPage(rend.Page):
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["A page"],
		],
		T.body[
			T.p["If you see this, you had better know why."]]])


class StreamerPage(rend.Page):
	"""delivers senseless but possibly huge streams of data through streaming.py
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
	"""starts streaming out data and then crashes.
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/plain")
		def writeNoise(f):
			f.write("Here is some data.\n")
			raise Exception
		return streaming.streamOut(writeNoise, request)



class Tests(rend.Page):
	child_foo = FooPage()
	child_stream = StreamerPage()
	child_streamcrash = StreamerCrashPage()
	docFactory = common.doctypedStan(T.html[
		T.head[
			T.title["Wrong way"],
		],
		T.body[
			T.p["There is nothing here.  Trust me."]]])

