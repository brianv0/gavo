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
from gavo.registry import oaiinter
from gavo.registry import publication

import tresc


class DeletedTest(testhelpers.VerboseTest):
	"""tests for deletion of record doing roughly what's necessary.
	"""
# All these things need to run in sequence.  Lousy.
	rdId = 'data/pubtest'

	resources = [("connection", tresc.dbConnection)]

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
			if tup["sourceRd"]==self.rdId]
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
			if tup["sourceRd"]==self.rdId]
		self.failUnless(len(matches)==1, "Unpublication deleted record.")
		match = matches[0]
		self.failUnless(match["deleted"],
			"Unpublication didn't set deleted flag.")
	
	def _assertCanBuildResob(self):
		restup = [tup for tup in oaiinter.getMatchingRestups(
			{}, connection=self.connection)
			if tup["sourceRd"]==self.rdId][0]
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
		self.failUnless('<dataModel ivoId="ivo://models/mod1">'
			'Sample Model 1</dataModel>' in res)
		capabilities._TMP_TAPREGEXT_HACK = False


if __name__=="__main__":
	testhelpers.main(CapabilityTest)
