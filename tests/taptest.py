"""
Simple tests for TAP.

All these tests really stink because TAP isn't really a good match for the
basically stateless unit tests that are executed in an arbitrary order.

There's more TAP/UWS related tests in test_tap.py; these require a
running reactor and are based on trial.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import datetime
import os
import time
import threading
import traceback
from cStringIO import StringIO

from nevow import inevow
from nevow.testutil import FakeRequest
from twisted.python.components import registerAdapter

from gavo.helpers import testhelpers

from gavo import base
from gavo import rscdesc  # uws needs getRD
from gavo import svcs
from gavo import utils
from gavo import votable
from gavo.helpers import testtricks
from gavo.protocols import tap
from gavo.protocols import taprunner
from gavo.protocols import uws
from gavo.protocols import uwsactions
from gavo.registry import capabilities
from gavo.web import vosi
from gavo.web import taprender

import adqltest
import tresc



class TAPFakeRequest(FakeRequest):
# taprender calls lowercaseProtocolArgs; fake this here.
	def __init__(self, *args, **kwargs):
		self.method = kwargs.pop("method", "GET")
		FakeRequest.__init__(self, *args, **kwargs)
		uwsactions.lowercaseProtocolArgs(self.args)


class _FakeContext(object):
	"""A scaffolding class for testing renderers.
	"""
	def __init__(self, **kwargs):
		self.request = TAPFakeRequest(args=kwargs)
		self.args = kwargs

registerAdapter(lambda ctx: ctx.request, _FakeContext, inevow.IRequest)


class PlainJobCreationTest(testhelpers.VerboseTest):
	"""tests for working job creation and destruction.
	"""
	resources = [("conn", tresc.dbConnection)]

# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		return tap.WORKER_SYSTEM.getNewJobId(parameters={"foo": "bar"})

	def _deleteJob(self, jobId):
		return tap.WORKER_SYSTEM.destroy(jobId)

	def _assertJobCreated(self, jobId):
		res = list(base.UnmanagedQuerier(self.conn).query(
			"SELECT jobId FROM tap_schema.tapjobs WHERE"
				" jobId=%(jobId)s", locals()))
		self.assertEqual(len(res), 1)
		job = tap.WORKER_SYSTEM.getJob(jobId)
		self.assertEqual(job.getSerializedPar("foo"), "bar")
		self.failUnless(os.path.exists(job.getWD()))

	def _assertJobDeleted(self, jobId):
		res = list(base.UnmanagedQuerier(self.conn).query(
			"SELECT destructiontime FROM tap_schema.tapjobs"
			" WHERE jobId=%(jobId)s", locals()))
		self.assertEqual(len(res), 0)
		self.assertRaises(base.NotFoundError, tap.WORKER_SYSTEM.getJob, jobId)
		self.failIf(os.path.exists(os.path.join(base.getConfig("uwsWD"), jobId)))

	def testBigAndUgly(self):
		jobId = self._createJob()
		self._assertJobCreated(jobId)
		self._deleteJob(jobId)
		self._assertJobDeleted(jobId)


class _UWSJobResource(testhelpers.TestResource):
# just a UWS job.  Don't manipulate it.  Too badly.
	def make(self, ignored):
		return tap.WORKER_SYSTEM.getNewJobId()
	
	def clean(self, jobId):
		tap.WORKER_SYSTEM.destroy(jobId)

_uwsJobResource = _UWSJobResource()


class TAPParametersTest(testhelpers.VerboseTest):
	resources = [("jobId", _uwsJobResource)]

	def testRunidInsensitive(self):
		with tap.WORKER_SYSTEM.changeableJob(self.jobId) as job:
			job.setSerializedPar("runId", "bac")
		job = tap.WORKER_SYSTEM.getJob(self.jobId)
		self.assertEqual(job.getSerializedPar("RUNID"), "bac")
		self.assertEqual(job.parameters["runid"], "bac")
	
	def testTAPMaxrec(self):
		with tap.WORKER_SYSTEM.changeableJob(self.jobId) as job:
			job.setSerializedPar("maxRec", "20")
		job = tap.WORKER_SYSTEM.getJob(self.jobId)
		self.assertEqual(job.parameters["maxrec"], 20)
	
	def testBadLangRejected(self):
		with tap.WORKER_SYSTEM.changeableJob(self.jobId) as job:
			self.assertRaises(base.ValidationError,
				job.setSerializedPar, "LANG", "German")

	def testUploadSerialization(self):
		with tap.WORKER_SYSTEM.changeableJob(self.jobId) as job:
			job.setSerializedPar("UPLOAD", "bar,http://127.0.0.1/root")
		job = tap.WORKER_SYSTEM.getJob(self.jobId)
		self.assertEqual(job.parameters["upload"], 
			[('bar', 'http://127.0.0.1/root')])


class UWSResponsesValidTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("jobId", _uwsJobResource)]

	def testJobRes(self):
		job = tap.WORKER_SYSTEM.getJob(self.jobId)
		self.assertValidates(uwsactions.RootAction().doGET(job, None),
			leaveOffending=True)

	def testJobList(self):
		self.assertValidates(uwsactions.getJobList(tap.WORKER_SYSTEM), 
			leaveOffending=True)


class BlockingTest(testhelpers.VerboseTest):
	"""tests for working impicit uws locking.
	"""
	resources = [("jobId", _uwsJobResource)]

	def testIndexDoesNotBlock(self):
		with tap.WORKER_SYSTEM.changeableJob(self.jobId):
			self.failUnless("uws:jobs" in uwsactions.getJobList(tap.WORKER_SYSTEM))

	def testGetPhaseDoesNotBlock(self):
		req = TAPFakeRequest()
		with tap.WORKER_SYSTEM.changeableJob(self.jobId):
			self.assertEqual(
				uwsactions.doJobAction(tap.WORKER_SYSTEM, req, (self.jobId, "phase")),
				"PENDING")

	def testPostPhaseDoesBlock(self):
		req = TAPFakeRequest(args={"PHASE": ["RUN"]})
		req.method = "POST"
		uwsactions.PhaseAction.timeout = 0.05
		with tap.WORKER_SYSTEM.changeableJob(self.jobId):
			self.assertRaisesWithMsg(base.ReportableError,
				"Could not access the jobs table. This probably means"
				" there is a stale lock on it.  Please notify the service operators.",
				uwsactions.doJobAction,
				(tap.WORKER_SYSTEM, req, (self.jobId, "phase")))


class QueueTest(testhelpers.VerboseTest):
	def testQuote(self):
		now = datetime.datetime.utcnow()
		tick = datetime.timedelta(minutes=15)
		jobs = []
		try:
			jobId = tap.WORKER_SYSTEM.getNewJobId()
			with tap.WORKER_SYSTEM.changeableJob(jobId) as wjob:
				wjob.change(phase=uws.QUEUED, destructionTime=now+10*tick)
			jobs.append(jobId)

			testJob = tap.WORKER_SYSTEM.getJob(jobId)
			# don't fail just because jobs are left in the queue
			baseDelay = testJob.quote-now

			jobId = tap.WORKER_SYSTEM.getNewJobId()
			with tap.WORKER_SYSTEM.changeableJob(jobId) as wjob:
				wjob.change(phase=uws.QUEUED, destructionTime=now+9*tick)
			jobs.append(jobId)
			
			# our quote must now be roughly 10 minutes (as configured in
			# tap.EST_TIME_PER_JOB) later
			self.assertEqual((testJob.quote-now-baseDelay).seconds/10, 
				tap.EST_TIME_PER_JOB.seconds/10)

			jobId = tap.WORKER_SYSTEM.getNewJobId()
			with tap.WORKER_SYSTEM.changeableJob(jobId) as wjob:
				wjob.change(phase=uws.QUEUED, destructionTime=now+11*tick)
			jobs.append(jobId)

			# the new job will run later then our test job, so no change
			# expected
			self.assertEqual((testJob.quote-now-baseDelay).seconds/10, 
				tap.EST_TIME_PER_JOB.seconds/10)

		finally:
			for jobId in jobs:
				tap.WORKER_SYSTEM.destroy(jobId)


class TAPTransitionsTest(testhelpers.VerboseTest):
	def testAbortPending(self):
		jobId = None
		try:
			jobId = tap.WORKER_SYSTEM.getNewJobId(
				parameters={"query": "bogus", "request": "doQuery",
				"LANG": "ADQL"})
			tap.WORKER_SYSTEM.changeToPhase(jobId, uws.ABORTED)
			self.assertEqual(tap.WORKER_SYSTEM.getJob(jobId).phase, 
				uws.ABORTED)
		finally:
			tap.WORKER_SYSTEM.destroy(jobId)


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
		res = vosi.CAP.capabilities[capabilities.getCapabilityElement(pub)]
		self.assertValidates(res.render(), leaveOffending=True)


class TAPSchemaTest(testhelpers.VerboseTest):
	def setUp(self):
		self.jobId = tap.WORKER_SYSTEM.getNewJobId(parameters={
				"query": "SELECT TOP 1 * FROM TAP_SCHEMA.tables",
				"request": "doQuery",
				"lang": "ADQL"})
	
	def tearDown(self):
		tap.WORKER_SYSTEM.destroy(self.jobId)

	def testTAP_tables(self):
		taprunner.runTAPJob(self.jobId)
		job = tap.WORKER_SYSTEM.getJob(self.jobId)
		self.assertEqual(job.phase, uws.COMPLETED)
		res = open(job.getResult("result")[0]).read()
		self.failUnless('<RESOURCE type="results">' in res)


def _getUnparsedQueryResult(query):
	jobId = tap.WORKER_SYSTEM.getNewJobId(parameters={
			"query": query,
			"request": "doQuery",
			"lang": "ADQL"})
	try:
		taprunner.runTAPJob(jobId)
		job = tap.WORKER_SYSTEM.getJob(jobId)
		if job.phase==uws.ERROR:
			raise Exception("Job died with msg %s"%job.error)
		name, mime = job.getResult("result")
		with open(name) as f:
			res = f.read()
	finally:
		tap.WORKER_SYSTEM.destroy(jobId)
	return res

def _getQueryResult(query):
	# returns a votable.simple result for query.
	vot = _getUnparsedQueryResult(query)
	res = votable.load(StringIO(vot))
	return res


class SimpleRunnerTest(testhelpers.VerboseTest):
	"""tests various taprunner scenarios.
	"""
	resources = [("ds", adqltest.adqlTestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.tableName = self.ds.tables["adql"].tableDef.getQName()

	def testSimpleJob(self):
		jobId = tap.WORKER_SYSTEM.getNewJobId(parameters={
			"query": "SELECT * FROM %s"%self.tableName,
			"request": "doQuery",
			"lang": "ADQL"})
		try:
			job = tap.WORKER_SYSTEM.getJob(jobId)
			self.assertEqual(job.phase, uws.PENDING)
			tap.WORKER_SYSTEM.changeToPhase(jobId, uws.QUEUED, None)
		
			runningPhases = set([uws.QUEUED, uws.UNKNOWN, uws.EXECUTING])
			# let things run, but bail out if nothing happens 
			for i in range(100):
				time.sleep(0.1)
				job.update()
				if job.phase not in runningPhases:
					break
			else:
				raise AssertionError("Job does not finish.  Your machine cannot be"
					" *that* slow?")
			self.assertEqual(job.phase, uws.COMPLETED)
			result = open(os.path.join(job.getWD(), 
				job.getResults()[0]["resultName"])).read()
			self.failUnless((datetime.datetime.utcnow()-job.endTime).seconds<1)

		finally:
			job = tap.WORKER_SYSTEM.destroy(jobId)
		self.failUnless('xmlns="http://www.ivoa.net/xml/VOTable/' in result)

	def testColumnNames(self):
		table, meta = _getQueryResult(
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
		table, meta = _getQueryResult(
			"SELECT rv, point('icrs', alpha, delta), PI() from %s"%self.tableName)
		fields = meta.getFields()
		self.assertEqual(fields[0].datatype, "double")
		self.assertEqual(fields[1].datatype, "char")
		self.assertEqual(fields[1].xtype, "adql:POINT")
		self.assertEqual(fields[2].datatype, "double")


class _TAPResultTable(testhelpers.TestResource):
	resources = [("ds", adqltest.adqlTestTable)]

	def make(self, deps):
		return testhelpers.getXMLTree(
			_getUnparsedQueryResult(
				"SELECT rv, PI() from %s"%
					deps["ds"].tables["adql"].tableDef.getQName()), debug=False)


class VOTableMetaTest(testhelpers.VerboseTest):
	resources = [("tree", _TAPResultTable())]

	def testQueryPresent(self):
		self.assertEqualIgnoringAliases(
			self.tree.xpath("//INFO[@name='query']")[0].get("value"),
			"SELECT rv, PI() ASWHATEVER FROM test.adql LIMIT 2000")
	
	def testJoinedTablesMentioned(self):
		self.assertEqual(self.tree.xpath("//INFO[@name='src_res']")[0].get("value"),
			"Contains traces from resource data/test")
		self.assertEqual(self.tree.xpath(
			"//INFO[@name='src_table']")[0].get("value"),
			"Contains traces from table test.adql")
	
	def testCopyrightsMentioned(self):
		self.assertEqual(self.tree.xpath(
			"//INFO[@name='copyright']")[0].get("value"),
			"Content from data/test has rights note (see INFO content)")
		self.assertEqual(self.tree.xpath("//INFO[@name='copyright']")[0].text,
			"Everything in here is pure fantasy (distributed under the GNU GPL)")

	def testSourcesMentioned(self):
		self.assertEqual(self.tree.xpath("//INFO[@name='source']")[0].get("value"),
			"1635QB41.G135......")


class TAPTableMetaTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection), ("ot", tresc.obscoreTable),
		("ssa", tresc.ssaTestTable)]

	def testSingleSourceTableMetadataCopied(self):
		res = taprunner.runTAPQuery(
			"SELECT TOP 1 * FROM ivoa.obscore", 1, self.conn, [], 1,
			autoClose=False)
		self.assertEqual(
			base.getMetaText(res, "description"),
			"The IVOA-defined obscore table, containing generic metadata for\n"
			"datasets within this datacenter.")
		list(res) # exhaust the cursor
	
	def testSingleSourceTableParamsCopied(self):
		res = taprunner.runTAPQuery(
			"SELECT TOP 1 * FROM test.hcdtest", 1, self.conn, [], 1,
			autoClose=False)
		list(res) # exhaust the cursor
		self.assertEqual(res.getParam("ssa_model"), "Spectrum-1.0")
		self.assertEqual(res.getParam("ssa_specres"), 1e-10)

	def testNoMetadataOnComplexQuery(self):
		res = taprunner.runTAPQuery(
			"SELECT TOP 1 * FROM (SELECT * from ivoa.obscore) as q", 
				1, self.conn, [], 1, autoClose=False)
		self.assertEqual(
			base.getMetaText(res, "description"), None)
		list(res)

	def testNoMetadataOnJoin(self):
		res = taprunner.runTAPQuery(
			"SELECT TOP 1 * FROM ivoa.obscore as a join ivoa.obscore as b"
				" ON (a.obs_collection=b.dataproduct_subtype)", 
				1, self.conn, [], 1, autoClose=False)
		self.assertEqual(
			base.getMetaText(res, "description"), None)
		list(res)


class JobMetaTest(testhelpers.VerboseTest):
	def setUp(self):
		self.jobId = tap.WORKER_SYSTEM.getNewJobId()
	
	def tearDown(self):
		tap.WORKER_SYSTEM.destroy(self.jobId)

	def _postRedirectCheck(self, req, segments, method="POST"):
		req.method = method
		try:
			return uwsactions.doJobAction(tap.WORKER_SYSTEM, req,
				segments=(self.jobId,)+segments)
		except svcs.WebRedirect:
			pass # that's the 303 expected
		else:
			self.fail("POSTing didn't redirect")

	def testExecD(self):
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "executionduration"))
		self.assertEqual(res, "3600")
	
	def testSetExecD(self):
		self._postRedirectCheck(
			TAPFakeRequest(args={"EXECUTIONDURATION": ["300"]}),
			("executionduration",))
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "executionduration"))
		self.assertEqual(res, "300")

	def testDestruction(self):
		self._postRedirectCheck(
			TAPFakeRequest(args={"DESTRuction": ["2000-10-10T10:12:13"]}),
			("destruction",))
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "destruction"))
		self.assertEqual(res, "2000-10-10T10:12:13Z")
	
	def testQuote(self):
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "quote"))
		# just make sure it's an iso date
		utils.parseISODT(res)

	def testNullError(self):
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "error"))
		self.assertEqual(res, "")

	def testParametersPostAll(self):
		self._postRedirectCheck(
			TAPFakeRequest(args={"QUERY": ["Nicenice"]}),
			("parameters",))

		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "parameters"))
		self.failUnless("Nicenice" in res.render())

	def testOwner(self):
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "owner"))
		self.assertEqual(res, "")

	def testPlan(self):
		self._postRedirectCheck(
			TAPFakeRequest(args={"QUERY": "SELECT * from TAP_SCHEMA.tables",
				"request": "doQuery", "lang": "ADQL"}),
			segments=("parameters",))
		res = uwsactions.doJobAction(tap.WORKER_SYSTEM, TAPFakeRequest(),
			segments=(self.jobId, "plan"))
		self.assertTrue("SELECT TAP_SCHEMA.tables.schema_name, TAP_SCHEMA.tables.table_name, TAP_SCHEMA.tables.table_type, TAP_SCHEMA.tables.description, TAP_SCHEMA.tables.utype, TAP_SCHEMA.tables.sourcerd FROM TAP_SCHEMA.tables LIMIT 2000"
			in res)


class _TAPPublishedADQLTable(tresc.CSTestTable):
	def make(self, deps):
		res = tresc.CSTestTable.make(self, deps)
		tap.publishToTAP(res.tableDef.rd, self.conn)
		self.conn.commit()
		return res
	
	def clean(self, table):
		try:
			tresc.CSTestTable.clean(self, table)
			tap.unpublishFromTAP(res.tableDef.rd, self.conn)
			self.conn.commit()
		except:
			self.conn.rollback()


class TAPPublicationTest(testhelpers.VerboseTest):
	resources = [("table", _TAPPublishedADQLTable())]

	def testColumnsPublished(self):
		with base.AdhocQuerier() as q:
			res = list(q.query(
				"select column_name, unit, datatype"
				" from tap_schema.columns where table_name='test.adql'"))
			self.failUnless(("alpha", "deg", "REAL") in res)
	
	def testSTCGroupPresent(self):
		with base.AdhocQuerier() as q:
			res = set(list(q.query(
				"select * from tap_schema.groups")))
			self.failUnless(
				('test.adql', 'alpha', 'col:weird.reason', 
					'weird_columns', 'col:weird.name', "data/test") in res)
			self.failUnless(
				('test.adql', 'rv', None, 'nice_columns', 'col:nice.name', "data/test")
					in res)


class _RenderedTAPExample(testhelpers.TestResource):
	def make(self, ignored):
		from gavo.web import examplesrender

		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><meta name="_example"
				title="Query against boolean columns">
				Some tables this
				service exposes to TAP -- e.g., :taptable:`amanda.nucand`. 
				To query those, you cannot say ``WHERE boolCol`` but have to compare
				``'True'`` or ``'False'`` as in

				.. tapquery::

					SELECT * 
					  FROM amanda.nucand 
					WHERE atmonusubset='True' and foo&lt;20
					
				(nothing else will work).</meta></resource>""")
		return testhelpers.getXMLTree(
			examplesrender._Example(
				rd.getMeta("_example"))._getTranslatedHTML(), debug=False)


class TAPExampleTest(testhelpers.VerboseTest):
	resources = [("tree", _RenderedTAPExample())]

	def testContainerDeclared(self):
		root = self.tree.xpath('/div[@typeof="example"]')[0]
		self.assertEqual(root.get("id"), "Queryagainstbooleancolumns")
		self.assertEqual(root.get("resource"), "#Queryagainstbooleancolumns")

	def testTitleMarkedUp(self):
		title = self.tree.xpath("h2")[0]
		self.assertEqual(title.get("property"), "name")
		self.assertEqual(title.text, "Query against boolean columns")

	def testPlainText(self):
		para = self.tree.xpath("p")[0]
		self.assertTrue(para.text.startswith("Some tables"))
	
	def testTableLink(self):
		tableAnchor = self.tree.xpath("//*[@property='table']")[0]
		self.assertEqual(len(tableAnchor), 0) # no children
		self.assertEqual(tableAnchor.text, "amanda.nucand")
		tableLink = self.tree.xpath("//a")[0]
		self.assertEqual(tableLink.get("href"), "/tableinfo/amanda.nucand")

	def testQueryPresent(self):
		queryEl = self.tree.xpath("//*[@property='query']")[0]
		self.assertEqual(queryEl.text.strip(),
			"SELECT *\n  FROM amanda.nucand\nWHERE atmonusubset='True' and foo<20")
		self.assertEqual(queryEl.attrib["class"],
			'dachs-ex-tapquery literal-block')
	

if __name__=="__main__":
	testhelpers.main(JobMetaTest)
