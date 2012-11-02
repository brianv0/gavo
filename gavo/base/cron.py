"""
A cron-like facility to regularly run some functions.

Most of the apparatus in here is not really for user consumption.
There's a singleton of the queue created below, and the methods of that
singleton are exposed as module-level functions.

To make the jobs actually execute, the running program has to call 
registerScheduler(schedulerFunction).  Only the first registration is relevant.
The schedulerFunction has the signature sf(delay, callable) and has to
arrange for callable to be called delay seconds in the future.  In reality,
that's just reactor.callLater registred by the web server.
"""

from __future__ import with_statement

import calendar
import heapq
import os
import subprocess
import time
import threading

from gavo import utils
from gavo.base import config


def sendMailToAdmin(subject, message):
	"""tries to send a mail to the configured administrator.

	This relies on a functional mail infrastructure on the local host.
	"""
	if not config.get("maintainerAddress"):
		utils.sendUIEvent("Error", "Wanted to send mail with subject '%s', but no"
			" maintainerAddress is given"%subject)
		return

	pipe = subprocess.Popen(config.get("sendmail"), shell=True,
		stdin=subprocess.PIPE)
	pipe.stdin.write("\n".join(["To: "+config.get("maintainerAddress"),
		"Subject: "+subject,
		"From: DaCHS server <%s>"%config.get("maintainerAddress"),
		"Content-Type: text/plain",
		"",
		utils.safe_str(message)]))
	pipe.stdin.close()

	if pipe.wait():
		utils.sendUIEvent("Error", "Wanted to send mail with subject"
			"'%s', but sendmail returned an error message"
			" (check the [general]sendmail setting)."%subject)


class AbstractJob(object):
	"""A job run in a queue.
	"""
	# here, Queue keeps track of the last time this job was started.
	lastStarted = None

	def reportCronFailure(self, message):
		sendMailToAdmin("DaCHS job failed",
			"\n".join([
				"DaCHS job %s failed"%str(self),
				"\nDetails:\n",
				message]))

	def run(self):
		"""runs callable under somewhat reliable circumstances.
		"""
		try:
			self.callable()
		except Exception, ex:
			utils.sendUIEvent("Error",
				"Failure in timed job.  Trying to send maintainer a mail.")
			self.reportCronFailure("".join(
				traceback.format_exception(*sys.exc_info())))

	def getNextWakeupTime(self, curTime):
		"""returns the UTC unix epoch seconds when this job is next
		supposed to run, starting from curTime.
		"""
		raise NotImplementedError(
			"You must override AbstractJob.getNextWakeupTime()")


class IntervalJob(AbstractJob):
	"""A job that's executed roughly every interval seconds.
	"""
	def __init__(self, interval, callable):
		self.interval, self.callable = interval, callable

	def getNextWakeupTime(self, curTime):
		if lastStarted is None:
			return curTime
		else:
			return curTime+self.interval


class DailyJob(AbstractJob):
	"""A job that's run roughly daily at a given time UTC.
	"""
	def __init__(self, hour, minute, callable):
		self.hour, self.minute = hour, minute
		self.callable = callable

	def getNextWakeupTime(self, curTime):
		# dumb strategy: get parts, replace hour and minute, and if it's
		# in the past, add a day
		curTup = time.gmtime(curTime)
		wakeupTime = calendar.timegm(
			curTup[:3]+(self.hour, self.minute)+curTup[5:])
		if wakeupTime<curTime:
			wakeupTime += 86400
		return wakeupTime


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
			heapq.heappush(self.jobs, (job.getNextWakeupTime(time.time()), job))
		self._scheduleWakeup()

	def _runNextJob(self):
		try:
			with self.lock:
				jobTime, job = heapq.heappop(self.jobs)
				if jobTime>time.time()+60:
					# spurious wakeup, forget about it
					heapq.heappush(jobTime, job)
				else:
					job.lastStarted = time.time()
					job.run()
		finally:
			self._scheduleJob(job)
	
	def _scheduleWakeup(self):
		if not self.jobs:  
			# Nothing to run; we'll be called when someone schedules something
			return
		nextWakeup = self.jobs[0][0]
		if self.scheduleFunction is not None:
			self.scheduleFunction(max(0, nextWakeup-time.time()), self._runNextJob)

	def runEvery(self, seconds, callable):
		self._scheduleJob(IntervalJob(seconds, callable))

	def repeatAt(self, hours, minutes, callable):
		self._scheduleJob(DailyJob(seconds, callable))

	def registerScheduleFunction(self, scheduleFunction):
		if self.scheduleFunction is None:
			self.scheduleFunction = scheduleFunction
			self._scheduleWakeup()


_queue = Queue()
runEvery = _queue.runEvery
repeatAt = _queue.repeatAt
registerScheduleFunction = _queue.registerScheduleFunction
