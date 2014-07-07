"""
Tests having to do with the registry code.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import os

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import registry
from gavo import rscdesc
from gavo import rscdef
from gavo import utils
from gavo.base import meta
from gavo.helpers import testtricks
from gavo.registry import builders
from gavo.registry import common
from gavo.registry import capabilities
from gavo.registry import nonservice
from gavo.registry import oaiinter
from gavo.registry import publication
from gavo.utils import ElementTree
from gavo.registry.model import OAI

import tresc


def getGetRecordResponse(resob):
	"""returns XML and parsedXML as returned from an OAI getRecord 
	call that retrieves resob.
	"""
	pars = {"verb": "GetRecord", "metadataPrefix": "ivo_vor"}
	source = OAI.PMH[
		oaiinter.getResponseHeaders(pars),
		builders.getVOGetRecordElement(resob)].render()
	return source, testhelpers.getXMLTree(source, debug=False)


class RegistryModelTest(testhelpers.VerboseTest):
	def testVSNamespaces(self):
		from gavo.registry import model
		self.assertEqual(model.VS0.ucd()._prefix, "vs0")
		self.assertEqual(model.VS.ucd()._prefix, "vs")

	def testVOTableDataType(self):
		from gavo.registry import model
		self.assertEqual(
			testhelpers.cleanXML(model.VS.voTableDataType["char"].render()),
			'<dataType arraysize="1" xsi:type="vs:VOTableType">char</dataType>')
		self.assertEqual(
			testhelpers.cleanXML(model.VS.voTableDataType["text"].render()),
			'<dataType arraysize="*" xsi:type="vs:VOTableType">char</dataType>')
		self.assertEqual(
			testhelpers.cleanXML(model.VS.voTableDataType["integer[20]"].render()),
			'<dataType arraysize="20" xsi:type="vs:VOTableType">int</dataType>')


class DeletedTest(testhelpers.VerboseTest):
	"""tests for deletion of record doing roughly what's necessary.
	"""
# All these things need to run in sequence.  Lousy.
	rdId = 'data/pubtest'

	resources = [("connection", tresc.dbConnection)]

	def tearDown(self):
		publication._purgeFromServiceTables(self.rdId, self.connection)
		self.connection.commit()

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
			'ivo://x-unregistred/foo/bar</oai:identifier><oai:datestamp>'
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
			{"from": yesterday.strftime(utils.isoTimestampFmt)})
			if tup["sourceRD"]==self.rdId]
		self.failUnless(len(matches)==1, "Publication did not write record.")
		match = matches[0]
		self.failUnless(
			(datetime.datetime.utcnow()-match["recTimestamp"]).seconds==0,
			"Stale publication record?  Your machine can't be that slow")

	def _assertUnpublished(self):
		yesterday = datetime.datetime.today()+ datetime.timedelta(days=-1)
		matches = [tup for tup in oaiinter.getMatchingRestups(
			{"from": yesterday.strftime(utils.isoTimestampFmt)})
			if tup["sourceRD"]==self.rdId]
		self.failUnless(len(matches)==1, "Unpublication deleted record.")
		match = matches[0]
		self.failUnless(match["deleted"],
			"Unpublication didn't set deleted flag.")
	
	def _assertCanBuildResob(self):
		restup = [tup for tup in oaiinter.getMatchingRestups({})
			if tup["sourceRD"]==self.rdId][0]
		resob = registry.getResobFromRestup(restup)
		self.assertEqual(resob.resType, "deleted")
		dcRepr = builders.getDCResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in dcRepr)
		self.failUnless("<oai:identifier>ivo://x-unregistred/data/pubtest/moribund<"
			in dcRepr)
		voRepr = builders.getVOResourceElement(resob).render()
		self.failUnless('<oai:header status="deleted"' in voRepr)
		self.failUnless("<oai:identifier>ivo://x-unregistred/data/pubtest/moribund<"
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
		# XXX TODO: think of better assertions
		self.failUnless('<dataModel' in res)
		capabilities._TMP_TAPREGEXT_HACK = False


class _SSACapabilityElement(testhelpers.TestResource):
	def make(self, deps):
		publication = testhelpers.getTestRD("ssatest"
			).getById("s").publications[0]
		res = capabilities.getCapabilityElement(publication).render()
		#os.popen("xmlstarlet fo", "w").write(res)
		return res, ElementTree.fromstring(res)


class SSAPCapabilityTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("textAndTree", _SSACapabilityElement())]

	def testValid(self):
		self.assertValidates(self.textAndTree[0])
	
	def testCapabilityAttributes(self):
		tree = self.textAndTree[1]
		self.assertEqual(tree.attrib["standardID"], 'ivo://ivoa.net/std/SSA')
		self.assertEqual(
			tree.attrib['{http://www.w3.org/2001/XMLSchema-instance}type'],
			'ssap:SimpleSpectralAccess')
	
	def testInterfaceIsStandard(self):
		intf = self.textAndTree[1].find("interface")
		self.assertEqual(intf.attrib["role"], "std")
	
	def testInterfaceHasStandardParam(self):
		for paramEl in self.textAndTree[1].findall("interface/param"):
			if paramEl.find("name").text=="BAND":
				break
		else:
			raise AssertionError("No BAND input parameter in SSAP interface")
		self.assertEqual(paramEl.attrib["std"], "true")
		self.assertEqual(paramEl.find("unit").text, "m")
	
	def testInterfaceHasLocalParam(self):
		for paramEl in self.textAndTree[1].findall("interface/param"):
			if paramEl.find("name").text=="excellence":
				break
		else:
			raise AssertionError("No excellence input parameter in SSAP interface")
		self.assertEqual(paramEl.attrib["std"], "false")
		self.assertEqual(paramEl.find("description").text, "random number")

	def testMaxRecordsReflectsConfig(self):
		self.assertEqual(int(self.textAndTree[1].find("maxRecords").text),
			base.getConfig("ivoa", "dalHardLimit"))

	def testTestQuery(self):
		self.assertEqual(self.textAndTree[1].find("testQuery/queryDataCmd").text,
			"TARGETNAME=alpha%20Boo&REQUEST=queryData")

	def testRecordCreationFailsOnMissingMeta(self):
		publication = testhelpers.getTestRD("ssatest"
			).getById("s").publications[0]
		publication.parent.delMeta("ssap.testQuery")
		self.assertRaisesWithMsg(base.NoMetaKey,
			"No meta item ssap.testQuery",
			capabilities.getCapabilityElement,
			(publication,))

	def testNestedMeta(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "data", "tmp.rd"),
			"""<resource schema="test" resdir=".">
				<service id="t" original="data/ssatest#s">
				<publish render="ssap.xml"/>
				<meta name="ssap">
					<meta name="dataSource">you bet</meta>
					<meta name="testQuery">HAHA.</meta>
				</meta></service></resource>"""):
			res = capabilities.getCapabilityElement(testhelpers.getTestRD("tmp"
				).getById("t").publications[0]).render()
			self.failUnless('<dataSource>you bet</dataSource>' in res)


class _SIACapabilityElement(testhelpers.TestResource):
	def make(self, deps):
		publication = testhelpers.getTestRD("test"
			).getById("pgsiapsvc").publications[0]
		res = capabilities.getCapabilityElement(publication).render()
		return res, testhelpers.getXMLTree(res, debug=False)


class SIAPCapabilityTest(testhelpers.VerboseTest):
	resources = [("txNTree", _SIACapabilityElement())]

	def testNoEmptyMax(self):
		self.failIf(self.txNTree[1].xpath("//maxImageExtent/lat"),
			"maxImageExtent/lat should be empty but is not")

	def testNoFilledMax(self):
		self.assertEqual(
			self.txNTree[1].xpath("//maxImageExtent/long")[0].text,
			"10")
	
	def testImageSizeAtomic(self):
		children = self.txNTree[1].xpath("//maxImageSize")
		self.assertEqual(len(children), 1)
		self.assertEqual(children[0].text, "3000")

	def testTestQuery(self):
		tqEl = self.txNTree[1].xpath("/capability/testQuery")[0]
		self.assertEqual(len(tqEl), 2)
		longs = tqEl.xpath("*/long")
		self.assertEqual([l.text for l in longs], ["10", "0.4"])


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


class _StandardsRec(testhelpers.TestResource):
	def make(self, ignored):
		class Container(meta.MetaMixin):
			resType = "standard"
			rd = base.caches.getRD("//services")
		container = Container()
		container.setMetaParent(container.rd)

		meta.parseMetaStream(container, """
			recTimestamp: 2010-10-10T10:10:10Z
			sets: ivo_managed
			status: active
			title: a test standard
			subject: testing
			referenceURL: http://bar
			identifier: ivo://foo.bar
			endorsedVersion: 1.1
			endorsedVersion.status: wd
			endorsedVersion.use: preferred
			endorsedVersion: 1.0
			endorsedVersion.status: rec
			endorsedVersion.use: deprecated
			deprecated: rather use something else
			key:
			key.name: bar1
			key.description: This one's open
			key:
			key.name: bar2
			key.description: This one's closed
			""")
		return getGetRecordResponse(container)
	

class StandardsTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("srcAndTree", _StandardsRec())]
	
	def testIsValid(self):
		self.assertValidates(self.srcAndTree[0])

	def testTwoEndorsedVersions(self):
		self.assertEqual(len(self.srcAndTree[1].xpath("//endorsedVersion")), 2)
	
	def testEndorsedVersionMetaPresent(self):
		el = self.srcAndTree[1].xpath("//endorsedVersion")[0]
		self.assertEqual(el.get("status"), "wd")
		self.assertEqual(el.get("use"), "preferred")
		self.assertEqual(el.text, "1.1")
	
	def testDeprecated(self):
		self.assertEqual(self.srcAndTree[1].xpath("//deprecated")[0].text,
			"rather use something else")

	def testTwoKeys(self):
		self.assertEqual(len(self.srcAndTree[1].xpath("//key")), 2)

	def testKeyStructure(self):
		el = self.srcAndTree[1].xpath("//key")[0]
		self.assertEqual(el[0].tag, "name")
		self.assertEqual(el[0].text, "bar1")
		self.assertEqual(el[1].tag, "description")
		self.assertEqual(el[1].text, "This one's open")


class _DocRec(testhelpers.TestResource):
	def make(self, ignored):
		class Container(meta.MetaMixin):
			resType = "document"
			rd = base.caches.getRD("//services")
		container = Container()
		container.setMetaParent(container.rd)

		meta.parseMetaStream(container, """
			recTimestamp: 2010-10-10T10:10:10Z
			sets: ivo_managed
			status: active
			title: a test document
			subject: testing
			referenceURL: http://bar/doc/fancy
			identifier: ivo://foo.bar
			language: en
			language: de
			accessURL: http://bar/doc/fancy/doc
			accessURL: http://foo/fancy/doc
			sourceURI: http://foo/fancy/src
			uses: Sample useful resource
			uses.ivoId: ivo://useful/sample1
			uses: Crapola junkyard bad example
			uses.ivoId: ivo://crapola/work
			""")
		return getGetRecordResponse(container)
	

class DocumentResTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("srcAndTree", _DocRec())]
	
	def testIsValid(self):
		self.assertValidates(self.srcAndTree[0])
	
	def testLanguages(self):
		langs = self.srcAndTree[1].xpath("//language")
		self.assertEqual(len(langs), 2)
		self.assertEqual(langs[0].text, "en")
		self.assertEqual(langs[1].text, "de")

	def testAccessURLs(self):
		urls = self.srcAndTree[1].xpath("//accessURL")
		self.assertEqual(len(urls), 2)
		self.assertEqual(urls[1].text, "http://foo/fancy/doc")
	
	def testSourceURI(self):
		urls = self.srcAndTree[1].xpath("//sourceURI")
		self.assertEqual(len(urls), 1)

	def testRelationships(self):
		relations = self.srcAndTree[1].xpath("//relationship")
		self.assertEqual(len(relations), 1)
		t = relations[0].xpath("relationshipType")[0]

		# until VOResource is fixed, we turn "uses" into related-to
		self.assertEqual(t.text, "related-to")
		ids = relations[0].xpath("relatedResource")
		self.assertEqual(ids[0].text, "Sample useful resource")
		self.assertEqual(ids[1].attrib["ivo-id"], "ivo://crapola/work")


class DataPublicationMetaTest(testhelpers.VerboseTest):
# Tests concerning metadata handling with the table data registry interface
	resources = [("conn", tresc.dbConnection)]

	def testMinimalMeta(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			<table id="ronk">
				<register sets="ivo_managed,local"/>
			</table></resource>""")
		self.assertRaisesWithMsg(base.MetaValidationError,
			"Meta structure on ronk did not validate:"
			" Meta key title missing, Meta key creationDate missing,"
			" Meta key description missing, Meta key subject missing",
			list,
			(publication._rdRscRecGrammar.parse(rd),))

	_minimalMeta = """
			<meta>
				title:x
				creationDate:y
				description:z
				subject:a
				referenceURL:b
			</meta>"""

	def testIterDataTable(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			%s
			<table id="ronk"><register sets="ivo_managed,local"/>
			</table></resource>"""%self._minimalMeta)
		recs = list(publication._rdRscRecGrammar.parse(rd))
		self.assertEquals(len(recs), 5)
		self.assertEquals(recs[0][0], "resources")
		self.assertEquals(recs[0][1]["resId"], "ronk")
		self.assertEquals(recs[1][1]["setName"], "ivo_managed")
		self.assertEquals(recs[2][1]["setName"], "local")
		self.assertEquals(recs[3][0], "subjects")

	def testIterDataData(self):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			%s
			<table id="ronk"/><table id="funk"/>
			<data id="ronkcoll"><register sets="ivo_managed,local"/>
			<make table="ronk"/><make table="funk"/>
			</data></resource>"""%self._minimalMeta)
		recs = list(publication._rdRscRecGrammar.parse(rd))
		self.assertEquals(len(recs), 5)
		self.assertEquals(recs[0][0], "resources")
		self.assertEquals(recs[0][1]["resId"], "ronkcoll")
		self.assertEquals(recs[1][1]["setName"], "ivo_managed")
		self.assertEquals(recs[2][1]["setName"], "local")
		self.assertEquals(recs[3][0], "subjects")
		self.assertEquals(recs[4][0], "authors")
		self.assertEquals(recs[4][1]["author"], "Could be same as contact.name")

	def testRejectedWithoutId(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<resource schema="data">\\n\\...], (3, 3):'
			" Published tables need an assigned id.",
			base.parseFromString,
			(rscdesc.RD, """<resource schema="data">
			<table><register sets="ivo_managed,local"/>
			</table></resource>"""))

	def testDataPublicationPurged(self):
		# this is actually a companion to DataPublicationTest making sure
		# that _PublishedData's clean method has worked, possibly last time.
		# Sorry 'bout that funkyness, but this is tricky to do sanely.
		q = base.UnmanagedQuerier(connection=self.conn)
		self.assertEqual(len(list(
			q.query("SELECT * FROM dc.resources where sourcerd=%(rdId)s",
				{"rdId": _PublishedData.rdId}))), 0, 
				"registrytest._PublishedData.clean failed?")
		self.assertEqual(
			common.getDependencies("__system__/services", connection=self.conn),
			[],
			"registrytest._PublishedData.clean failed?")


class _ResobGrammarResponse(testhelpers.TestResource):
	"""A resource giving the records the grammar in registry.publication
	spits out for a simple resource.
	"""
	def make(self, deps):
		tables = {}
		rd = base.caches.getRD("data/ssatest")
		for destTable, row in publication._rdRscRecGrammar.parse(rd):
			del row["parser_"]
			tables.setdefault(destTable, []).append(row)
		return tables


class ResobGrammarTest(testhelpers.VerboseTest):
	resources = [("tables", _ResobGrammarResponse())]

	def testServicePresent(self):
		self.assertEqual(self.tables["resources"][0]["ivoid"],
			'ivo://x-unregistred/data/ssatest/s')
	
	def testSubjects(self):
		self.assertEqual(self.tables["subjects"],
			[{'sourceRD': 'data/ssatest', 'resId': u's', 'subject': 'Testing'}])
	
	def testAuthors(self):
		self.assertEqual(
			set([r["author"] for r in self.tables["authors"]]),
			set(['Hendrix, J.', 'Page, J', 'The Master Tester']))


class _PublishedRD(testhelpers.TestResource):
	"""A resource that publishes all the stuff from an RD for while the
	resource exists.

	The RD to be published is given in the rdId class attribute.
	"""
	resources = [("conn", tresc.dbConnection)]

	def make(self, deps):
		self.conn = deps["conn"]
		rd = base.caches.getRD(self.rdId)
		publication.updateServiceList([rd], connection=self.conn)
		return rd
	
	def clean(self, res):
		publication._purgeFromServiceTables(self.rdId, self.conn)
		self.conn.commit()


class _PublishedData(_PublishedRD):
	rdId = "data/testdata"


class DataPublicationTest(testhelpers.VerboseTest):
# Tests for a published table
	resources = [
		("conn", tresc.dbConnection),
		("pubDataRD", _PublishedData())]

	def testPublication(self):
		q = base.UnmanagedQuerier(connection=self.conn)
		self.assertEqual(len(list(
			q.query("SELECT * FROM dc.resources where sourcerd=%(rdId)s",
				{"rdId": self.pubDataRD.sourceId}))), 1)
	
	def testResobGeneration(self):
		td = self.pubDataRD.getById("barsobal")
		ivoId = base.getMetaText(td, "identifier")
		resOb = registry.getResobFromIdentifier(ivoId)
		self.assertEqual(td, resOb)
	
	def testIsInDependencies(self):
		self.assertEqual(
			registry.getDependencies("__system__/services", connection=self.conn),
			["data/testdata"])


class _ServiceVORRecord(testhelpers.TestResource):
	def make(self, ignored):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			<meta name="creationDate">2011-03-04T11:00:00</meta>
			<meta name="title">A sensless service</meta>
			<meta name="source">1989AGAb....2...33W</meta>
			<service id="glonk">
				<nullCore/>
				<outputTable>
					<column name="score"/>
				</outputTable>
				<publish render="form" sets="ivo_managed,local"/>
			</service></resource>""")
		rd.sourceId = "funky/town"
		base.caches.getRD.cacheCopy["funky/town"] = rd
		tree = testhelpers.getXMLTree(
			builders.getVOResourceElement(rd.services[0]).render(), debug=False)
		return tree.xpath("metadata/Resource")[0]

_serviceVORRecord = _ServiceVORRecord()


class ServiceRecordTest(testhelpers.VerboseTest):
	resources = [("rec", _serviceVORRecord)]

	def testSourceFormatInferred(self):
		self.assertEqual(self.rec.xpath("content/source")[0].get("format"),
			"bibcode")


class _TableVORRecord(testhelpers.TestResource):
	def make(self, ignored):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			<meta name="creationDate">2011-03-04T11:00:00</meta>
			<meta name="title">My first DataCollection</meta>
			<table id="punk">
				<column name="oink" utype="noises:animal.pig"/>
				<column name="where" type="spoint" ucd="pos.eq;source"/>
				<register sets="ivo_managed,local"/>
				<meta name="utype">testing.table.name</meta>
				<meta name="description">Some silly test data</meta>
				<meta name="subject">testing</meta>
				<meta name="subject">regressions</meta>
				<meta name="coverage.profile">Box ICRS 12 13 2 3</meta>
				<meta name="coverage.waveband">X-Ray</meta>
				<meta name="coverage.waveband">Radio</meta>
				<meta name="coverage.regionOfRegard">3</meta>
				<meta name="format">audio/vorbis</meta>
				<meta name="referenceURL">http://junk.g-vo.org</meta>
				<meta name="servedBy" ivoId="ivo://org.g-vo.junk/tap"
					>GAVO TAP service</meta>
				<meta name="servedBy" ivoId="ivo://org.g-vo.junk/adql"
					>GAVO ADQL Web</meta>
			</table></resource>""")
		rd.sourceId = "funky/town"
		td = rd.tables[0]
		tree = testhelpers.getXMLTree(
			builders.getVOResourceElement(td).render(), debug=False)
		return tree.xpath("metadata/Resource")[0]

_tableVORRecord = _TableVORRecord()


class TablePublicationRecordTest(testhelpers.VerboseTest):
# Tests for the registry record of a data publication
	resources = [("tree", _tableVORRecord)]

	def testCreatedInherited(self):
		self.assertEqual(self.tree.attrib["created"], "2011-03-04T11:00:00")
	
	def testConfigMetaPresent(self):
		self.assertEqual(
			self.tree.xpath("curation/contact/email")[0].text, 
			base.getMetaText(meta.configMeta, "contact.email"))
	
	def testVORModelWorked(self):
		self.assertEqual(
			self.tree.xpath("content/description")[0].text, 
			"Some silly test data")

	def testVORModelWorked2(self):
		self.assertEqual(self.tree.xpath("title")[0].text,
			"My first DataCollection")

	def testAllSubjectsRendered(self):
		self.assertEqual(len(self.tree.xpath("content/subject")), 2)
	
	def testDataMetaRendered(self):
		self.assertEqual(self.tree.xpath("format")[0].text, "audio/vorbis")
	
	def testCoverageProfileRendered(self):
		self.assertEqual(self.tree.xpath(
			"coverage/STCResourceProfile/AstroCoordArea/Box/Size/C1")[0].text, 
			"2.0")

	def testWavebandsPresent(self):
		bands = self.tree.xpath("coverage/waveband")
		self.assertEqual(len(bands), 2)
		self.assertEqual(bands[0].text, "X-Ray")

	def testRegionOfRegardPresent(self):
		self.assertEqual(self.tree.xpath("coverage/regionOfRegard")[0].text,
			"3")

	def testTablesetRendered(self):
		self.assertEqual(self.tree.xpath("tableset/schema/table/name")[0].text,
			"data.punk")
	
	def testColumnMetaRendered(self):
		self.assertEqual(
			self.tree.xpath("tableset/schema/table/column")[0
				].xpath("name")[0].text,
			"oink")

	def testRelationship(self):
		par = self.tree.xpath("//relationship")[0]
		self.assertEqual(par.xpath("relationshipType")[0].text, "served-by")
		self.assertEqual(par.xpath("relatedResource")[0].text,
			"GAVO TAP service")
		self.assertEqual(par.xpath("relatedResource")[0].attrib["ivo-id"],
			"ivo://org.g-vo.junk/tap")
		self.assertEqual(par.xpath("relatedResource")[1].attrib["ivo-id"],
			"ivo://org.g-vo.junk/adql")

	def testUtype(self):
		self.assertEqual(self.tree.xpath("tableset/schema/table/utype")[0].text,
			"testing.table.name")


class _DataGetRecordRes(testhelpers.TestResource):
	def make(self, ignored):
		rd = base.parseFromString(rscdesc.RD, """<resource schema="data">
			<meta name="creationDate">2011-03-04T11:00:00</meta>
			<meta name="title">My first DataCollection</meta>
			<table id="honk">
				<column name="col1" description="column from honk"/>
			</table>
			<table id="funk">
				<column name="oink" utype="noises:animal.pig"/>
				<column name="where" type="spoint" ucd="pos.eq;source"/>
			</table>
			<data id="punk">
				<register sets="ivo_managed,local"/>
				<meta name="description">Some silly test data</meta>
				<meta name="subject">testing</meta>
				<meta name="subject">regressions</meta>
				<meta name="coverage.profile">Box ICRS 12 13 2 3</meta>
				<meta name="format">audio/vorbis</meta>
				<meta name="referenceURL">http://junk.g-vo.org</meta>
				<make table="honk"/>
				<make table="funk"/>
			</data></resource>""")
		rd.sourceId = "funky/town"
		return getGetRecordResponse(rd.dds[0])

_dataGetRecordRes = _DataGetRecordRes()


class DataGetRecordTest(testhelpers.VerboseTest, testtricks.XSDTestMixin):
	resources = [("srcAndTree", _dataGetRecordRes)]

	def testIsValid(self):
		self.assertValidates(self.srcAndTree[0])


# minimal meta for successful RR generation without a (working) RD
_fakeMeta ="""<meta name="identifier">ivo://gavo.testing</meta>
<meta name="datetimeUpdated">2000-00-00T00:00:00</meta>
<meta name="referenceURL">http://faked</meta>
<meta name="recTimestamp">2000-00-00T00:00:00</meta>
<meta name="sets">ivo_managed</meta>"""


class RelatedTest(testhelpers.VerboseTest):
# Tests for everything to do with the "related" meta
	def _getTreeFor(self, dataBody):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test"><table id="foo">%s%s</table></resource>"""%(
				dataBody, _fakeMeta))
		td = rd.tables[0]
		return testhelpers.getXMLTree(
			builders.getVOResourceElement(td).render(), debug=False)

	def testNoRelations(self):
		tree = self._getTreeFor("")
		self.failIf(tree.xpath("metadata/Resource/content/relationship"))

	def testSimpleRelation(self):
		tree = self._getTreeFor(
			'<meta name="servedBy" ivoId="ivo://glub">The Glub Data</meta>')
		relEl = tree.xpath("metadata/Resource/content/relationship")
		self.failUnless(relEl)
		self.assertEqual(relEl[0].xpath("relationshipType")[0].text,
			"served-by")
		self.assertEqual(relEl[0].xpath("relatedResource")[0].text,
			"The Glub Data")
		self.assertEqual(relEl[0].xpath("relatedResource")[0].attrib["ivo-id"],
			"ivo://glub")

	def testReset(self):
		tree0 = self._getTreeFor(
			'<meta name="servedBy" ivoId="ivo://glub">The Glub Data</meta>')
		tree1 = self._getTreeFor(
			'<meta name="servedBy" ivoId="ivo://frob">The Frob Data</meta>')
		# we once had a bug where the builder didn't get reset, and due to
		# bad arch I think it'll come again.  Therefore this test -- it
		# will catch this.
		self.assertEqual(len(tree1.xpath(
			"metadata/Resource/content/relationship/relatedResource")), 1)

	def testRegistration(self):
		try:
			tree = self._getTreeFor(
				'<register services="//adql#query"/>')
			relEl = tree.xpath("metadata/Resource/content/relationship")
			self.failUnless(relEl)
			self.assertEqual(relEl[0].xpath("relationshipType")[0].text,
				"served-by")
			self.assertEqual(relEl[0].xpath("relatedResource")[0].attrib["ivo-id"],
				"ivo://%s/__system__/adql/query"%base.getConfig("ivoa", "authority"))

			# also check metadata on the exposing end
			svc = base.caches.getRD("//adql").getById("query")
			svcTree = testhelpers.getXMLTree(
				builders.getVOResourceElement(svc).render(), debug=False)
			for rel in svcTree.xpath("metadata/Resource/content/relationship"):
				if rel.xpath("relationshipType")[0].text=="service-for":
					for dest in rel.xpath("relatedResource"):
						if dest.attrib.get("ivo-id")=="ivo://gavo.testing":
							return
			# Fallthrough: The reference to our test service has not been found
			fail("Data registration did not leave service-for meta")
		finally:
			# clear adql entry in cache since we've changed it
			base.caches.clearForName("//adql")


class IdResolutionTest(testhelpers.VerboseTest):
	auth = base.getConfig("ivoa", "authority")

	def testNormal(self):
		# (id is rdid/id)
		svc = registry.getResobFromIdentifier(
			"ivo://%s/__system__/services/overview"%self.auth)
		self.assertEqual(svc.outputTable.columns[0].name, "sourceRD")

	def testAuthority(self):
		rec = registry.getResobFromIdentifier("ivo://%s"%self.auth)
		self.failUnless(isinstance(rec, registry.nonservice.ResRec))
		self.assertEqual(registry.getResType(rec), "authority")
		self.failUnless(base.getMetaText(rec, "description").startswith(
			" \\metaString{authority.description}{UNCONFIGURED}"))
	
	def testOrganization(self):
		rec = registry.getResobFromIdentifier("ivo://%s/org"%self.auth)
		self.failUnless(isinstance(rec, registry.nonservice.ResRec))
		self.assertEqual(registry.getResType(rec), "organization")
		self.assertEqual(base.getMetaText(rec, "referenceURL"),
			"http://your.institution/home")

	def testBadId(self):
		self.assertRaises(registry.IdDoesNotExist,
			registry.getResobFromIdentifier,
			"ivo://junk/blastes")


class ListRecordsTest(testhelpers.VerboseTest):
	def testRecords(self):
		tree = testhelpers.getXMLTree(
			oaiinter.runPMH({"verb": "ListIdentifiers", "metadataPrefix": "ivo_vor"},
				oaiinter.RegistryCore.builders).render())
		res = set(el.text for el in tree.xpath("//identifier"))
		expected = set([
			"ivo://x-unregistred/__system__/services/registry",
			"ivo://x-unregistred",
			"ivo://x-unregistred/org"])
		self.assertEqual(res&expected, expected)


class OAIParameterTest(testhelpers.VerboseTest):
	def testEqualGranularityEnforced(self):
		self.assertRaisesWithMsg(oaiinter.BadArgument,
			"from",
			oaiinter.runPMH,
			({"verb": "ListIdentifiers", "metadataPrefix": "ivo_vor",
				"from": "2010-10-10", "until": "2011-10-10T10:10:10Z"},
				oaiinter.RegistryCore.builders))


class ResumptionTokenTest(testhelpers.VerboseTest):
	def testBasic(self):
		pars = {"verb": "listSets"}
		pars["resumptionToken"] = oaiinter.makeResumptionToken(pars, 20)
		newPars = oaiinter.parseResumptionToken(pars)
		self.assertEqual(pars["verb"], newPars["verb"])
		self.assertEqual(newPars["resumptionToken"], 20)
		

	def testBadTokenFailsProperly(self):
		self.assertRaisesWithMsg(oaiinter.BadResumptionToken,
			"Odd-length string",
			oaiinter.parseResumptionToken,
			({"resumptionToken": "xyz"},))


class MetaExpandedTest(testhelpers.VerboseTest):
	def testWithTAPRecord(self):
		rd = base.caches.getRD("//tap")
		rec = publication.iterSvcRecs(rd.services[0]).next()[-1]
		self.failUnless(rec["description"].startswith(
			"The Unittest Suite's TAP end point. The Table Access"))
		self.assertEqual(rec["shortName"], "DaCHS standin TAP")


class ResourceLocationTest(testhelpers.VerboseTest):
	def testCaseyTableNamesOk(self):
		self.assertEqual(registry.getTableDef("ivoa.obsCore").getQName(), 
			"ivoa.ObsCore")


class _OtherServiceRRTree(testhelpers.TestResource):
	def make(self, deps):
		rd = base.parseFromString(rscdesc.RD, """
			<resource schema="test">
				<meta name="datetimeUpdated">2000-00-00T00:00:00</meta>
				<meta name="referenceURL">http://faked</meta>
				<service id="web">
					<meta name="title">Web service</meta>
					<publish render="form" sets="local"/>
					<nullCore/></service>
				<service id="scs" allowed="scs.xml">
					<meta name="title">SCS service</meta>
					<meta name="testQuery.ra">1</meta>
					<meta name="testQuery.dec">1</meta>
					<meta name="testQuery.sr">1</meta>
					<publish render="scs.xml" sets="ivo_managed"/>
					<publish render="form" sets="ivo_managed" service="web"/>
					<nullCore/></service></resource>
				""")
		rd.sourceId = "k"
		return testhelpers.getXMLTree(
			builders.getVOResourceElement(rd.services[1]).render(), debug=False)


class OtherServiceTest(testhelpers.VerboseTest):
# tests for having a service attribute in a publish record
	resources = [("tree", _OtherServiceRRTree())]

	def testSCSCapability(self):
		self.assertEqual(self.tree.xpath("//capability[1]/interface/accessURL"
				)[0].text,
			"http://localhost:8080/k/scs/scs.xml?")

	def testWebCapability(self):
		self.assertEqual(self.tree.xpath("//capability[2]/interface/accessURL"
				)[0].text,
			"http://localhost:8080/k/web/form")


if __name__=="__main__":
	testhelpers.main(OtherServiceTest)
