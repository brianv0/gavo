"""
Simple tests for TAP and environs.

All these tests really stink because TAP isn't really a good match for the
basically stateless unit tests that are executed in an arbitrary order.

How do other people test such stuff?
"""

from __future__ import with_statement

import os
import Queue
import time
import threading

from nevow import inevow
from nevow.testutil import FakeRequest
from twisted.python.components import registerAdapter

from gavo import base
from gavo import rscdesc  # uws needs getRD
from gavo.protocols import tap
from gavo.protocols import uws
from gavo.web import taprender

import testhelpers
import adqltest


class _PlainActions(uws.UWSActions):
	def __init__(self):
		uws.UWSActions.__init__(self, "plainActions", [
			(uws.PENDING, uws.QUEUED, "noOp"),
			(uws.QUEUED, uws.EXECUTING, "run"),
			(uws.EXECUTING, uws.COMPLETED, "noOp"),
			(uws.QUEUED, uws.ABORTED, "noOp"),
			(uws.EXECUTING, uws.ABORTED, "noOp"),
			(uws.COMPLETED, uws.DESTROYED, "noOp"),])
	
	def run(self, newState, uwsJob, ignored):
		uwsJob = uws.EXECUTING
		f = open(os.path.join(uwsJob.getWD(), "ran"))
		f.write("ran")
		f.close()
		uwsJob.changeToPhase(uws.COMPLETED)


uws.registerActions(_PlainActions)


class _FakeJob(object):
	"""A scaffolding class for UWSJob.
	"""
	def __init__(self, phase):
		self.phase = phase


class _FakeContext(object):
	"""A scaffolding class for testing renderers.
	"""
	def __init__(self, **kwargs):
		self.request = FakeRequest(args=kwargs)
		self.args = kwargs

registerAdapter(lambda ctx: ctx.request, _FakeContext, inevow.IRequest)


class PlainActionsTest(testhelpers.VerboseTest):
	"""tests for uws actions.
	"""
	def setUp(self):
		self.actions = uws.getActions("plainActions")

	def testSimpleTransition(self):
		job = _FakeJob(object)
		self.actions.getTransition(uws.PENDING, uws.QUEUED)(uws.QUEUED, job, None)
		self.assertEqual(job.phase, uws.QUEUED)
	
	def testFailingTransition(self):
		self.assertRaises(base.ValidationError,
			self.actions.getTransition, uws.PENDING, uws.COMPLETED)
	

class PlainJobCreationTest(testhelpers.VerboseTest):
	"""tests for working job creation and destruction.
	"""
# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		with uws.createFromRequest(FakeRequest(args={"foo": "bar"}), 
				"plainActions") as job:
			return job.jobId

	def _deleteJob(self, jobId):
		with uws.makeFromId(jobId) as job:
			job.delete()

	def _assertJobCreated(self, jobId):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobId=%(jobId)s", locals())
		querier.close()
		self.assertEqual(len(res), 1)
		job = uws.makeFromId(jobId)
		self.assertEqual(job.getParDict(), {"foo": "bar"})
		self.failUnless(os.path.exists(job.getWD()))

	def _assertJobDeleted(self, jobId):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobId=%(jobId)s", locals())
		querier.close()
		self.assertEqual(len(res), 0)
		self.assertRaises(base.NotFoundError, uws.makeFromId, jobId)
		self.failIf(os.path.exists(os.path.join(base.getConfig("uwsWD"), jobId)))

	def testBigAndUgly(self):
		jobId = self._createJob()
		self._assertJobCreated(jobId)
		self._deleteJob(jobId)
		self._assertJobDeleted(jobId)


class UWSMiscTest(testhelpers.VerboseTest):
	"""uws tests not fitting anywhere else.
	"""
	def testBadActionsRaise(self):
		with uws.create(actions="Wullu_ulla99") as job:
			try:
				self.assertRaises(base.NotFoundError, 
					job.changeToPhase, uws.EXECUTING)
			finally:
				job.delete()


class LockingTest(testhelpers.VerboseTest):
	"""tests for working impicit uws locking.
	"""
	def setUp(self):
		with uws.create(actions="plainActions") as job:
			self.jobId = job.jobId
		self.queue = Queue.Queue()
	
	def tearDown(self):
		with uws.makeFromId(self.jobId) as job:
			job.delete()

	def _blockingJob(self):
		# this is started in a thread while self.jobId is held
		self.queue.put("Child started")
		q = base.SimpleQuerier()
		with uws.makeFromId(self.jobId) as job:
			self.queue.put("Job created")

	def testLocking(self):
		with uws.makeFromId(self.jobId) as job:
			child = threading.Thread(target=self._blockingJob)
			child.start()
			# see that child process has started but could not create the job
			self.assertEqual(self.queue.get(True, 1), "Child started")
			# make sure we time out on waiting for another sign of the child --
			# it should be blocking.
			self.assertRaises(Queue.Empty, self.queue.get, True, 0.05)
		# we've closed our handle on job, now child can run
		self.assertEqual(self.queue.get(True, 1), "Job created")


class SimpleRunnerTest(testhelpers.VerboseTest):
	"""tests various taprunner scenarios.
	"""
	resources = [("ds", adqltest.adqlTestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.tableName = self.ds.tables["adql"].tableDef.getQName()

	def testSimpleJob(self):
		jobId = None
		try:
			with uws.create(args={
					"QUERY": "SELECT * FROM %s"%self.tableName,
					"REQUEST": "doQuery",
					"LANG": "ADQL"}) as job:
				jobId = job.jobId
				self.assertEqual(job.phase, uws.PENDING)
				job.changeToPhase(uws.EXECUTING, None)

			# let things run, but bail out if nothing happens 
			for i in range(50):
				time.sleep(0.1)
				with uws.makeFromId(jobId) as job:
					if job.phase!=uws.EXECUTING:
						break
			else:
				raise AssertionError("Job does not finish.  Your machine cannot be"
					" *that* slow?")

			with uws.makeFromId(jobId) as job:
				self.assertEqual(job.phase, uws.COMPLETED)
				result = open(job.getResultName()).read()

		finally:
			if jobId is not None:
				with uws.makeFromId(jobId) as job:
					job.delete()
		self.failUnless('xmlns="http://www.ivoa.net/xml/VOTable/' in result)


if __name__=="__main__":
	testhelpers.main(SimpleRunnerTest)
