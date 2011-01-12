"""
Tests having to do with the registry code.
"""

# This is really hard to sensibly work out.  Sigh

import datetime
import os

from gavo import api
from gavo import base
from gavo import registry
from gavo import utils
from gavo.base import sqlsupport
from gavo.helpers import testhelpers
from gavo.registry import builders
from gavo.registry import capabilities
from gavo.registry import nonservice
from gavo.registry import oaiinter
from gavo.registry import publication
from gavo.utils import ElementTree

import tresc


class DeletedTest(testhelpers.VerboseTest):
	"""tests for deletion of record doing roughly what's necessary.
	"""
# All these things need to run in sequence.  Lousy.
	rdId = 'data/pubtest'

	resources = [("connection", tresc.dbConnection)]

	def _makeDeletedRecord(self):
		return base.makeStruct(nonservice.DeletedResource,
			resTuple={"sourceRD": "foo", "resId": "bar", "recTimestamp":
				datetime.datetime(2010, 10, 10, 10, 10, 10)})

	def testResob(self):
		dr = self._makeDeletedRecord()
		self.assertEqual(base.getMetaText(dr, "identifier"), 
			"ivo://%s/foo/bar"%base.getConfig("ivoa", "authority"))
		self.assertEqual(base.getMetaText(dr, "status"), "deleted")

	def testResrec(self):
		dr = self._makeDeletedRecord()
		oairec = builders.getVOResourceElement(dr).render()
		self.failUnless('<oai:header status="deleted"><oai:identifier>'
			'ivo://org.gavo.dc/foo/bar</oai:identifier><oai:datestamp>'
			'2010-10-10T10:10:10Z</oai:datestamp></oai:header></oai:record>'
			in oairec)

	def _createPublication(self):
		rd = api.getRD(self.rdId)
		publication.updateServiceList([rd], connection=self.connection)

	def _deletePublication(self):
		rd = api.getRD(self.rdId)
		del rd.services[0]
		publication.updateServiceList([rd], connection=self.connection)

	def _assertPublished(self):
		# see if oaiinter functions see new service
		yesterday = datetime.datetime.today()+ datetime.timedelta(days=-1)
		matches = [tup for tup in oaiinter.getMatchingRestups(
			{"from": yesterday.strftime(utils.isoTimestampFmt)}, 
				connection=self.connection)
			if tup["sourceRD"]==self.rdId]
		self.failUnless(len(matches)==1, "Publication did not write record.")
		match = matches[0]
		self.failUnless(
			(datetime.datetime.utcnow()-match["recTimestamp"]).seconds==0,
			"Stale publication record?  Your machine can't be that slow")

	def _assertUnpublished(self):
		yesterday = datetime.datetime.today()+ datetime.timedelta(days=-1)
		matches = [tup for tup in oaiinter.getMatchingRestups(
			{"from": yesterday.strftime(utils.isoTimestampFmt)}, 
				connection=self.connection)
			if tup["sourceRD"]==self.rdId]
		self.failUnless(len(matches)==1, "Unpublication deleted record.")
		match = matches[0]
		self.failUnless(match["deleted"],
			"Unpublication didn't set deleted flag.")
	
	def _assertCanBuildResob(self):
		restup = [tup for tup in oaiinter.getMatchingRestups(
			{}, connection=self.connection)
			if tup["sourceRD"]==self.rdId][0]
		resob = registry.getResobFromRestup(restup)
		self.assertEqual(resob.resType, "deleted")
		dcRepr = builders.getDCResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in dcRepr)
		self.failUnless("<oai:identifier>ivo://org.gavo.dc/data/pubtest/moribund<"
			in dcRepr)
		voRepr = builders.getVOResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in voRepr)
		self.failUnless("<oai:identifier>ivo://org.gavo.dc/data/pubtest/moribund<"
			in voRepr)

	def testBigAndUgly(self):
		self._createPublication()
		self._assertPublished()

		# Must work a second time, overwriting the old junk
		self._createPublication()
		self._assertPublished()

		# Now nuke the record
		self._deletePublication()
		self._assertUnpublished()

		# And create a resource object from it
		self._assertCanBuildResob()


class CapabilityTest(testhelpers.VerboseTest):
	def testTAP(self):
		capabilities._TMP_TAPREGEXT_HACK = True
		publication = api.getRD("//tap").getById("run").publications[0]
		publication.parent.addMeta("supportsModel", "Sample Model 1")
		publication.parent.addMeta("supportsModel.ivoId", "ivo://models/mod1")
		publication.parent.addMeta("supportsModel", "Sample Model 2")
		publication.parent.addMeta("supportsModel.ivoId", "ivo://models/mod2")
		res = capabilities.getCapabilityElement(publication).render()
		#os.popen("xmlstarlet fo", "w").write(res)
		# XXX TODO: think of better assertions
		self.failUnless('<dataModel' in res)
		capabilities._TMP_TAPREGEXT_HACK = False


class AuthorityTest(testhelpers.VerboseTest):
# This test will fail until defaultmeta.txt has the necessary entries
# and //services is published
	def testAuthorityResob(self):
		authId = "ivo://%s"%base.getConfig("ivoa", "authority")
		resob = registry.getResobFromIdentifier(authId)
		self.assertEqual(base.getMetaText(resob, "identifier"), authId)
		self.failIf(resob.getMeta("title") is None)
		self.failIf(resob.getMeta("datetimeUpdated") is None)
		self.failIf(resob.getMeta("recTimestamp") is None)
		self.assertEqual(base.getMetaText(resob, "sets"), "ivo_managed")
	
	def testAuthorityVORes(self):
		resob = registry.getResobFromIdentifier(
			"ivo://%s"%base.getConfig("ivoa", "authority"))
		resrec = builders.getVORMetadataElement(resob).render()
		tree = ElementTree.fromstring(resrec)
		self.assertEqual(tree.find("managingOrg").text, 
			"ivo://%s/org"%base.getConfig("ivoa", "authority"))
		self.failUnless('created="' in resrec)


if __name__=="__main__":
	testhelpers.main(AuthorityTest)
