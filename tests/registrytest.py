"""
Tests having to do with the registry code.
"""

# This is really hard to sensibly work out.  Sigh

import datetime 

from gavo import api
from gavo import base
from gavo import registry
from gavo import utils
from gavo.registry import builders
from gavo.registry import oaiinter
from gavo.registry import servicelist

import testhelpers


class DeletedTest(testhelpers.VerboseTest):
	"""tests for deletion of record doing roughly what's necessary.
	"""
# All these things need to run in sequence.  Lousy.

	srvTestRD = """
	<resource schema="test">
		<staticCore id="nullcore" file="forget"/>
		<meta name="title">foosv</meta>
		<meta name="creationDate">1970-01-01T05:20:00</meta>
		<meta name="description">The foo service</meta>
		<meta name="subject">Testing</meta>
		<service id="moribund" core="nullcore">
			<meta name="shortName">moribund</meta>
			<publish render="form" sets="ivo_managed"/>
		</service>
	</resource>"""

	def setUp(self):
		self.connection = base.getDBConnection(profile="test")
	
	def tearDown(self):
		self.connection.rollback()

	def _createPublication(self):
		rd = base.parseFromString(api.RD, self.srvTestRD)
		rd.sourceId = "test/test"
		servicelist.updateServiceList([rd], connection=self.connection)

	def _deletePublication(self):
		rd =  base.parseFromString(api.RD, "<resource schema='test'/>")
		rd.sourceId = "test/test"
		servicelist.updateServiceList([rd], connection=self.connection)

	def _assertPublished(self):
		# see if oaiinter functions see new service
		yesterday = datetime.date.today()+ datetime.timedelta(days=-1)
		matches = [tup for tup in oaiinter.getMatchingRestups(
			{"from": yesterday.isoformat()}, connection=self.connection)
			if tup["sourceRd"]=='test/test']
		self.failUnless(len(matches)==1, "Publication did not write record.")
		match = matches[0]
		self.failUnless(
			(datetime.datetime.utcnow()-match["recTimestamp"]).seconds==0,
			"Stale publication record?  Your machine can't be that slow")

	def _assertUnpublished(self):
		yesterday = datetime.date.today()+ datetime.timedelta(days=-1)
		matches = [tup for tup in oaiinter.getMatchingRestups(
			{"from": yesterday.isoformat()}, connection=self.connection)
			if tup["sourceRd"]=='test/test']
		self.failUnless(len(matches)==1, "Unpublication deleted record.")
		match = matches[0]
		self.failUnless(match["deleted"],
			"Unpublication didn't set deleted flag.")
	
	def _assertCanBuildResob(self):
		restup = [tup for tup in oaiinter.getMatchingRestups(
			{}, connection=self.connection)
			if tup["sourceRd"]=='test/test'][0]
		resob = registry.getResobFromRestup(restup)
		self.assertEqual(resob.resType, "deleted")
		dcRepr = builders.getDCResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in dcRepr)
		self.failUnless("<oai:identifier>ivo://org.gavo.dc/test/test/moribund<"
			in dcRepr)
		voRepr = builders.getVOResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in voRepr)
		self.failUnless("<oai:identifier>ivo://org.gavo.dc/test/test/moribund<"
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


if __name__=="__main__":
	testhelpers.main(DeletedTest)
