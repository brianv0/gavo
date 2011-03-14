"""
Streaming out large computed things using twisted and threads.
"""

import sys
import time
import threading
import traceback

from nevow import appserver

from twisted.internet import reactor
from twisted.internet.interfaces import IPushProducer
from twisted.python import threadable

from zope.interface import implements

from gavo import base
from gavo.formats import votablewrite


class DataStreamer(threading.Thread):
# This is nasty (because it's a thread) and not necessary most of the
# time since the source may be a file or something that could just yield
# now and then.  We should really, really fix this.
	"""is a twisted-enabled Thread to stream out large files produced
	on the fly.

	It is basically a pull producer.  To use it, construct it with
	a data source and a twisted request (or any IFinishableConsumer)
	If in a nevow resource, you should then return request.deferred.

	The data source simply is a function writeStreamTo taking one
	argument; this will be the DataStreamer.  You can call its write
	method to deliver data.  There's no need to close anything, just
	let your function return.

	writeStream will be run in a thread to avoid blocking the reactor.
	This thread will be halted if the consumer calls stopProducing.  Since
	python threads cannot be halted from outside, this works by the
	consumer's thread acquiring the writeLock and only releasing it
	on resumeProducing.
	"""

	implements(IPushProducer)

	chunkSize = 8192 # XXX TODO: Figure out a good chunk size for the
	                 # network stack

	def __init__(self, writeStreamTo, consumer):
		threading.Thread.__init__(self)
		self.writeStreamTo, self.consumer = writeStreamTo, consumer
		self.paused, self.killWriter = False, False
		consumer.registerProducer(self, True)
		self.setDaemon(True) # kill transfers on server restart

	def resumeProducing(self):
		self.paused = False

	def pauseProducing(self):
		self.paused = True

	def stopProducing(self):
		self.killWriter = True

	def realWrite(self, data):
		if isinstance(data, unicode): # we don't support encoding here, but
			data = str(data)            # don't break on accidental unicode.
		while self.paused:  # let's do a busy loop; twisted can handle
		                    # overflows, and locks become messy.
			time.sleep(0.1)
		return reactor.callFromThread(self.consumer.write, data)
	
	def write(self, data):
		if self.killWriter:
			raise IOError("Stop writing, please")
		if len(data)<self.chunkSize:
			self.realWrite(data)
		else:
			# would be cool if we could use buffers here, but twisted won't
			# let us.
			for offset in range(0, len(data), self.chunkSize):
				self.realWrite(data[offset:offset+self.chunkSize])

	def cleanup(self):
		# Must be callFromThread'ed
		self.join(0.01)
		self.consumer.unregisterProducer()
		self.consumer.finish()
		self.consumer = None

	def run(self):
		try:
			self.writeStreamTo(self)
		except:
			base.ui.notifyError("Exception while streaming"
				" (closing connection):\n")
		# All producing is done in the thread, so when no one's writing any
		# more, we should have delivered everything to the consumer
		reactor.callFromThread(self.cleanup)

	synchronized = ['resumeProducing', 'stopProducing']

threadable.synchronize(DataStreamer)


def streamOut(writeStreamTo, request):
	"""sets up the thread to have writeStreamTo write to request from
	a thread.

	For convenience, this function returns request.deferred, you
	you can write things like return streamOut(foo, request) in your
	renderHTTP (or analoguous).
	"""
	t = DataStreamer(writeStreamTo, request)
	t.start()
	return request.deferred


def streamVOTable(request, data, **contextOpts):
	"""streams out the payload of an SvcResult as a VOTable.
	"""
	def writeVOTable(outputFile):
		"""writes a VOTable representation of the SvcResult instance data
		to request.
		"""
		if "tablecoding" not in contextOpts:
			contextOpts["tablecoding"] = { 
				True: "td", False: "binary"}[data.queryMeta["tdEnc"]]
		if "version" not in contextOpts:
			contextOpts["version"] = data.queryMeta.get("VOTableVersion")
		try:
			tableMaker = votablewrite.writeAsVOTable(
				data.original, outputFile,
				ctx=votablewrite.VOTableContext(**contextOpts))
		except:
			base.ui.notifyError("Yikes -- error during VOTable render.\n")
			outputFile.write(">>>> INTERNAL ERROR, INVALID OUTPUT <<<<")
			return ""
	return streamOut(writeVOTable, request)
