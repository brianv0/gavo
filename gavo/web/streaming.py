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
from gavo import utils
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
		self.paused, self.exceptionToRaise = False, None
		consumer.registerProducer(self, True)
		self.setDaemon(True) # kill transfers on server restart

	def resumeProducing(self):
		self.paused = False

	def pauseProducing(self):
		self.paused = True

	def stopProducing(self):
		self.exceptionToRaise = IOError("Stop writing, please")

	def realWrite(self, data):
		if isinstance(data, unicode): # we don't support encoding here, but
			data = str(data)            # don't break on accidental unicode.
		while self.paused:  # let's do a busy loop; twisted can handle
		                    # overflows, and waiting on a semaphore becomes
												# technically messy here (why?)
			time.sleep(0.1)
		return reactor.callFromThread(self._writeToConsumer, data)
	
	def _writeToConsumer(self, data):
		# We want to catch errors occurring during writes.  This method
		# is called from the reactor (main) thread.
		# We assign to the exceptionToRaise instance variable, and this
		# races with stopProducing.  This race is harmless, though, since
		# in any case writing stops, and the exception raised is of secondary
		# importance.
		try:
			self.consumer.write(data)
		except IOError, ex:
			self.exceptionToRaise = ex
		except Exception, ex:
			base.ui.notifyError("Exception during streamed write.")
			self.exceptionToRaise = ex
	
	def write(self, data):
		if self.exceptionToRaise:
			raise self.exceptionToRaise
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
			try:
				self.writeStreamTo(self)
			except IOError:
				# I/O errors are most likely not our fault, and I don't want
				# to make matters worse by pushing any dumps into a line
				# that's probably closed anyway.
				base.ui.notifyError("I/O Error while streaming:")
			except:
				base.ui.notifyError("Exception while streaming"
					" (closing connection):\n")
				self.consumer.write("\n\n\nXXXXXX Internal error in DaCHS software.\n"
					"If you are seeing this, please notify gavo@ari.uni-heidelberg.de\n"
					"with as many details (like a URL) as possible.\n"
					"Also, the following traceback may help people there figure out\n"
					"the problem:\n"+
					utils.getTracebackAsString())
		# All producing is done in the thread, so when no one's writing any
		# more, we should have delivered everything to the consumer
		finally:
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
		tableMaker = votablewrite.writeAsVOTable(
			data.original, outputFile,
			ctx=votablewrite.VOTableContext(**contextOpts))
	return streamOut(writeVOTable, request)
