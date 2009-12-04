"""
Simple tests for TAP and environs.
"""

import os

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
	"""tests for working job submission and destruction.
	"""
# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		return uws.create(FakeRequest(args={"foo": "bar"}), "plainActions")

	def _deleteJob(self, job):
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
		job = self._createJob()
		self._assertJobCreated(job.jobid)
		self._deleteJob(job)
		self._assertJobDeleted(job.jobid)



if __name__=="__main__":
	testhelpers.main(PlainJobCreationTest)
