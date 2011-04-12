"""
Simple tests for TAP and environs.

All these tests really stink because TAP isn't really a good match for the
basically stateless unit tests that are executed in an arbitrary order.

There's more TAP/UWS related tests in test_tap.py; these require a
running reactor and are based on trial.
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
from gavo import votable
from gavo.helpers import testhelpers
from gavo.helpers import testtricks
from gavo.protocols import tap
from gavo.protocols import taprunner
from gavo.protocols import uws
from gavo.protocols import uwsactions
from gavo.registry import capabilities
from gavo.web import taprender

import adqltest
import tresc



class TAPFakeRequest(FakeRequest):
# The UWS machinery wants its arguments in scalars, hence this class.
	def __init__(self, *args, **kwargs):
		FakeRequest.__init__(self, *args, **kwargs)
		self.scalars = self.args


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


class _FakeJob(uws.UWSJob):
	"""A scaffolding class for UWSJob.
	"""
	def __init__(self, phase):
		self.phase = phase
		self.actions = "plainActions"
	
	def __del__(self):
		pass


class _FakeContext(object):
	"""A scaffolding class for testing renderers.
	"""
	def __init__(self, **kwargs):
		self.request = TAPFakeRequest(args=kwargs)
		self.args = kwargs

registerAdapter(lambda ctx: ctx.request, _FakeContext, inevow.IRequest)


class PlainActionsTest(testhelpers.VerboseTest):
	"""tests for uws actions.
	"""
	def setUp(self):
		self.actions = uws.getActions("plainActions")

	def testSimpleTransition(self):
		job = _FakeJob(uws.PENDING)
		self.actions.getTransition(uws.PENDING, uws.QUEUED)(uws.QUEUED, job, None)
		self.assertEqual(job.phase, uws.QUEUED)
	
	def testFailingTransition(self):
		self.assertRaises(base.ValidationError,
			self.actions.getTransition, uws.PENDING, uws.COMPLETED)

	def testNoEndstateActions(self):
		job = _FakeJob(object)
		job.phase = uws.COMPLETED
		job.changeToPhase(uws.ERROR)
		self.assertEqual(job.phase, uws.COMPLETED)

	def testNullActionIgnored(self):
		job = _FakeJob(object)
		job.phase = uws.QUEUED
		job.changeToPhase(uws.QUEUED)
		self.assertEqual(job.phase, uws.QUEUED)



class PlainJobCreationTest(testhelpers.VerboseTest):
	"""tests for working job creation and destruction.
	"""
	resources = [("conn", tresc.dbConnection)]

# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		with uws.UWSJob.createFromRequest(TAPFakeRequest(args={"foo": "bar"}), 
				"plainActions") as job:
			return job.jobId

	def _deleteJob(self, jobId):
		with uws.UWSJob.makeFromId(jobId) as job:
			job.delete()

	def _assertJobCreated(self, jobId):
		with base.SimpleQuerier(connection=self.conn) as querier:
			res = list(querier.query("SELECT quote FROM uws.jobs WHERE"
				" jobId=%(jobId)s", locals()))
		self.assertEqual(len(res), 1)
		job = uws.UWSJob.makeFromId(jobId)
		self.assertEqual(job.getParameter("foo"), "bar")
		self.failUnless(os.path.exists(job.getWD()))

	def _assertJobDeleted(self, jobId):
		with  base.SimpleQuerier(connection=self.conn) as querier:
			res = list(querier.query("SELECT quote FROM uws.jobs WHERE"
				" jobId=%(jobId)s", locals()))
		self.assertEqual(len(res), 0)
		self.assertRaises(base.NotFoundError, uws.UWSJob.makeFromId, jobId)
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
		with uws.UWSJob.create(actions="Wullu_ulla99") as job:
			try:
				self.assertRaises(base.NotFoundError, 
					job.changeToPhase, uws.EXECUTING)
			finally:
				job.delete()


class _UWSJobResource(testhelpers.TestResource):
# just a UWS job.  Don't manipulate it.
	def make(self, ignored):
		with uws.UWSJob.create(actions="plainActions") as job:
			self.jobId = job.jobId
			return self.jobId
	
	def clean(self, ignored):
		with uws.UWSJob.makeFromId(self.jobId) as job:
			job.delete()


class LockingTest(testhelpers.VerboseTest):
	"""tests for working impicit uws locking.
	"""
	resources = [("jobId", _UWSJobResource())]

	def testLocking(self):
		queue = Queue.Queue()
		def blockingJob():
			# this is started in a thread while self.jobId is held
			queue.put("Child started")
			with uws.UWSJob.makeFromId(self.jobId) as job:
				queue.put("Job created")

		with uws.UWSJob.makeFromId(self.jobId) as job:
			child = threading.Thread(target=blockingJob)
			child.start()
			# see that child process has started but could not create the job
			self.assertEqual(queue.get(True, 1), "Child started")
			# make sure we time out on waiting for another sign of the child --
			# it should be blocking.
			self.assertRaises(Queue.Empty, queue.get, True, 0.05)
		# we've closed our handle on job, now child can run
		self.assertEqual(queue.get(True, 1), "Job created")

	def testTimesOut(self):
		with uws.UWSJob.makeFromId(self.jobId) as job:
			self.assertRaisesWithMsg(base.ReportableError,
				"Could not access the jobs table. This probably means there"
				" is a stale lock on it.  Please notify the service operators.",
				uws.UWSJob.makeFromId,
				(self.jobId,), timeout=0.01)

	def testIndexDoesNotBlock(self):
		with uws.UWSJob.makeFromId(self.jobId) as job:
			self.failUnless("uws:jobs" in uwsactions.getJobList())

	def testGetPhaseDoesNotBlock(self):
		req = TAPFakeRequest()
		with uws.UWSJob.makeFromId(self.jobId) as job:
			self.assertEqual(uwsactions.doJobAction(req, (self.jobId, "phase")),
				"PENDING")

	def testPostPhaseDoesBlock(self):
		req = TAPFakeRequest(args={"PHASE": "RUN"})
		req.method = "POST"
		uwsactions.PhaseAction.timeout = 0.05
		with uws.UWSJob.makeFromId(self.jobId) as job:
			self.assertRaisesWithMsg(base.ReportableError,
				"Could not access the jobs table. This probably means"
				" there is a stale lock on it.  Please notify the service operators.",
				uwsactions.doJobAction,
				(req, (self.jobId, "phase")))


class SimpleRunnerTest(testhelpers.VerboseTest):
	"""tests various taprunner scenarios.
	"""
	resources = [("ds", adqltest.adqlTestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.tableName = self.ds.tables["adql"].tableDef.getQName()
	
	def _getQueryResult(self, query):
		# returns a votable.simple result for query.
		with tap.TAPJob.create(args={
				"QUERY": query,
				"REQUEST": "doQuery",
				"LANG": "ADQL"}) as job:
			jobId = job.jobId
		try:
			taprunner.runTAPJob(jobId)
			with tap.TAPJob.makeFromId(jobId) as job:
				if job.phase==uws.ERROR:
					self.fail("Job died with msg %s"%job.getError())
				name, mime = job.getResult("result")
				res = votable.load(name)
		finally:
			with tap.TAPJob.makeFromId(jobId) as job:
				job.delete()
		return res

	def testSimpleJob(self):
		jobId = None
		try:
			with uws.UWSJob.create(args={
					"QUERY": "SELECT * FROM %s"%self.tableName,
					"REQUEST": "doQuery",
					"LANG": "ADQL"}) as job:
				jobId = job.jobId
				self.assertEqual(job.phase, uws.PENDING)
				job.changeToPhase(uws.QUEUED, None)
			
			runningPhases = set([uws.QUEUED, uws.EXECUTING])
			# let things run, but bail out if nothing happens 
			for i in range(100):
				time.sleep(0.1)
				with uws.UWSJob.makeFromId(jobId) as job:
					if job.phase not in runningPhases:
						break
			else:
				raise AssertionError("Job does not finish.  Your machine cannot be"
					" *that* slow?")

			with uws.UWSJob.makeFromId(jobId) as job:
				self.assertEqual(job.phase, uws.COMPLETED)
				result = open(os.path.join(job.getWD(), 
					job.getResults()[0]["resultName"])).read()

		finally:
			if jobId is not None:
				with uws.UWSJob.makeFromId(jobId) as job:
					job.delete()
		self.failUnless('xmlns="http://www.ivoa.net/xml/VOTable/' in result)

	def testColumnNames(self):
		table, meta = self._getQueryResult(
			'SELECT cos(delta) as frob, alpha as "AlPhA", delta, "delta",'
			' 20+30, 20+30 AS constant, rv as "AS"'
			' from %s'%self.tableName)
		fields = meta.getFields()
		self.assertEqual(fields[0].name, "frob")
		self.assertEqual(fields[0].getDescription(), "A sample Dec --"
			" *TAINTED*: the value was operated on in a way that unit and"
			" ucd may be severely wrong")
		self.assertEqual(fields[1].name, "AlPhA")
		self.assertEqual(fields[2].name, "delta")
		# the next line tests for a documented violation of the spec.
		self.assertEqual(fields[3].name, "delta_")
		self.failUnless(isinstance(fields[4].name, basestring))
		self.assertEqual(fields[5].name, "constant")
		self.assertEqual(fields[6].name, "AS")

	def testColumnTypes(self):
		table, meta = self._getQueryResult(
			"SELECT rv, point('icrs', alpha, delta), PI() from %s"%self.tableName)
		fields = meta.getFields()
		self.assertEqual(fields[0].datatype, "double")
		self.assertEqual(fields[1].datatype, "char")
		self.assertEqual(fields[1].xtype, "adql:POINT")
		self.assertEqual(fields[2].datatype, "double")


class TAPSchemaTest(testhelpers.VerboseTest):
	"""tests for accessability of TAP_SCHEMA from ADQL.
	"""
	def setUp(self):
		with tap.TAPJob.create(args={
				"QUERY": "SELECT TOP 1 * FROM TAP_SCHEMA.tables",
				"REQUEST": "doQuery",
				"LANG": "ADQL"}) as job:
			self.jobId = job.jobId
	
	def tearDown(self):
		with tap.TAPJob(self.jobId) as job:
			job.delete()

	def testTAP_tables(self):
		taprunner.runTAPJob(self.jobId)
		with tap.TAPJob(self.jobId) as job:
			self.assertEqual(job.phase, uws.COMPLETED)


class UploadSyntaxOKTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	def _runTest(self, sample):
		s, e = sample
		self.assertEqual(tap.parseUploadString(s), e)
	
	samples = [
		('a,b', [('a', 'b'),]),
		('a5_ug,http://knatter?RA=99&DEC=1.54', 
			[('a5_ug', 'http://knatter?RA=99&DEC=1.54'),]),
		('a5_ug,http://knatter?RA=99&DEC=1.54;a,b', 
			[('a5_ug', 'http://knatter?RA=99&DEC=1.54'), ('a', 'b')]),]


class UploadSyntaxNotOKTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	def _runTest(self, sample):
		self.assertRaises(base.ValidationError, tap.parseUploadString,
			sample)
	
	samples = [
		'a,',
		',http://wahn',
		'a,b;',
		'a,b;whacky/name,b',]


class CapabilitiesTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	def testValid(self):
		pub = base.caches.getRD("//tap").getById("run").publications[0]
		res = capabilities.getCapabilityElement(pub)
		self.assertValidates(res.render(), leaveOffending=True)


if __name__=="__main__":
	testhelpers.main(CapabilitiesTest)
