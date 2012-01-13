"""
Tests for generic UWS

If it's TAP we're talking about, use taptest.py.
"""

import datetime
import Queue
import threading

from gavo.helpers import testhelpers

from gavo import base
from gavo import rscdesc # for base.caches registration
from gavo.protocols import uws

import tresc

class _PlainTransitions(uws.UWSTransitions):
	def __init__(self):
		uws.UWSTransitions.__init__(self, "plain", [
			(uws.PENDING, uws.QUEUED, "noOp"),
			(uws.PENDING, uws.EXECUTING, "run"),
			(uws.QUEUED, uws.EXECUTING, "run"),
			(uws.EXECUTING, uws.COMPLETED, "noOp"),
			(uws.QUEUED, uws.ABORTED, "noOp"),
			(uws.EXECUTING, uws.ABORTED, "noOp"),])
	
	def run(self, newState, writableJob, ignored):
		writableJob.change(phase=uws.COMPLETED)


class IntegerParameter(uws.JobParameter):
	@staticmethod
	def _serialize(value):
		return str(value)
	
	@staticmethod
	def _deserialize(value):
		return int(value)


class UWSTestJob(uws.BaseUWSJob):
	_jobsTDId = "data/uwstest#testjobs"
	_transitions = _PlainTransitions()

	_parameter_somenumber = IntegerParameter
	_parameter_nocase = IntegerParameter

_TEST_UWS = uws.UWS(UWSTestJob)


class _TestUWSTable(tresc.RDDataResource):
	rdName = "uwstest.rd"
	dataId = "import"

_testUWSTable = _TestUWSTable()


class UWSObjectTest(testhelpers.VerboseTest):
	resources = [("testUWSTable", _testUWSTable)]

	def testGetStatement(self):
		self.assertEqual(_TEST_UWS._statements["getById"][1],
			"SELECT jobId, phase, executionDuration, destructionTime,"
			" owner, parameters, runId, startTime, endTime, error, magic"
			" FROM test.testjobs WHERE jobId=%(jobId)s ")

	def testExGetStatement(self):
		self.assertEqual(_TEST_UWS._statements["getByIdEx"][1],
			"SELECT jobId, phase, executionDuration, destructionTime,"
			" owner, parameters, runId, startTime, endTime, error, magic"
			" FROM test.testjobs WHERE jobId=%(jobId)s FOR UPDATE ")

	def testFeedStatement(self):
		self.assertEqual(_TEST_UWS._statements["feedToIdEx"][1], 
			'INSERT INTO test.testjobs (jobId, phase, executionDuration,'
			' destructionTime, owner, parameters, runId,'
			' startTime, endTime, error, magic) VALUES (%(jobId)s, %(phase)s,'
			' %(executionDuration)s, %(destructionTime)s, %(owner)s,'
			' %(parameters)s, %(runId)s, %(startTime)s, %(endTime)s,'
			' %(error)s, %(magic)s)')
	
	def testJobsTDCache(self):
		td1 = UWSTestJob.jobsTD
		td2 = UWSTestJob.jobsTD
		self.assertEqual(td1.columns[0].name, "jobId")
		self.failUnless(td1 is td2)

	def testCountFunctions(self):
		jobId = _TEST_UWS.getNewJobId()
		self.assertEqual(_TEST_UWS.countQueuedJobs(), 0)
		_TEST_UWS.changeToPhase(jobId, uws.QUEUED)
		try:
			self.assertEqual(_TEST_UWS.countQueuedJobs(), 1)
			self.assertEqual(_TEST_UWS.countRunningJobs(), 0)
		finally:
			_TEST_UWS.destroy(jobId)

	def testNotFoundRaised(self):
		self.assertRaises(uws.JobNotFound,
			_TEST_UWS.getJob,
			"there's no way this id could ever exist")


class TestWithUWSJob(testhelpers.VerboseTest):
	resources = [("testUWSTable", _testUWSTable)]

	def setUp(self):
		self.job = _TEST_UWS.getNewJob()
		testhelpers.VerboseTest.setUp(self)
	
	def tearDown(self):
		try:
			_TEST_UWS.destroy(self.job.jobId)
		except uws.JobNotFound:
			# tests may kill jobs themselves
			pass


class SimpleJobsTest(TestWithUWSJob):
	def testNonPropertyRaises(self):
		self.assertRaises(AttributeError,
			lambda: self.job.foobar)

	def testCannotChangeRO(self):
		self.assertRaises(TypeError,
			self.job.change, owner="rupert")

	def testChangeWorks(self):
		self.assertEqual(self.job.owner, None)
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			self.assertEqual(wjob.owner, None)
			wjob.change(owner="rupert")
			self.assertEqual(wjob.owner, "rupert")
		self.job.update()
		self.assertEqual(self.job.owner, "rupert")

	def testDefaultInPlace(self):
		self.assertEqual(self.job.phase, uws.PENDING)

	def testAssigningIsForbidden(self):
		def fails():
			with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
				wjob.phase = uws.PENDING
		self.assertRaises(TypeError, fails)

	def testAssigningToNonexistingRaises(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			self.assertRaises(AttributeError, wjob.change, foo="bar")

	def testPropertyEncoding(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(parameters={"foo": 4})
		self.job.update()
		self.assertEqual(self.job.parameters["foo"], 4)

	def testNoParameterSerInRO(self):
		def fails():
			self.job.setSerializedPar("glob", "someString")
		self.assertRaises(TypeError, fails)

	def testNonmagicParameterSer(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.setSerializedPar("glob", "some string")
		self.job.update()
		self.assertEqual(self.job.parameters["glob"], "some string")
		self.assertEqual(self.job.getSerializedPar("glob"), "some string")

	def testMagicParameterSer(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.setSerializedPar("someNumber", 4)
		self.job.update()
		self.assertEqual(self.job.parameters["somenumber"], 4)
		self.assertEqual(self.job.getSerializedPar("somenumber"), "4")
		self.assertEqual(self.job.getSerializedPar("someNumber"), "4")

	def testMagicParameterNoCase(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.setSerializedPar("nOcAsE", 4)
		self.job.update()
		self.assertEqual(self.job.parameters["nocase"], 4)
		self.assertEqual(self.job.getSerializedPar("NOCASE"), "4")


class PlainActionsTest(TestWithUWSJob):
	def testSimpleTransition(self):
		_TEST_UWS.changeToPhase(self.job.jobId, uws.QUEUED)
		self.job.update()
		self.assertEqual(self.job.phase, uws.QUEUED)

	def testTransitionWithCallback(self):
		_TEST_UWS.changeToPhase(self.job.jobId, uws.EXECUTING)
		self.job.update()
		self.assertEqual(self.job.phase, uws.COMPLETED)

	def testFailingTransition(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(phase=uws.EXECUTING)
			self.assertRaises(base.ValidationError,
				wjob.getTransitionTo,
				uws.QUEUED)

	def testFailingGoesToError(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(phase=uws.EXECUTING)
		_TEST_UWS.changeToPhase(self.job.jobId, uws.QUEUED)
		self.job.update()
		self.assertEqual(self.job.phase, uws.ERROR)
	
	def testNoEndstateActions(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(phase=uws.COMPLETED)
		_TEST_UWS.changeToPhase(self.job.jobId, uws.ERROR)
		self.job.update()
		self.assertEqual(self.job.phase, uws.COMPLETED)

	def testNullActionIgnored(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(phase=uws.QUEUED)
		_TEST_UWS.changeToPhase(self.job.jobId, uws.QUEUED)
		self.job.update()
		self.assertEqual(self.job.phase, uws.QUEUED)


class JobHandlingTest(TestWithUWSJob):
	def testCleanupLeaves(self):
		_TEST_UWS.cleanupJobsTable()
		self.failUnless(self.job.jobId in _TEST_UWS.getJobIds())
	
	def testCleanupCatchesExpired(self):
		with _TEST_UWS.changeableJob(self.job.jobId) as wjob:
			wjob.change(destructionTime=
				datetime.datetime.utcnow()-datetime.timedelta(seconds=20))
		_TEST_UWS.cleanupJobsTable()
		self.failIf(self.job.jobId in _TEST_UWS.getJobIds())

	def testCleanupWithArgs(self):
		_TEST_UWS.cleanupJobsTable(includeAll=True)
		self.failIf(self.job.jobId in _TEST_UWS.getJobIds())

	def testLocking(self):
		queue = Queue.Queue()
		def blockingJob():
			# this is started in a thread while self.jobId is held
			queue.put("Child started")
			with _TEST_UWS.changeableJob(self.job.jobId) as job:
				queue.put("Job created")

		with _TEST_UWS.changeableJob(self.job.jobId) as job:
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
		def timesOut(jobId):
			with _TEST_UWS.changeableJob(jobId, timeout=0.001) as job:
				self.fail("No lock happened???")

		with _TEST_UWS.changeableJob(self.job.jobId) as job:
			self.assertRaisesWithMsg(base.ReportableError,
				"Could not access the jobs table. This probably means there"
				" is a stale lock on it.  Please notify the service operators.",
				timesOut,
				(self.job.jobId,))


if __name__=="__main__":
	testhelpers.main(JobHandlingTest)
