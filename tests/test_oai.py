"""
Some (trial) tests for OAI; we're testing *our* client against *our*
server here, which is a bit pointless -- but only a bit.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import re
import time

from twisted.internet import reactor
from twisted.internet import threads

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import utils
from gavo.protocols import oaiclient
from gavo.registry import publication
from gavo.web import root

import trialhelpers


class _OAITest(trialhelpers.RenderTest):
	registry = "http://localhost:57707/oai.xml"

	def setUp(self):
		self.port = reactor.listenTCP(57707, root.site)
		self.renderer = root.root

	def tearDown(self):
		self.port.stopListening()


class OAIBasicTest(_OAITest):

	def _failNoExc(self, ignored):
		self.fail("An exception should have been raised here")

	def testBasicError(self):
		def checkError(failure):
			self.failUnless(isinstance(failure.value, oaiclient.FailedQuery))

		return threads.deferToThread(
			oaiclient.OAIQuery(self.registry, "foobar").talkOAI,
			oaiclient.IdParser
		).addCallback(self._failNoExc
		).addErrback(checkError)

	def testReponseDatestamp(self):
		def assertResponseDate(res):
			dt = datetime.datetime.utcnow()-utils.parseISODT(
				re.search("<oai:responseDate>(.*)</oai:responseDate>", 
				res).group(1))
			self.failIf(abs(dt.seconds)>10)

		return threads.deferToThread(
			oaiclient.OAIQuery(self.registry, 
				"ListIdentifiers", metadataPrefix="oai_dc").doHTTP
		).addCallback(assertResponseDate)

	def testGetRecords(self):

		def assertParsed(res):
			for rec in res:
				if rec["id"]=="ivo://x-unregistred/__system__/services/registry":
					break
			else:
				self.fail("No registry RR in list records response")
			self.assertEqual(rec["accessURL"][0], "http://localhost:8080/oai.xml")

		return threads.deferToThread(oaiclient.getRecords, self.registry
		).addCallback(assertParsed)

	def testGetIdentifiers(self):

		def assertParsed(res):
			for rec in res:
				if rec["id"]=="ivo://x-unregistred/__system__/services/registry":
					break
			else:
				self.fail("No registry RR in list records response")
			# Make sure IdParser is actually being used
			self.failIf("accessURL" in rec)

		return threads.deferToThread(oaiclient.getIdentifiers, self.registry
		).addCallback(assertParsed)

	def testResumption(self):
		# test robustness: don't fail even if someone has tinkered with services
		# in the last second.
		base.caches.getRD("//services").loadedAt -= 10
		q = oaiclient.OAIQuery(
			self.registry, "ListIdentifiers", metadataPrefix="oai_dc")
		q.maxRecords = 1
		# there must be at least two records (the registry and the authority)
		def assertResumptionHappened(res):
			self.failIf(len(res)<2)
			ids = set(rec["id"] for rec in res)
			for id in [
				"ivo://x-unregistred/__system__/services/registry",
				'ivo://x-unregistred']:
				self.failUnless(id in ids)
			self.assertEqual(len(ids), len(res), "Duplicate records with resumption")
				
		return threads.deferToThread(q.talkOAI, oaiclient.IdParser
		).addCallback(assertResumptionHappened)

	def testBadResumptionToken(self):
		q = oaiclient.OAIQuery(
			self.registry, "ListIdentifiers", metadataPrefix="oai_dc")

		def assertErrorCode(res):
			self.assertRaises(oaiclient.FailedQuery,
				oaiclient.sax.parseString, res, oaiclient.IdParser())

		return threads.deferToThread(q.doHTTP, resumptionToken="kaesekuchen"
		).addCallback(assertErrorCode)
	
	def testNoResumptionAfterReload(self):
		q = oaiclient.OAIQuery(
			self.registry, "ListIdentifiers", metadataPrefix="oai_dc")
		q.maxRecords = 1

		def assertErrorsOut(stuff):
			return self.failUnless(
				'code="badResumptionToken">Service table has changed'
				in stuff)

		def resumeNext(stuff):
			resumptionToken = re.search("resumptionToken>([^<]*)<", stuff).group(1)
			base.caches.getRD("//services").loadedAt = time.time()+2
			return threads.deferToThread(q.doHTTP, resumptionToken=resumptionToken
			).addCallback(assertErrorsOut)

		return threads.deferToThread(q.doHTTP).addCallback(resumeNext)

	def testIdentify(self):
		def assertParsed(serverProperties):
			self.assertEqual(serverProperties.granularity, "YYYY-MM-DDThh:mm:ssZ")
			self.assertEqual(serverProperties.repositoryName, 
				"Unittest Suite Registry")
			self.assertEqual(serverProperties.baseURL, 
				"http://localhost:8080/oai.xml")
			self.assertEqual(serverProperties.protocolVersion, "2.0")
			self.assertEqual(serverProperties.deletedRecord, "transient")
			self.assertEqual(serverProperties.adminEmails, 
				["invalid@whereever.else"])

		return threads.deferToThread(oaiclient.getServerProperties,
			self.registry).addCallback(assertParsed)

	def testListIdentifiers(self):
		return self.assertGETHasStrings("/oai.xml", {
				"verb": "ListIdentifiers", 
				"metadataPrefix": "oai_dc"}, [ 
				'oai:ListIdentifiers>',
				'ivo_managed'])



class OAIParameterTest(_OAITest):
	def testFromUntil(self):
		conn = base.getDBConnection("admin")
		rd = testhelpers.getTestRD("pubtest")
		publication.updateServiceList([rd], connection=conn)
		conn.commit()

		def assertNotInWithUntil(res):
			for rec in res:
				if rec["id"]=='ivo://x-unregistred/data/pubtest/moribund':
					self.fail("moribund service from pubtest in old svcs?")

			publication._purgeFromServiceTables("data/pubtest", conn)
			conn.commit()
			conn.close()

		def assertInWithFrom(res):
			for rec in res:
				if rec["id"]=='ivo://x-unregistred/data/pubtest/moribund':
					break
			else:
				self.fail("moribund service from pubtest not found in new svcs")
			return threads.deferToThread(oaiclient.getIdentifiers,
				self.registry,
				endDate=datetime.datetime.utcnow()-datetime.timedelta(seconds=10)
			).addCallback(assertNotInWithUntil)

		return threads.deferToThread(oaiclient.getIdentifiers,
			self.registry,
			startDate=datetime.datetime.utcnow()-datetime.timedelta(seconds=1)
		).addCallback(assertInWithFrom)

	def testSets(self):
		conn = base.getDBConnection("admin")
		rd = testhelpers.getTestRD("test")
		publication.updateServiceList([rd], connection=conn)
		conn.commit()

		def assertNotInIvo(res):
			for rec in res:
				if rec["id"]=='ivo://x-unregistred/data/test/basicprod':
					self.fail("basicprod service from test in ivo set?")

			publication._purgeFromServiceTables("data/test", conn)
			conn.commit()
			conn.close()

		def assertInLocal(res):
			for rec in res:
				if rec["id"]=='ivo://x-unregistred/data/test/basicprod':
					break
			else:
				self.fail("basicprod service from test not in local set?")

			return threads.deferToThread(oaiclient.getIdentifiers,
				self.registry,
				set="ivo_managed",
			).addCallback(assertNotInIvo)

		return threads.deferToThread(oaiclient.getIdentifiers,
			self.registry,
			set="local",
		).addCallback(assertInLocal)


class OAIContentCallbackTest(_OAITest):
	def testSavesResult(self):
		savedContent = []
		def save(stuff):
			savedContent.append(stuff)

		def assertSaved(svcResult):
			self.failUnless("<oai:repositoryName>Unittest" in savedContent[0])

		q = oaiclient.OAIQuery(self.registry, verb="Identify",
			metadataPrefix=None, contentCallback=save)
		return threads.deferToThread(q.talkOAI, oaiclient.IdentifyParser
			).addCallback(assertSaved)

	def testErrorIsNotSaved(self):
		savedContent = []
		def save(stuff):
			savedContent.append(stuff)

		def assertNotSaved(failure):
			self.failIf(savedContent)
		def failIfRan(whatever):
			self.fail("This should not have worked")

		q = oaiclient.OAIQuery(self.registry, verb="Schwumbel",
			contentCallback=save)
		return threads.deferToThread(q.talkOAI, oaiclient.IdentifyParser
			).addCallback(failIfRan
			).addErrback(assertNotSaved)


