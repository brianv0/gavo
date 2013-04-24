"""
Tests for the server infrastructure (like scheduled functions, notifications,
and such).
"""

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


class _TestScheduleFunction(testhelpers.TestResource):
	def make(self, deps):
		spawnedThreads = _listWithMessage()

		def schedule(delay, callable):
			t = threading.Timer(delay/10., callable)
			t.daemon = 1
			t.start()
			spawnedThreads.append(t)

		cron.registerScheduleFunction(schedule)

		def storeAMail(subject, message):
			spawnedThreads.lastMessage = subject+"\n"+message

		self.oldMailFunction = cron.sendMailToAdmin
		cron.sendMailToAdmin = storeAMail

		return spawnedThreads
	
	def clean(self, spawnedThreads):
		cron.clearScheduleFunction()
		for t in spawnedThreads:
			if t.isAlive():
				try:
					t.cancel()
				except:
					import traceback
					traceback.print_exc()
			t.join(0.001)
		cron.sendMailToAdmin = self.oldMailFunction


class CronTest(testhelpers.VerboseTest):
	resources = [("threads", _TestScheduleFunction())]

	def testDailyReschedulePre(self):
		job = cron.DailyJob([(15, 20)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 10, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 15, 20))

	def testDailyReschedulePost(self):
		job = cron.DailyJob([(15, 20)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 20, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (4, 15, 20))

	def testDailyRescheduleBetween(self):
		job = cron.DailyJob([(15, 20), (8, 45)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 12, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 15, 20))

	def testDailyRescheduleBeforeAll(self):
		job = cron.DailyJob([(15, 20), (8, 45)], "testing#testing", None)
		t0 = calendar.timegm((1990, 5, 3, 0, 30, 0, -1, -1, -1))
		t1 = time.gmtime(job.getNextWakeupTime(t0))
		self.assertEqual(t1[2:5], (3, 8, 45))

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
		self.threads[-1].join(1)
		self.failIf(self.threads[-1].isAlive())
		del self.threads[-1]
		self.assertEqual(rd.flum, "how\nhop")

	def testRescheduleUnschedules(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" every="1">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>""")
		self.assertEqual(len([j for _, j in cron._queue.jobs
			if j.name=="None#seir"]), 1)
		self.threads[-1].join(0.2)
		self.failIf(self.threads[-1].isAlive())
		del self.threads[-1]

		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" every="1">
				<job><code>
						rd.flum = 32
				</code></job></execute></resource>""")
		self.threads[-1].join(0.2)
		self.failIf(self.threads[-1].isAlive())
		del self.threads[-1]
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
		self.threads[-1].join()
		self.failIf(self.threads[-1].isAlive())
		del self.threads[-1]
		for i in range(100):
			if hasattr(rd.jobs[0], "ran"):
				break
			time.sleep(0.005)
		else:
			raise AssertionError("spawned ls did not come around")
		self.failUnless("A process spawned by seir failed with 2"
			in self.threads.lastMessage)
		self.failUnless("Output of ['ls', '/does/not/exist']:"
			in self.threads.lastMessage)

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

	def testAtFromRDGood(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<execute title="seir" at="16:28">
				<job><code>
						rd.flum = 31
				</code></job></execute></resource>""")
		self.assertEqual(rd.jobs[0].parsedAt[0], (16, 28))
		self.assertEqual(len(rd.jobs[0].parsedAt), 1)
		self.threads[-1].cancel()
		self.threads[-1].join(0.01)
		self.failIf(self.threads[-1].isAlive())
		self.assertEqual(time.gmtime([j for _, j in cron._queue.jobs 
			if j.name=="None#seir"][0].getNextWakeupTime(time.time()))[3:5],
			(16, 28))


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
			ed.notifyNewSource(range(30))
		except Tell, ex:
			pass
		self.assertEqual(ex.args[0], '[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1')


if __name__=="__main__":
	testhelpers.main(CronTest)
