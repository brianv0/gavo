"""
Tests for the datalink subsystem and (potentially) special data tricks.
"""

#c Copyright 2008-2015, the GAVO project
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
	def testErrorDocumentMetaGeneral(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "broken"},
			["<TD>Fault: global name 'ddt' is not defined</TD>"])

	def testErrorDocumentMetaNotFound(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://not.here"},
			["<TD>NotFoundFault: Not a pubDID from this site.</TD>"])

	@unittest.skip("Make trialhelpers.ArchiveTest use DCExceptionHandler")
	def testErrorDocumentAccess(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", 
			{"ID": "broken"},
			["global name 'ddt' is not defined"])

	@unittest.skip("Make trialhelpers.ArchiveTest use DCExceptionHandler")
	def testErrorStatus(self):
		return self.assertStatus("/data/cores/dl/dlget", 422)

	@unittest.skip("Make trialhelpers.ArchiveTest use DCExceptionHandler")
	def testWithoutId(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {}, [
			"<TABLEDATA></TABLEDATA>",
			"<FIELD",
			'name="service_def"']) 

	def testMetadata(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://x-unregistred/~?data/excube.fits"},
			['<DESCRIPTION>The latitude coordinate, lower limit</DESCRIPTION>'
				'<VALUES><MIN value="30.9831815872">',])

	def testRespformat1(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "votable",
			},
			['<DESCRIPTION>The latitude coordinate, lower limit</DESCRIPTION>'
				'<VALUES><MIN value="30.9831815872">',])

	def testRespformat2(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "application/x-votable+xml",
			},
			['<DESCRIPTION>The latitude coordinate, lower limit</DESCRIPTION>'
				'<VALUES><MIN value="30.9831815872">',])

	@unittest.skip("Make trialhelpers.ArchiveTest use DCExceptionHandler")
	def testInvalidRespformat(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", {
				"ID": "ivo://x-unregistred/~?data/excube.fits",
				"RESPONSEFORMAT": "vnd-microsoft/xls"
			},
			["ValidationError: Field RESPONSEFORMAT: u'vnd-microsoft/xls'"
				" is not a valid value for RESPONSEFORMAT"])

	def testMetadataError(self):
		return self.assertGETHasStrings("/data/cores/dl/dlmeta", 
			{"ID": "ivo://x-unregistred/~?data/excube.fit"},
			["TR><TD>ivo://x-unregistred/~?data/excube.fit</TD><TD></TD><TD></TD><TD>"
				"NotFoundFault: accref 'data/excube.fit' could not be located"
				" in product table</TD>"])
	
	def testCubeCutout(self):
		return self.assertGETHasStrings("/data/cores/dl/dlget", {
			"ID": "ivo://x-unregistred/~?data/excube.fits",
			"COO_3_MIN": "3753"}, [
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
	
	def testAvailability(self):
		return self.assertGETHasStrings("/data/cores/dl/availability", {},
			["<avl:available>true</avl:available>"])

	def testCapabilities(self):
		return self.assertGETHasStrings("/data/cores/dl/capabilities", {}, [
			'standardID="ivo://ivoa.net/std/DataLink#links-1.0"',
			'/data/cores/dl/dlmeta</accessURL>',
			'<ucd>meta.id;meta.main</ucd>'])

	def testCleanedup(self):
		# this doesn't do any queries, it just makes sure that
		# the datalink services above cleaned up after themselves
		# (of course, we might see crap from the last run rather than
		# from this, but statistically it should catch trouble.
		pooLeft = glob.glob(
			os.path.join(api.getConfig("tempDir"), "fitstable*"))
		self.assertFalse(pooLeft, "Something left fitstable temporaries"
			" in tempDir")

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
				"COO_3_MIN": "3753"}
			).addCallback(checkPosted)
			

atexit.register(trialhelpers.provideRDData("test", "import_fitsprod"))
atexit.register(trialhelpers.provideRDData("ssatest", "test_import"))
