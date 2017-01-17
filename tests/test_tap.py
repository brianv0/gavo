"""
Twisted trial-based tests for TAP and UWS.

Tests not requiring the TAP renderer go to taptest.py

The real big integration tap tests use the HTTP interface and are in
an external resource package taptest.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import atexit
import datetime
import httplib
import re
import os
import sys
import unittest
import urllib
import urlparse
import warnings

from nevow import context
from nevow import flat
from nevow import testutil
from nevow import url
from nevow import util
from twisted.internet import reactor
from twisted.python import threadable
threadable.init()

from gavo.helpers import testhelpers

from gavo import base
from gavo import rscdesc
from gavo.protocols import scs  # for table's q3c mixin
from gavo.web import weberrors
from gavo.web.taprender import TAPRenderer

import trialhelpers


base.DEBUG = True


votWithGeom = 'eJxdUctugzAQvOcrVj72YAfUEwIkClRCigIiNNdqC26DRDCxHUj69bVDUKNcPLPa2dmH/X1eRW+b\nFEYuVSv6gDjUJSu4HLteBeSg9eAxNk0TbUeBtOeamRQzVfjVcTZadbjyy3SXf5RxaujNzuB7lm4S\nyJKAKIWfnahRG38CKCVeVfvLA/JCoEGN+jqYoD6gJNDjkT9XnOsmIINQlJ9M0Lc6IA3/MXQuVLr2\nIqWliIWQjaKFUK0tdBO6x+7MXQKXWYnNqfOKPNtWduYk3cVlVlRZvg2zuNzB0hHEN+DApT5LDjXv\nNZc+e1SvfHbbzppEVbQsPXMAvyotWJKEyzRwa+HS9doB59WCz0zaypnVm/ffw7S743JN9nBhdv+z\n8A+9NIXB\n'


class TAPRenderTest(trialhelpers.RenderTest):
	_tapService = base.caches.getRD("__system__/tap").getById("run")
	@property
	def renderer(self):
		ctx = trialhelpers.getRequestContext("/async")
		return TAPRenderer(ctx, self._tapService)


class SyncMetaTest(TAPRenderTest):
	"""tests for non-doQuery sync queries.
	"""
	def testVersionRejected(self):
		"""requests with bad version are rejected.
		"""
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "getCapabilities", "VERSION": "0.1"},
			['<INFO name="QUERY_STATUS" value="ERROR">Version mismatch'])

	def testNoSyncPaths(self):
		"""segments below sync are 404.
		"""
		return trialhelpers.runQuery(self.renderer, "GET", "/sync/foo/bar", {}
			).addCallback(lambda res: ddt
			).addErrback(lambda res: None)

	def testCapabilities(self):
		"""simple get capabilities response looks ok.
		"""
		return self.assertGETHasStrings("/sync", 
			{"REQUEST": "getCapabilities"}, [
				'<capability standardID="ivo://ivoa.net/std/TAP', 
				'ParamHTTP">'])

	def testExamples(self):
		return self.assertGETHasStrings("/examples", {}, [
			'resource="#tap_schemaexample"',
			'property="table"',
			'>tap_schema.columns</em>',
			'10\xc2\xb5m',
			'property="query"',
			"LIKE '%em.IR.8-15um%'\n</pre>",
			'vocab="ivo://ivoa.net/std/DALI-examples#"'])
			

class SyncQueryTest(TAPRenderTest):
	"""tests for querying sync queries.
	"""
	aVOTable = os.path.join(base.getConfig("inputsdir"), 
		"data/vizier_votable.vot")

	def testNoLangRejected(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery", 
				"QUERY": 'SELECT alpha FROM test.adql WHERE alpha<3'
			}, [
				"<INFO", "Required parameter 'lang' missing.</INFO>"])

	def testBadLangRejected(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "Furz",
				"QUERY": 'SELECT alpha FROM test.adql WHERE alpha<3'
			}, [
				'<INFO name="QUERY_STATUS" value="ERROR">Field LANG: This service does'
				' not support the query language Furz'])

	def testSimpleQuery(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT alpha FROM test.adql WHERE alpha<2'
			}, [
				'<RESOURCE type="results">',
				'ucd="pos.eq.ra;meta.main"',
				'ID="alpha"',
				'unit="deg"',
				'name="alpha"'])

	def testOverflow(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"MAXREC": "1",
				"QUERY": 'SELECT alpha FROM test.adql'
			}, [
				'<INFO name="QUERY_STATUS" value="OVERFLOW"', ])

	def testBadFormat(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT alpha FROM test.adql WHERE alpha<2',
				"FORMAT": 'xls'
			}, [
				'<INFO name="QUERY_STATUS" value="ERROR">Field FORMAT:'
				' Unsupported format \'xls\'', 'Legal format codes include'])

	def testClearVOT(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT CIRCLE(\'ICRS\', alpha, delta, 10)'
					' FROM test.adql WHERE alpha<3',
				"FORMAT": "votable/td"
			}, [
				'<TABLEDATA><TR><TD>Circle ICRS 2. 14. 10.</TD></TR></TABLEDATA>'])

	def testCSV(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT alpha,delta FROM test.adql WHERE alpha<3',
				"FORMAT": "text/csv"
			}, [
				'2.0,14.0'])

	def testTSV(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT alpha, delta FROM test.adql WHERE alpha<3',
				"FORMAT": "TSV"
			}, [
				'2.0\t14.0'])

	def testJSON(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": "SELECT TOP 1 column_name, datatype FROM TAP_SCHEMA.columns"
					" WHERE table_name='tap_schema.tables' ORDER BY column_name",
				"FORMAT": "application/json"
			}, [
				'"contains": "table"',
				'"description": "ADQL datatype"',
				'[["description", "VARCHAR"]]',
				'"queryStatus": "OVERFLOW"'])


	def testBin2Table(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT alpha, delta FROM test.adql WHERE alpha<3',
				"FORMAT": "application/x-votable+xml;serialization=BINARY2"
			}, [
				'BINARY2', 'AEAAAABBYAAA'])

	def testBadUploadSyntax(self):
		return self.assertPOSTHasStrings("/sync", {
				"REQUEST": "doQuery",
				"UPLOAD": "bar",
				"LANG": "ADQL",
				"QUERY": 'SELECT * FROM test.adql'
			}, [
				"only allow regular SQL identifiers"])

	def testBadUploadSyntax2(self):
		return self.assertPOSTHasStrings("/sync", {
			"REQUEST": "doQuery",
			"UPLOAD": "bar,http://x.y;",
			"LANG": "ADQL",
			"QUERY": 'SELECT * FROM test.adql'}, [
			"only allow regular SQL identifiers"
			])

	def testNonExistingUpload(self):
		return self.assertPOSTHasStrings("/sync", {
				"REQUEST": "doQuery",
				"UPLOAD": "bar,http://127.0.0.1:65000",
				"LANG": "ADQL",
				"QUERY": 'SELECT * FROM test.adql'
			}, [
				"'http://127.0.0.1:65000' cannot be retrieved</INFO",
				"Connection refused"])

	def testUploadCannotReadLocalFile(self):
		return self.assertPOSTHasStrings("/sync", {
			"REQUEST": "doQuery",
			"UPLOAD": "bar,file:///etc/passwd",
			"LANG": "ADQL",
			"QUERY": 'SELECT * FROM test.adql'}, [
			"'file:///etc/passwd' cannot be retrieved</INFO",
			"unknown url type"
			]).addErrback(lambda failure: None)

	def testMalformedUploadURL(self):
		return self.assertPOSTHasStrings("/sync", {
			"REQUEST": "doQuery",
			"UPLOAD": "http://fit://file://x.ab",
			"LANG": "ADQL",
			"QUERY": 'SELECT * FROM test.adql'}, [
			'<INFO name="QUERY_STATUS" value="ERROR">Field UPLOAD:'
			' Syntax error in UPLOAD parameter'
			])

	def testInlineUploadFromArgsWorks(self):
		return self.assertPOSTHasStrings("/sync", {
				"REQUEST": "doQuery",
				"UPLOAD": "bar,param:HoNk",
				"LANG": "ADQL",
				"QUERY": 'SELECT * FROM tap_upload.bar join test.adql on'
					' (alpha-"_RAJ2000"<0)',
				"HoNk": open(self.aVOTable).read(),
			}, [
				'xmlns="http://www.ivoa.net/xml/VOTable/',
				'ucd="pos.eq.ra;meta.main"',
				'encoding="base64"'])

	def testMissingInlineParameter(self):
		return self.assertPOSTHasStrings("/sync", {
				"REQUEST": "doQuery",
				"UPLOAD": "bar,param:HoNk",
				"LANG": "ADQL",
				"QUERY": 'SELECT top 1 * FROM tap_upload.bar',
				"MoNk": open(self.aVOTable).read(),
			}, [
				'<INFO name="QUERY_STATUS" value="ERROR">No parameter for'
				' upload table bar'])

	def testWithUploadGeom(self):
		return self.assertPOSTHasStrings("/sync", {
				"REQUEST": "doQuery",
				"UPLOAD": "t1,param:HoNk",
				"LANG": "ADQL",
				"FORMAT": "votable/td",
				"QUERY": 'SELECT * FROM test.adql join tap_upload.t1'
					" on 1=contains(ssa_location, circle('', alpha, delta, 0.002))",
				"HoNk": votWithGeom.decode("base64").decode("zlib")
			}, ["Position UNKNOWNFrame 2.00", "10.25"])


class SimpleAsyncTest(TAPRenderTest):
	"""tests for some non-ADQL async queries.
	"""
	def testVersionRejected(self):
		"""requests with bad version are rejected.
		"""
		return self.assertPOSTHasStrings("/async", {
				"REQUEST": "getCapabilities",
				"VERSION": "0.1"},
			['<INFO name="QUERY_STATUS" value="ERROR">Version mismatch'])

	def testJobList(self):
		return self.assertGETHasStrings("/async", {}, [
			'<uws:jobs xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0'])

	def testNonExistingPhase(self):
		return self.assertGETHasStrings("/async/23/phase", {},
			['<VOTABLE ', 'ERROR">UWS job \'23\' could not'])

	def testLifecycle(self):
		"""tests job creation, redirection, phase, and deletion.
		"""
		# This one is too huge and much too slow for a unit test.  Still
		# I want at least one integration-type test in here since the
		# big test probably won't be run at every commit.
		def assertDeleted(result, jobId):
			self.assertEqual(result[1].code, 303)
			next = result[1].headers["location"][len(
				self._tapService.getURL("tap")):]
			self.assertEqual(next, "/async",
				"Deletion redirect doesn't point to job list but to %s"%next)
			return self.assertGETLacksStrings(next, {}, ['jobref id="%s"'%jobId]
			).addCallback(lambda res: reactor.disconnectAll())

		def delete(jobId):
			return trialhelpers.runQuery(self.renderer, "DELETE", "/async/"+jobId, {}
			).addCallback(assertDeleted, jobId)

		def assertStarted(lastRes, jobId):
			# lastRes must be a redirect to the job info page
			req = lastRes[1]
			self.assertEqual(req.code, 303)
			self.assertEqual(req.headers["location"], 
				 "http://localhost:8080/__system__/tap/run/tap/async/"+jobId)
			return delete(jobId)

		def promote(ignored, jobId):
			return trialhelpers.runQuery(self.renderer, "POST", 
				"/async/%s/phase"%jobId, {"PHASE": "RUN"}
			).addCallback(assertStarted, jobId)

		def checkPlan(ignored, jobId):
			return self.assertGETHasStrings("/async/%s/plan"%jobId, {},
				["<plan:operation><plan:description>Limit</plan:description>"]
			).addCallback(promote, jobId)

		def checkQuote(ingored, jobId):
			return self.assertGETHasStrings("/async/%s/quote"%jobId, {},
				['-']
				).addCallback(checkPlan, jobId)

		def checkPhase(jobId):
			return self.assertGETHasStrings("/async/%s/phase"%jobId, {},
				['PENDING']
				).addCallback(checkQuote, jobId)

		def checkPosted(result):
			# jobId is in location of result[1]
			request = result[1]
			self.assertEqual(request.code, 303)
			next = request.headers["location"]
			self.failIf("/async" not in next)
			jobId = next.split("/")[-1]
			return checkPhase(jobId)

		return trialhelpers.runQuery(self.renderer, "POST", "/async", {
			"REQUEST": "doQuery", "LANG": "ADQL", 
			"QUERY": "SELECT alpha FROM test.adql WHERE alpha<3"}
		).addCallback(checkPosted)

	def testBadConstructionArgument(self):
		def checkPosted(result):
			request = result[1]
			self.assertEqual(request.code, 400)
			self.failUnless("base 10: 'kaputt" in result[0])
			# it would be cool if we could check that the job has actually
			# not been created -- but even looking at the DB that's not trivial
			# to do reliably.

		return trialhelpers.runQuery(self.renderer, "POST", "/async", {
			"REQUEST": "doQuery", "LANG": "ADQL", 
			"MAXREC": "kaputt",
			"QUERY": "SELECT ra FROM test.adql WHERE ra<3"}
		).addCallback(checkPosted)

atexit.register(trialhelpers.provideRDData("test", "ADQLTest"))
