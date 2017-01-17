"""
Tests for the datalink subsystem and (potentially) special data tricks.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import atexit
import glob
import os
import time
import unittest

from twisted.internet import reactor
from twisted.python import threadable
threadable.init()

import trialhelpers

from gavo import api


class SyncTest(trialhelpers.ArchiveTest):
	def testInfoWorks(self):
		return self.assertGETHasStrings("/data/cores/dl/info", {}, [
			'<h2 class="section">Input Fields</h2>',
			"<td>The pubisher DID of the dataset of interest</td>"])

	def testErrorDocumentMetaGeneral(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "broken"},
			["<TD>Fault: global name 'ddt' is not defined</TD>"])

	def testErrorDocumentMetaNotFound(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://not.here"},
			["<TD>NotFoundFault: Not a pubDID from this site.</TD>"])

	def testErrorDocumentAccess(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", 
			{"ID": "broken"},
			["global name 'ddt' is not defined"])

	def testErrorStatus(self):
		return self.assertStatus("/data/cores/dl/dlget", 422)

	def testWithoutId(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {}, [
			"<TABLEDATA></TABLEDATA>",
			"<FIELD",
			'name="service_def"']) 

	def testMetadata(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://x-unregistred/~?data/excube.fits"}, [
				'latitude coordinate</DESCRIPTION><VALUES><MIN value="30.9831815872">'
					'</MIN><MAX value="30.9848485045">',
				'xtype="interval"'])

	def testRespformat1(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "votable",
			},
			['<DESCRIPTION>The latitude coordinate</DESCRIPTION>'
				'<VALUES><MIN value="30.9831815872">',])

	def testRespformat2(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "application/x-votable+xml",
			},
			['<DESCRIPTION>The latitude coordinate</DESCRIPTION>'
				'<VALUES><MIN value="30.9831815872">',])

	def testInvalidRespformat(self):
		def assertStatus422(res):
			self.assertEqual(res[1].code, 422)

		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "vnd-microsoft/xls"
			},
			["Field RESPONSEFORMAT: 'vnd-microsoft/xls'"
				" is not a valid value for RESPONSEFORMAT"]).addCallback(
				assertStatus422)

	def testRedirection(self):
		def assertStatus301(res):
			self.assertEqual(res[1].code, 301)

		return self.assertGETHasStrings("/data/cores/dl/dlget", {
				"ID": "somewhereelse",
			},
			['<a href="http://some.whereel.se/there">different URL']).addCallback(
				assertStatus301)

	def testMetadataError(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://x-unregistred/~?data/excube.fit"},
			["TR><TD>ivo://x-unregistred/~?data/excube.fit</TD><TD></TD><TD></TD><TD>"
				"NotFoundFault: accref 'data/excube.fit' could not be located"
				" in product table</TD>"])
	
	def testCubeCutout(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", {
			"ID": "ivo://x-unregistred/~?data/excube.fits",
			"COO_3": "3753 +Inf"}, [
			"NAXIS3  =                    2",
			"CRPIX3  =                 -1.0"])

	def testSDM2Spectrum(self):
		# This is testing a silly sort of backdoor.  Don't count on it
		# staying in place.
		return self.assertGETHasStrings("/data/ssatest/dl/dlget", {
				"FORMAT": "application/x-votable+xml;content=spec2",
				"ID": "ivo://test.inv/test2"},
			["spec2:Char.SpatialAxis.Coverage.Location.Value",
			"1908.0"])

	def testNoMultiArguments(self):
		def assertErrorResponse(res):
			self.assertEqual(res[1].code, 422)

		return self.assertGETHasStrings("/data/cores/dl/dlget", {
				"CIRCLE": ["10 10 5", "14 13 2"],
				"ID": "ivo://x-unregistred/~?data/excube.fits"},
			["MultiValuedParamNotSupported: Field CIRCLE"]
			).addCallback(assertErrorResponse)

	def testAvailability(self):
		return self.assertGETHasStrings("/data/cores/dl/availability", {},
			["<avl:available>true</avl:available>"])

	def testCapabilities(self):
		return self.assertGETHasStrings("/data/cores/dl/capabilities", {}, [
			'standardID="ivo://ivoa.net/std/DataLink#links-1.0"',
			'/data/cores/dl/dlmeta</accessURL>',
			'<ucd>meta.id;meta.main</ucd>'])

	def testNoExtraSegments(self):
		return self.assertGETHasStrings("/data/ssatest/dl/dlget/inv.test2", {
				"ID": "ivo://test.inv/test2"},
			["Not Found (404)",
			"'dlget' has no child"])

	def testCleanedup(self):
		# this doesn't do any queries, it just makes sure that
		# the datalink services above cleaned up after themselves
		# (of course, we might see crap from the last run rather than
		# from this, but statistically it should catch trouble.
		pooLeft = glob.glob(
			os.path.join(api.getConfig("tempDir"), "fitstable*"))
		self.assertFalse(pooLeft, "Something left fitstable temporaries"
			" in tempDir %s"%api.getConfig("tempDir"))

	def testDECandPOS(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", {
			"ID": "ivo://x-unregistred/~?data/excube.fits",
			"DEC": "30.9832 30.9834",
			"POS": "CIRCLE 359.36 30.985 0.0004"},[
			"UsageError: Field DEC: Attempt to cut out along axis 2"
			" that has been modified before."])

	def testPOSandPIXEL(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", {
			"ID": "ivo://x-unregistred/~?data/excube.fits",
			"PIXEL_1": "1 3",
			"POS": "CIRCLE 359.36 30.985 0.0004"},[
			"UsageError: Field PIXEL_1: Attempt to cut out along axis 1"
			" that has been modified before."])

	def testEmptyResponse(self):
		def assertResponseCode(res):
			self.assertEqual(res[0], "")
			self.assertEqual(res[1].code, 204)

		return self.assertGETLacksStrings("/data/cores/dl/dlget", {
			"ID": "ivo://x-unregistred/~?data/excube.fits",
			"POS": "CIRCLE 10 10 0.0001"},
			[" "]).addCallback(assertResponseCode)


def killLocalhost(url):
	"""should delete the host part from url.

	Well, this only works for a very special case and is easy to improve  :-)
	"""
	return url[21:]


class AsyncTest(trialhelpers.ArchiveTest):
	def testNonExistingJobMessage(self):
		return self.assertGETHasStrings("/data/cores/dl/dlasync/thisjobidisbad", 
			{}, [
			'name="QUERY_STATUS"',
			'value="ERROR"',
			"UWS job 'thisjobidisbad' could not be located in jobs table"])

	def testNonExistingJobStatus(self):
		return self.assertStatus("/data/cores/dl/dlasync/thisjobidisbad",
			404)

	def testJoblist(self):
		return self.assertGETHasStrings("/data/cores/dl/dlasync", 
			{}, [
			"/static/xsl/dlasync-joblist-to-html.xsl",
			"<uws:jobs"])

	def testBasicCutout(self):
		# this is a pretty close clone of testLifeCycle in test_tap, and
		# whatever's said there applies here, too.
		def assertDeleted(result, jobURL):
			self.assertEqual(result[1].code, 303)
			next = killLocalhost(result[1].headers["location"])
			jobId = jobURL.split("/")[-1]
			return self.assertGETLacksStrings(next, {}, ['jobref id="%s"'%jobId]
			).addCallback(lambda res: reactor.disconnectAll())

		def deleteJob(jobURL):
			return trialhelpers.runQuery(self.renderer, "DELETE", 
				jobURL, {}
			).addCallback(assertDeleted, jobURL)

		def checkResult(result, jobURL):
			self.assertEqual(result[1].headers["content-type"], "image/fits")
			self.assertTrue("NAXIS1  =                   11" in result[0])
			return deleteJob(jobURL)
		
		def waitForResult(result, jobURL, retry):
			if retry>300:
				raise AssertionError("Datalink job at jobURL %s didn't finish."
					"  Leaving it for inspection."%jobURL)
			if result[0].startswith("COMPLETED"):
				return trialhelpers.runQuery(self.renderer, "GET",
					jobURL+"/results/result", {}
				).addCallback(checkResult, jobURL)

			time.sleep(0.1)
			return trialhelpers.runQuery(self.renderer, "GET", 
				jobURL+"/phase", {}
			).addCallback(waitForResult, jobURL, retry+1)

		def assertStarted(result, jobURL):
			req = result[1]
			self.assertEqual(req.code, 303)
			self.assertEqual(killLocalhost(req.headers["location"]), jobURL)
			return waitForResult(("", None), jobURL, 0)

		def startJob(jobURL):
			return trialhelpers.runQuery(self.renderer, "POST", 
				jobURL+"/phase", {"PHASE": "RUN"}
			).addCallback(assertStarted, jobURL)

		def checkPosted(result):
			request = result[1]
			self.assertEqual(request.code, 303)
			jobURL = request.headers["location"]
			self.assertTrue(jobURL.startswith(
				"http://localhost:8080/data/cores/dl/dlasync/"),
				"Bad service URL on redirect")
			return startJob(killLocalhost(jobURL))

		return trialhelpers.runQuery(self.renderer,  "POST",
			"/data/cores/dl/dlasync", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"COO_3": "3753 +Inf"}
			).addCallback(checkPosted)
			

atexit.register(trialhelpers.provideRDData("test", "import_fitsprod"))
atexit.register(trialhelpers.provideRDData("ssatest", "test_import"))
