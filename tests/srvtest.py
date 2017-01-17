"""
Tests for the server infrastructure (like scheduled functions, notifications,
and such).
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

import calendar
import threading
import time

from gavo import base
from gavo import rscdesc
from gavo.base import cron
from gavo.base import events
from gavo.rscdef import executing


class _listWithMessage(list):
	"""Uh... I need this to have a place to keep... mails.
	"""
	lastMessage = None


class _Scheduler(object):
	"""helper class for _TestScheduleFunction.
	"""
	def __init__(self):
		self.curTimer = None
	
	def schedule(self, delay, callable):
		if self.curTimer is not None:
			if self.curTimer.isAlive():
				self.curTimer.cancel()
		self.curTimer = threading.Timer(delay/10., callable)
		self.curTimer.daemon = 1
		self.curTimer.start()

	def storeAMail(self, subject, message):
		self.lastMessage = subject+"\n"+message

	def finalize(self):
		if self.curTimer and self.curTimer.isAlive():
			self.curTimer.cancel()
		cron.sendMailToAdmin = self.oldMailFunction

	def wait(self):
		self.curTimer.join(1)


class _TestScheduleFunction(testhelpers.TestResource):
	def make(self, deps):
		s = _Scheduler()
		cron.registerScheduleFunction(s.schedule)
		s.oldMailFunction = cron.sendMailToAdmin
		cron.sendMailToAdmin = s.storeAMail
		return s

	def clean(self, scheduler):
		cron.sendMailToAdmin = scheduler.oldMailFunction
		cron.clearScheduleFunction()
		scheduler.finalize()


class CronTest(testhelpers.VerboseTest):
	resources = [("scheduler", _TestScheduleFunction())]

	def testDailyReschedulePre(self):
		job = cron.TimedJob([(None, None, 15, 20)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 10, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 15, 20))

	def testDailyReschedulePost(self):
		job = cron.TimedJob([(None, None, 15, 20)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (4, 15, 20))

	def testDailyRescheduleBetween(self):
		job = cron.TimedJob([(None, None, 15, 20), (None, None, 8, 45)], 
			"testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 12, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 15, 20))

	def testDailyRescheduleBeforeAll(self):
		job = cron.TimedJob([(None, None, 15, 20), (None, None, 8, 45)], 
			"testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 8, 45))

	def testMonthlyReschedule(self):
		job = cron.TimedJob([(8, None, 15, 20)], "testing#testing", None)

		t0 = calendar.timegm((1990, 12, 3, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[:3], (1990, 12, 8))

		t0 = calendar.timegm((1990, 12, 13, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[:3], (1991, 1, 8))

	def testWeeklyReschedule(self):
		job = cron.TimedJob([(None, 3, 15, 20)], "testing#testing", None)

		t0 = calendar.timegm((1990, 12, 26, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[:3], (1990, 12, 26))

		t0 = calendar.timegm((1990, 12, 28, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[:3], (1991, 1, 2))

	def testNegativeFirstSchedule(self):
		job = cron.IntervalJob(-3600, "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[3:6], (20, 30, 0))

	def testEveryFirstSchedule(self):
		job = cron.IntervalJob(3600, "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 20, 36))

	def testEveryReschedule(self):
		job = cron.IntervalJob(3600, "testing#testing", None)
		job.lastStarted = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t0 = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 21, 30))

	def testEveryInRD(self):
		rd = base.parseFromString(rscdesc.RD, r"""<resource schema="test">
			<macDef name="flog">hop</macDef>
			<execute title="seir" every="1">
				<job><code>
						rd.flum = "how\\n\flog"
				</code></job></execute></resource>""")
		self.scheduler.wait()
		self.assertEqual(rd.flum, "how\nhop")

	def testRescheduleUnschedules(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" every="1">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>""")
		self.assertEqual(len([j for _, j in cron._queue.jobs
			if j.name=="None#seir"]), 1)

		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" every="1">
				<job><code>
						rd.flum = 32
				</code></job></execute></resource>""")
		self.scheduler.wait()
		self.assertEqual(rd.flum, 32)
		self.assertEqual(len([j for _, j in cron._queue.jobs
			if j.name=="None#seir"]), 1)

	def testFailingSpawn(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" every="1">
				<job><code>
					execDef.spawn(["ls", "/does/not/exist"])
					execDef.ran = 1
				</code></job></execute></resource>""")
		self.scheduler.wait()
		for i in range(100):
			if hasattr(rd.jobs[0], "ran"):
				break
			time.sleep(0.005)
		else:
			raise AssertionError("spawned ls did not come around")
		self.failUnless("A process spawned by seir failed with 2"
			in self.scheduler.lastMessage)
		self.failUnless("Output of ['ls', '/does/not/exist']:"
			in self.scheduler.lastMessage)

	def testAtFromRDBad(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			'At [<resource schema="test">\\n\\...], (5, 17): \'25:78\' is'
				' not a valid value for at',
			base.parseFromString,
			(rscdesc.RD, """<resource schema="test">
			<execute title="seir" at="25:78">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>"""))

	def testAtFromRDAlsoBad(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			'At [<resource schema="test">\\n\\...], (5, 17): \'m31 22:18\' is'
				' not a valid value for at',
			base.parseFromString,
			(rscdesc.RD, """<resource schema="test">
			<execute title="seir" at="m31 22:18">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>"""))

	def testAtFromRDGood(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" at="16:28">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>""")
		self.assertEqual(rd.jobs[0].parsedAt[0], (None, None, 16, 28))
		self.assertEqual(len(rd.jobs[0].parsedAt), 1)
		self.scheduler.wait()
		self.assertEqual(time.gmtime([j for _, j in cron._queue.jobs 
			if j.name=="None#seir"][0].getNextWakeupTime(time.time()))[3:5],
			(16, 28))

	def testAtFromRDWithMonth(self):
		# this is a somewhat non-deterministic test...
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" at="m6 16:28, w3 10:20">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>""")
		self.assertEqual(rd.jobs[0].parsedAt[0], (6, None, 16, 28))
		self.assertEqual(rd.jobs[0].parsedAt[1], (None, 3, 10, 20))
		self.assertEqual(len(rd.jobs[0].parsedAt), 2)

		scheduledAt, job = [item for item in cron._queue.jobs
			if item[1].name=="None#seir"][0]
		tup = time.gmtime(scheduledAt)
		self.assertTrue(tup.tm_wday==2 or tup.tm_mday==6,
			"seir not scheduled on Wednesday or 6th of month: %s"%repr(tup))
		self.assertTrue(scheduledAt>=time.time(),
			"seir in the past")


class Tell(Exception):
	"""is raised by some listeners to show they've been called.
	"""


class EventDispatcherTest(testhelpers.VerboseTest):
	def testNoNotifications(self):
		"""tests for the various notifications not bombing out by themselves.
		"""
		ed = events.EventDispatcher()
		ed.notifyError("Something")

	def testNotifyError(self):
		def callback(ex):
			raise Exception(ex)
		ed = events.EventDispatcher()
		ed.subscribeError(callback)
		fooMsg = "WumpMessage"
		try:
			ed.notifyError(fooMsg)
		except Exception, foundEx:
			self.assertEqual(fooMsg, foundEx.args[0])

	def testUnsubscribe(self):
		res = []
		def callback(arg):
			res.append(arg)
		ed = events.EventDispatcher()
		ed.subscribeInfo(callback)
		ed.notifyInfo("a")
		ed.unsubscribeInfo(callback)
		ed.notifyInfo("b")
		self.assertEqual(res, ["a"])

	def testObserver(self):
		ed = events.EventDispatcher()
		class Observer(base.ObserverBase):
			@base.listensTo("NewSource")
			def gotNewSource(self, sourceName):
				raise Tell(sourceName)
		o = Observer(ed)
		ex = None
		try:
			ed.notifyNewSource("abc")
		except Tell, ex:
			pass
		self.assertEqual(ex.args[0], "abc")
		try:
			ed.notifyNewSource(range(57))
		except Tell, ex:
			pass
		self.assertEqual(ex.args[0], 
			'[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41...')


if __name__=="__main__":
	testhelpers.main(CronTest)
