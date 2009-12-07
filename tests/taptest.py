"""
Simple tests for TAP and environs.
"""

from __future__ import with_statement

import os
import Queue
import threading

from nevow.testutil import FakeRequest

from gavo import base
from gavo import rscdesc  # uws needs getRD
from gavo.protocols import uws

import testhelpers


class _PlainActions(uws.UWSActions):
	def __init__(self):
		uws.UWSActions.__init__(self, "plainActions", [
			(uws.PENDING, uws.QUEUED, "changeStatePlain"),
			(uws.QUEUED, uws.EXECUTING, "run"),
			(uws.EXECUTING, uws.COMPLETED, "changeStatePlain"),
			(uws.QUEUED, uws.ABORTED, "changeStatePlain"),
			(uws.EXECUTING, uws.ABORTED, "changeStatePlain"),
			(uws.COMPLETED, uws.DESTROYED, "changeStatePlain"),])
	
	def changeStatePlain(self, newState, uwsJob):
		uwsJob.state = newState

	def run(self, newState, uwsJob):
		uwsJob = uws.EXECUTING
		f = open(os.path.join(uwsJob.getWD(), "ran"))
		f.write("ran")
		f.close()
		uwsJob.changeState(uws.COMPLETED)


uws.registerActions(_PlainActions)


class _FakeJob(object):
	"""A scaffolding class for UWSJob.
	"""
	def __init__(self, state):
		self.state = state


class PlainActionsTest(testhelpers.VerboseTest):
	"""tests for uws actions.
	"""
	def setUp(self):
		self.actions = uws.getActions("plainActions")

	def testSimpleTransition(self):
		job = _FakeJob(object)
		self.actions.getTransition(uws.PENDING, uws.QUEUED)(uws.QUEUED, job)
		self.assertEqual(job.state, uws.QUEUED)
	
	def testFailingTransition(self):
		self.assertRaises(base.ValidationError,
			self.actions.getTransition, uws.PENDING, uws.COMPLETED)
	

class PlainJobCreationTest(testhelpers.VerboseTest):
	"""tests for working job creation and destruction.
	"""
# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		with uws.create(FakeRequest(args={"foo": "bar"}), "plainActions") as job:
			return job.jobid

	def _deleteJob(self, jobid):
		with uws.makeFromId(jobid) as job:
			job.delete()

	def _assertJobCreated(self, jobid):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobid=%(jobid)s", locals())
		querier.close()
		self.assertEqual(len(res), 1)
		job = uws.makeFromId(jobid)
		self.assertEqual(job.getParDict(), {"foo": "bar"})
		self.failUnless(os.path.exists(job.getWD()))

	def _assertJobDeleted(self, jobid):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobid=%(jobid)s", locals())
		querier.close()
		self.assertEqual(len(res), 0)
		self.assertRaises(base.NotFoundError, uws.makeFromId, jobid)
		self.failIf(os.path.exists(os.path.join(base.getConfig("uwsWD"), jobid)))

	def testBigAndUgly(self):
		jobid = self._createJob()
		self._assertJobCreated(jobid)
		self._deleteJob(jobid)
		self._assertJobDeleted(jobid)


class LockingTest(testhelpers.VerboseTest):
	"""tests for working impicit uws locking.
	"""
	def setUp(self):
		with uws.create(FakeRequest(), "plainActions") as job:
			self.jobid = job.jobid
		self.queue = Queue.Queue()
	
	def tearDown(self):
		with uws.makeFromId(self.jobid) as job:
			job.delete()

	def _blockingJob(self):
		print "starting blocking job"
		# this is started in a thread while self.jobid is held
		self.queue.put("Child started")
		q = base.SimpleQuerier()
		with uws.makeFromId(self.jobid) as job:
			self.queue.put("Job created")

	def testLocking(self):
		with uws.makeFromId(self.jobid) as job:
			child = threading.Thread(target=self._blockingJob)
			child.start()
			# see that child process has started but could not create the job
			self.assertEqual(self.queue.get(True, 1), "Child started")
			# make sure we time out on waiting for another sign of the child --
			# it should be blocking.
			self.assertRaises(Queue.Empty, self.queue.get, True, 0.05)
		# we've closed our handle on job, now child can run
		self.assertEqual(self.queue.get(True, 1), "Job created")

if __name__=="__main__":
	testhelpers.main(LockingTest)
