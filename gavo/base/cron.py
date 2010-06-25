"""
A cron-like facility to regularly run some funcitons.

This works by calling cron.every(seconds, callable) at any time.  callable
will then be called rougly every seconds in some way.  callable must
be thread-safe since it will, in general, be run in a thread.

To make this happen, the running program has to call 
registerScheduler(schedulerFunction).  Only the first registration is relevant.
The schedulerFunction has the signature sf(delay, callable) and has to
arrange for callable to be called delay seconds in the future.  In reality,
that's just reactor.callLater registred by the web server.
"""

from __future__ import with_statement

import heapq
import time
import threading


class Job(object):
	"""A cron-like job.
	"""
	def __init__(self, interval, callable):
		self.interval, self.callable = interval, callable

	def run(self):
		try:
			self.callable()
		except Exception, ex:
			import traceback # XXX TODO: make a proper log once we have utils.getUI
			traceback.print_exc()


class Queue(object):
	"""A cron-job queue.

	This is really a heap sorted by the time the job is next supposed to run.
	"""
	def __init__(self):
		self.jobs = []
		self.lock = threading.Lock()
		self.scheduleFunction = None

	def _scheduleJob(self, job):
		with self.lock:
			heapq.heappush(self.jobs, (time.time(), job))

	def _scheduleJobNext(self, job):
		with self.lock:
			heapq.heappush(self.jobs, (time.time()+job.interval, job))

	def _scheduleNext(self):
		with self.lock:
			nextTime, job = heapq.heappop(self.jobs)
		def runCron():
			try:
				job.run()
			finally:
				self._scheduleJobNext(job)
				self._scheduleNext()
		self.scheduleFunction(max(0, nextTime-time.time()), runCron)

	def every(self, seconds, callable):
		self._scheduleJob(Job(seconds, callable))

	def registerScheduleFunction(self, scheduleFunction):
		if self.scheduleFunction is None:
			self.scheduleFunction = scheduleFunction
			self._scheduleNext()


_queue = Queue()
every = _queue.every
registerScheduleFunction = _queue.registerScheduleFunction
