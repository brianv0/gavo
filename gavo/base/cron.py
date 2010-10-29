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
		self._scheduleWakeup()

	def _scheduleJobNext(self, job):
		with self.lock:
			heapq.heappush(self.jobs, (time.time()+job.interval, job))
		self._scheduleWakeup()

	def _runNextJob(self):
		try:
			with self.lock:
				jobTime, job = heapq.heappop(self.jobs)
				if jobTime>time.time()+60:
					# spurious wakeup, forget about it
					heapq.heappush(jobTime, job)
				else:
					job.run()
		finally:
			self._scheduleJobNext(job)
	
	def _scheduleWakeup(self):
		if not self.jobs:  
			# Nothing to run; we'll be called when someone schedules something
			return
		nextWakeup = self.jobs[0][0]
		if self.scheduleFunction is not None:
			self.scheduleFunction(max(0, nextWakeup-time.time()), self._runNextJob)

	def every(self, seconds, callable):
		self._scheduleJob(Job(seconds, callable))

	def registerScheduleFunction(self, scheduleFunction):
		if self.scheduleFunction is None:
			self.scheduleFunction = scheduleFunction
			self._scheduleWakeup()


_queue = Queue()
every = _queue.every
registerScheduleFunction = _queue.registerScheduleFunction
