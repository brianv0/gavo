"""
Tests for SODA functionality.

There's a lot of tests like these in productstest, but for the old,
atomic parameter-style dlget stuff.  This should go ca. 2017.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from cStringIO import StringIO
import gc
import os
import unittest

from nevow.testutil import FakeRequest

from gavo.helpers import testhelpers

from gavo import api
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo import votable
from gavo.rscdef import regtest
from gavo.protocols import datalink
from gavo.protocols import products
from gavo.protocols import soda
from gavo.utils import fitstools

import tresc

class SODAElementTest(testhelpers.VerboseTest):
	resources = [("prodtestTable", tresc.prodtestTable)]
	parent = None

	def testMetaMakerSyntaxError(self):
		mm = api.parseFromString(datalink.MetaMaker,
			'<metaMaker>\n'
			' <code>\n'
			'	print return\n'
			' </code>\n'
			'</metaMaker>\n')
		self.assertRaisesWithMsg(
			api.BadCode,
			regtest.EqualingRE(r"Bad source code in function \(invalid syntax"
				r" \(<generated code \d+>, line 4\)\)"),
			mm.compile,
			(self,))

	def testStandardDescGenWorks(self):
		ivoid = rscdef.getStandardPubDID(
			os.path.join(api.getConfig("inputsDir"), 
				"data/a.imp"))
		dg = api.parseFromString(datalink.DescriptorGenerator,
			'<descriptorGenerator procDef="//soda#fromStandardPubDID"/>'
			).compile(self)
		res = dg(ivoid, {})
		self.assertEqual(res.accref, "data/a.imp")
		self.assertEqual(res.owner, "X_test")
		self.assertEqual(res.mime, "text/plain")
		self.assertEqual(res.accessPath, "data/a.imp")

	def testProductsGenerator(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlget">
			<datalinkCore>
				<dataFunction procDef="//soda#generateProduct"/>
				<metaMaker><code>yield MS(InputKey, name="ignored")</code></metaMaker>
				</datalinkCore>
			</service>""")
		res = svc.run("form", {"ID": rscdef.getStandardPubDID(
			"data/b.imp"), "ignored": 0.4}).original
		self.assertEqual("".join(res.iterData()), 'alpha: 03 34 33.45'
			'\ndelta: 42 34 59.7\nobject: michael\nembargo: 2003-12-31\n')

	def testProductsGeneratorMimecheck(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo" 
				allowed="dlget">
			<datalinkCore>
				<dataFunction procDef="//soda#generateProduct">
					<bind name="requireMimes">["image/fits"]</bind></dataFunction>
					<metaMaker><code>yield MS(InputKey, name="ignored")</code></metaMaker>
				</datalinkCore>
			</service>""")
		self.assertRaisesWithMsg(api.ValidationError,
			"Field PUBDID: Document type not supported: text/plain",
			svc.run,
			("form", {"ID": rscdef.getStandardPubDID("data/b.imp"),
				"ignored": 0.5}))

	def testAccrefPrefixDeny(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo" 
				allowed="dlmeta">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fromStandardPubDID">
					<bind name="accrefPrefix">'nodata'</bind>
				</descriptorGenerator>
			</datalinkCore>
			</service>""")
		res = svc.run("dlmeta", {"ID": rscdef.getStandardPubDID("data/b.imp")})
		row = list(votable.parseString(res.original[1]).next())[0]
		self.assertEqual(row[3],
			'AuthenticationFault: This Datalink'
			' service not available with this pubDID')
		self.assertEqual(row[5], "#this")

	def testAccrefPrefixAccept(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo" 
				allowed="dlmeta">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fromStandardPubDID">
					<bind name="accrefPrefix">'data/b'</bind>
				</descriptorGenerator>
			</datalinkCore>
			</service>""")
		res = svc.run("dlmeta", {"ID": rscdef.getStandardPubDID("data/b.imp")})
		row = list(votable.parseString(res.original[1]).next())[0]
		self.assertTrue(row[1].endswith("/getproduct/data/b.imp"))
		self.assertEqual(row[5], "#this")

	def testProductsGeneratorFailure(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlget">
			<datalinkCore>
				<dataFunction procDef="//soda#generateProduct">
					<code>descriptor.data = None
					</code></dataFunction>
					<metaMaker><code>yield MS(InputKey, name="ignored")
					</code></metaMaker>
				</datalinkCore>
			</service>""")
		self.assertRaisesWithMsg(api.ReportableError,
			"Internal Error: a first data function did not create data.",
			svc.run,
			("form", {"ID": rscdef.getStandardPubDID("data/b.imp"),
				"ignored": 0.4}))

	def testProductsMogrifier(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<dataFunction procDef="//soda#generateProduct"/>
				<inputKey name="addto" type="integer" multiplicity="single"/>
				<dataFunction>
					<setup>
						<code>
							from gavo.protocols import products
							class MogrifiedProduct(products.ProductBase):
								def __init__(self, input, offset):
									self.input, self.offset = input, offset
									products.ProductBase.__init__(self, input.rAccref)

								def iterData(self):
									for chunk in self.input.iterData():
										yield "".join(chr(ord(c)+self.offset)
											for c in chunk)
						</code>
					</setup>
					<code>
						descriptor.data = MogrifiedProduct(descriptor.data,
							args["addto"])
					</code>
				</dataFunction></datalinkCore>
			</service>""")
		res = "".join(svc.run("form", {
			"ID": [rscdef.getStandardPubDID("data/b.imp")], 
			"addto": ["4"]}).original.iterData())
		self.assertEqual(res, 
			"eptle>$47$78$77289\x0ehipxe>$86$78$9=2;\x0e"
			"sfnigx>$qmgleip\x0eiqfevks>$6447156175\x0e")

	def testAccrefFilter(self):
		svc = api.parseFromString(svcs.Service, """<service id="uh">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc">
					<bind key="accrefPrefix">"test"</bind>
				</descriptorGenerator>
			</datalinkCore></service>""")

		self.assertRaisesWithMsg(svcs.ForbiddenURI,
			"This Datalink service not available with this pubDID"
			" (pubDID: ivo://x-unregistred/~?goo/boo)",
			svc.run,
			("dlget", {"ID": [rscdef.getStandardPubDID("goo/boo")]}))

		self.assertRaisesWithMsg(svcs.UnknownURI,
			"Not a pubDID from this site. (pubDID: ivo://great.scott/goo/boo)",
			svc.run,
			("dlget", {"ID": ["ivo://great.scott/goo/boo"]}))


class _DumbSODAService(testhelpers.TestResource):
	resources = [("prodtestTable", tresc.prodtestTable)]

	def make(self, dependents):
		svc = api.parseFromString(svcs.Service, """<service id="uh" 
			allowed="dlget">
			<datalinkCore>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		return svc


class DLInterfaceTest(testhelpers.VerboseTest):
	resources = [("svc", _DumbSODAService())]

	def testIDNecessary(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field ID: ID is mandatory with dlget",
			self.svc.run,
			("dlget", {"REQUEST": ["getLinks"]}))

	def testREQUESTLegal(self):
		dlResp = self.svc.run("dlmeta", {"request": ["getLinks"],
			"ID": rscdef.getStandardPubDID("data/b.imp")}).original[1]
		self.failUnless("TD>http://localhost:8080/getproduct/data/b.imp</TD>"
			in dlResp)

	def testbraindeadREQUESTbombs(self):
		self.assertRaisesWithMsg(api.ValidationError, 
			"Field REQUEST: 'getFoobar' is not a valid value for REQUEST",
			self.svc.run,
			("dlmeta", {"request": ["getFoobar"],
				"ID": rscdef.getStandardPubDID("data/b.imp")}))


class _MetaMakerTestData(testhelpers.TestResource):
# test data for datalink metadata generation 
	resources = [
		("prodtestTable", tresc.prodtestTable)]

	def make(self, dependents):
		svc = api.parseFromString(svcs.Service, """
		<service id="foo" allowed="dlget,dlmeta,static">
			<property key="staticData">data</property>
			<datalinkCore>
				<metaMaker>
					<code>
					yield MS(InputKey, name="format", type="text",
						ucd="meta.format",
						description="Output format desired",
						values=MS(Values,
							options=[MS(Option, content_=descriptor.mime),
								MS(Option, content_="application/fits")]))
					</code>
				</metaMaker>

				<metaMaker>
					<code>
					yield descriptor.makeLink("http://foo/bar", 
						contentType="test/junk", 
						semantics="#alternative",
						contentLength=500002)
					yield descriptor.makeLink("http://foo/baz", 
						contentType="test/gold", 
						semantics="#calibration")
					</code>
				</metaMaker>
				<metaMaker>
					<code>
						if descriptor.pubDID.endswith("b.imp"):
							yield DatalinkFault.NotFoundFault("ivo://not.asked.for",
								"Cannot locate other mess")
					</code>
				</metaMaker>
				<metaMaker>
					<code>
						yield descriptor.makeLinkFromFile(
							"no.such.file", description="An unrelated nothing",
							semantics="http://www.g-vo.org/dl#unrelated")
					</code>
				</metaMaker>
				<metaMaker>
					<code>
						yield descriptor.makeLinkFromFile("data/map1.map", 
							description="Some mapping",
							semantics="http://www.g-vo.org/dl#related")
					</code>
				</metaMaker>
				<dataFunction procDef="//soda#generateProduct"/>
			</datalinkCore>
			<publish render="dlmeta" sets="ivo_managed"/>
			</service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": [
				rscdef.getStandardPubDID("data/a.imp"),
				rscdef.getStandardPubDID("data/b.imp"),
				]}).original

		from gavo.registry import capabilities
		capEl = capabilities.getCapabilityElement(svc.publications[0])

		return (mime, 
			testhelpers.getXMLTree(data, debug=False),
			list(votable.parseString(data).next()),
			testhelpers.getXMLTree(capEl.render(), debug=False))

_metaMakerTestData = _MetaMakerTestData()


class DatalinkMetaMakerTest(testhelpers.VerboseTest):
	resources = [("serviceResult", _metaMakerTestData),
		("prodtestTable", tresc.prodtestTable)]

	def testIDSet(self):
		svc1 = self.serviceResult[1].xpath("//RESOURCE[@utype='adhoc:service']")[0]
		self.assertEqual(
			svc1.xpath("GROUP/PARAM[@name='ID']")[0].get("value"),
			"ivo://x-unregistred/~?data/a.imp")
		svc2 = self.serviceResult[1].xpath("//RESOURCE[@utype='adhoc:service']")[1]
		self.assertEqual(
			svc2.xpath("GROUP/PARAM[@name='ID']")[0].get("value"),
			"ivo://x-unregistred/~?data/b.imp")

	def testMimeOk(self):
		self.assertEqual(self.serviceResult[0], 
			"application/x-votable+xml;content=datalink")

	def testUCDPresent(self):
		tree = self.serviceResult[1]
		self.assertEqual(
			tree.xpath("//PARAM[@name='format']")[0].get("ucd"),
			"meta.format")
	
	def testTypeTranslationWorks(self):
		tree = self.serviceResult[1]
		self.assertEqual(
			tree.xpath("//PARAM[@name='format']")[0].get("arraysize"),
			"*")

	def testOptionsRepresented(self):
		tree = self.serviceResult[1]
		self.assertEqual(
			tree.xpath("//PARAM[@name='format']/VALUES/OPTION")[0].get("value"),
			"text/plain")
		self.assertEqual(
			tree.xpath("//PARAM[@name='format']/VALUES/OPTION")[1].get("value"),
			"application/fits")

	def testAccessURLPresent(self):
		tree = self.serviceResult[1]
		self.assertEqual(
			tree.xpath("//PARAM[@name='accessURL']")[0].get("value"),
			"http://localhost:8080/data/test/foo/dlget")

	def testCapability(self):
		intfEl = self.serviceResult[3].xpath("//interface")[0]
		self.assertEqual(
			intfEl.attrib["{http://www.w3.org/2001/XMLSchema-instance}type"],
			"vs:ParamHTTP")
		self.assertEqual(intfEl.xpath("queryType")[0].text, "GET")
		self.assertEqual(intfEl.xpath("resultType")[0].text, 
			'application/x-votable+xml;content=datalink')
		self.assertEqual(intfEl.xpath("accessURL")[0].text, 
			'http://localhost:8080/data/test/foo/dlmeta')

		self.assertEqual(self.serviceResult[3].xpath("/capability")[0].attrib[
			"standardID"], "ivo://ivoa.net/std/DataLink#links-1.0")

	def testCapabilityParameters(self):
		intfEl = self.serviceResult[3].xpath("//interface")[0]
		for el in intfEl.xpath("param"):
			parName = el.xpath("name")[0].text
			if parName=="ID":
				self.assertEqual(el.attrib["std"], "true")
				self.assertEqual(el.xpath("ucd")[0].text, "meta.id;meta.main")

			elif parName=="RESPONSEFORMAT":
				datatype = el.xpath("dataType")[0]
				self.assertEqual(datatype.text, "char")
				self.assertEqual(datatype.get("arraysize"), "*")

			elif parName=="REQUEST":
				self.assertEqual(el.xpath("description")[0].text, 
					"Request type (must be getLinks)")

			else:
				raise AssertionError("Unexpected Parameter %s"%parName)

	def testAsyncDeclared(self):
		svc = api.parseFromString(svcs.Service, """
		<service id="foo" allowed="dlget,dlasync,dlmeta">
			<datalinkCore>
				<metaMaker>
					<code>
						yield MS(InputKey, name="PAR", type="text")
					</code>
				</metaMaker>
				<dataFunction procDef="//soda#generateProduct"/>
			</datalinkCore>
			</service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": [
				rscdef.getStandardPubDID("data/a.imp"),
				]}).original

		tree = testhelpers.getXMLTree(data, debug=False)

		self.assertEqual(len(tree.xpath("//TR")), 4)
		self.assertEqual(
			set(['http://localhost:8080/data/test/foo/dlget', 
				'http://localhost:8080/data/test/foo/dlasync']),
			set([p.get("value") for p in tree.xpath("//PARAM[@name='accessURL']")]))
		self.assertEqual(
			set(['ivo://ivoa.net/std/SODA#async-1.0',
				'ivo://ivoa.net/std/SODA#sync-1.0']),
			set([p.get("value") 
				for p in tree.xpath("//PARAM[@name='standardID']")]))

	def testCoreForgetting(self):
		from gavo.svcs import renderers
		args = {"ID": rscdef.getStandardPubDID("data/ex.fits")}
		svc = api.getRD("data/cores").getById("dl")
		renderer = renderers.getRenderer("dlmeta")
		gns = testhelpers.getMemDiffer()
		core = svc.core.adaptForRenderer(renderer)

		class _Sentinel(object):
			pass
		s = _Sentinel()
		core.ref = s

		coreId = id(core.__dict__)
		self.assertTrue(coreId in set(id(r) for r in gc.get_referrers(s)))
		it = svc._makeInputTableFor(renderer, args, core=core)
		core.runForMeta(svc, it, svcs.emptyQueryMeta)
		core.finalize()
		core.inputTable.breakCircles()
		del core
		del it
		gc.collect()

		ns = gns()
		self.assertEqual(len(ns), 0, "Uncollected garbage: %s"%ns)
		self.assertFalse(coreId in set(id(r) for r in gc.get_referrers(s)),
			"core still lives and references s")


class _MetaMakerTestRows(testhelpers.TestResource):
	resources = [
		("serviceResult", _metaMakerTestData)]

	def make(self, dependents):
		td = api.resolveCrossId("//datalink#dlresponse", None)
		rows = {}
		for tuple in dependents["serviceResult"][2]:
			row = td.makeRowFromTuple(tuple)
			rows.setdefault((row["ID"], row["semantics"]), []).append(row)
		return rows


class DatalinkMetaRowsTest(testhelpers.VerboseTest):
	resources = [("rows", _MetaMakerTestRows()),
		("serviceResult", _metaMakerTestData)]

	def testAllLinks(self):
		self.assertEqual(len(self.rows), 15)
		for r in self.rows.values():
			self.assertEqual(len(r), 1)
	
	def testAllWithId(self):
		self.assertEqual(set(r[0] for r in self.rows), 
			set(['ivo://x-unregistred/~?data/b.imp',
				'ivo://x-unregistred/~?data/a.imp',
				'ivo://not.asked.for']))
	
	def testAccessURLStatic(self):
		self.assertEqual(self.rows[
			('ivo://x-unregistred/~?data/b.imp', '#alternative')][0]["access_url"], 
			'http://foo/bar')

	def testAccessURLAccess(self):
		self.assertEqual(self.rows[
			('ivo://x-unregistred/~?data/b.imp', '#proc')][0]["access_url"],
			'http://localhost:8080/data/test/foo/dlget')

	def testAccessURLSelf(self):
		self.assertEqual(self.rows[
			('ivo://x-unregistred/~?data/b.imp', '#this')][0]["access_url"],
				"http://localhost:8080/getproduct/data/b.imp")
		self.assertEqual(self.rows[
			('ivo://x-unregistred/~?data/a.imp', '#this')][0]["access_url"],
				"http://localhost:8080/getproduct/data/a.imp")
	
	def testMimes(self):
		self.assertEqual(self.rows[('ivo://x-unregistred/~?data/a.imp', 
			'#calibration')][0]["content_type"], 'test/gold')
	
	def testSemantics(self):
		self.assertEqual(set(r[1] for r in self.rows), 
			set(['#proc', '#this', '#alternative', '#calibration', '#preview',
				"http://dc.g-vo.org/datalink#other",
				'http://www.g-vo.org/dl#related',
				'http://www.g-vo.org/dl#unrelated',
				]))

	def testSizes(self):
		self.assertEqual(self.rows[('ivo://x-unregistred/~?data/a.imp', 
			'#alternative')][0]["content_length"], 500002) 
		self.assertEqual(self.rows[('ivo://x-unregistred/~?data/a.imp', 
			'#calibration')][0]["content_length"], None) 

	def testServiceLink(self):
		svcRow = self.rows[('ivo://x-unregistred/~?data/a.imp', 
			'#proc')][0]
		resId = svcRow["service_def"]
		for res in self.serviceResult[1].xpath("//RESOURCE"):
			if res.attrib.get("ID")==resId:
				break
		else:
			self.fail("Processing service not in datalink links")
		self.assertEqual(res.attrib.get("type"), "meta")
		self.assertEqual(res.attrib.get("utype"), "adhoc:service")

	def testSelfMeta(self):
		selfRow = self.rows[('ivo://x-unregistred/~?data/b.imp', '#this')][0]
		self.assertEqual(selfRow["content_type"], "text/plain")
		self.assertEqual(selfRow["content_length"], 73)

	def testMetaError(self):
		errors = self.rows[('ivo://not.asked.for', datalink.DEFAULT_SEMANTICS)]
		self.assertEqual(errors[0]["error_message"],
			'NotFoundFault: Cannot locate other mess')

	def testPreviewMetaURL(self):
		previewRow = self.rows[('ivo://x-unregistred/~?data/b.imp', '#preview')][0]
		self.assertEqual(previewRow["access_url"],
			"http://example.com/borken.jpg")
		self.assertEqual(previewRow["content_type"],
			"image/jpeg")

	def testPreviewMetaAuto(self):
		previewRow = self.rows[('ivo://x-unregistred/~?data/a.imp', '#preview')][0]
		self.assertEqual(previewRow["access_url"],
			"http://localhost:8080/getproduct/data/a.imp?preview=True")
		self.assertEqual(previewRow["content_type"],
			"text/plain")
	
	def testFromNonExistingFile(self):
		errRow = self.rows[('ivo://x-unregistred/~?data/b.imp', 
			'http://www.g-vo.org/dl#unrelated')][0]
		self.assertEqual(errRow["error_message"], 
			"NotFoundFault: No file for linked item")
		self.assertEqual(errRow["description"],
			"An unrelated nothing")

	def testFromFile(self):
		row = self.rows[('ivo://x-unregistred/~?data/b.imp', 
			'http://www.g-vo.org/dl#related')][0]
		self.assertEqual(row["error_message"], None)
		self.assertEqual(row["content_length"], 8)
		self.assertEqual(row["description"], "Some mapping")
		self.assertEqual(row["content_type"], "application/octet-stream")


def _dissectSODAFile(sodaFile):
	"""returns mime and content for a soda-returned File.

	It also calls cleanup(), if it's there -- basically, that's stuff
	nevow does for us in actual action.
	"""
	content = sodaFile.fp.getContent()
	sodaFile.fp.remove()
	if hasattr(sodaFile, "cleanup"):
		sodaFile.cleanup(None)
	return sodaFile.type, content


############### Start FITS tests

class SODAFITSTest(testhelpers.VerboseTest):
	resources = [("fitsTable", tresc.fitsTable)]

	def testNotFound(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta, dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc">
					<bind key="accrefPrefix">"data/"</bind>
				</descriptorGenerator>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": ["ivo://junky.ivorn/made/up"]}).original
		self.assertEqual("application/x-votable+xml;content=datalink", mime)
		self.failUnless("<TR><TD>ivo://junky.ivorn/made/up</TD><TD></TD>"
			"<TD></TD><TD>NotFoundFault: Not a pubDID from this site.</TD>" in data)

	def testMakeDescriptor(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc">
					<bind key="accrefPrefix">"data/"</bind>
				</descriptorGenerator>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<metaMaker><code>
					assert descriptor.hdr["EQUINOX"]==2000.
					assert (map(int, descriptor.skyWCS.wcs_sky2pix([(166, 20)], 0)[0])
						==[7261, 7984])
					if False:
						yield
				</code></metaMaker>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/ex.fits")]}).original
		tree = testhelpers.getXMLTree(data)
		self.assertEqual(tree.xpath("//PARAM[@name='RA']")[0].get("unit"),
			"deg")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']")[0].get("xtype"),
			"interval")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']")[0].get("datatype"),
			"double")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']")[0].get("arraysize"),
			"2")
		self.assertEqual(tree.xpath("//PARAM[@name='RA']/VALUES/MIN"
			)[0].get("value")[:7], "168.243")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']/VALUES/MAX"
			)[0].get("value"), "22.2192872351")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']/DESCRIPTION"
			)[0].text, "The latitude coordinate")

	def testMakeCubeDescriptor(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams">
					<bind key="axisMetaOverrides">{
						"RA": {"ucd": "pos.eq.ra;meta.special"},
						3:    {"name": "ANGSTROMS", "unit": "0.1nm"}}
					</bind>
				</metaMaker>
				<FEED source="//soda#fits_standardBANDCutout"
					spectralAxis="3"
					wavelengthOverride="0.1nm"/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")]}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@name='RA']")[0].get("ucd"),
			"pos.eq.ra;meta.special")
		self.assertEqual(tree.xpath("//PARAM[@name='RA']/VALUES/MIN"
			)[0].get("value"), "359.3580942")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC']/VALUES/MAX"
			)[0].get("value"), "30.9848485045")
		self.assertEqual(tree.xpath("//PARAM[@name='ANGSTROMS']/VALUES/MIN"
			)[0].get("value"), "3749.0")
		self.assertEqual(tree.xpath("//PARAM[@name='ANGSTROMS']/VALUES/MAX"
			)[0].get("value"), "3755.0")
		lmaxPar = tree.xpath("//PARAM[@name='BAND']")[0]
		self.assertEqual(lmaxPar.get("ucd"), "em.wl")
		self.assertEqual(lmaxPar.get("unit"), "m")
		self.assertEqual(lmaxPar.xpath("VALUES/MAX")[0].get("value"),
			"3.755e-07")

	def testCutoutNoSpatialCube(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<dataFunction procDef="//soda#fits_doWCSCutout"/>
				<dataFormatter procDef="//soda#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectSODAFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"COO_3": ["3753 3755"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 11)
		self.assertEqual(hdr["NAXIS2"], 7)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testCutoutBANDCube(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<FEED source="//soda#fits_standardBANDCutout"
					spectralAxis="3"
					wavelengthOverride="0.1nm"/>
				<dataFunction procDef="//soda#fits_doWCSCutout"/>
				<dataFormatter procDef="//soda#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectSODAFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"BAND": ["3.755e-7 +Inf"],
				"RA": ["359.359 +Inf"],
				"DEC": ["30.39845 +Inf"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 8)
		self.assertEqual(hdr["NAXIS2"], 7)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testCutoutCube(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<dataFunction procDef="//soda#fits_doWCSCutout"/>
				<dataFormatter procDef="//soda#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectSODAFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"RA": ["359.36 359.359"],
				"DEC": ["30.9845 30.985"],
				"COO_3": ["3753 3755"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 2)
		self.assertEqual(hdr["NAXIS3"], 2)

	_geoDLServiceLiteral = """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<FEED source="//soda#fits_Geometries"/>
				<dataFunction procDef="//soda#fits_doWCSCutout"/>
				<dataFormatter procDef="//soda#fits_formatHDUs"/>
			</datalinkCore></service>"""

	def testCutoutPOLYGON(self):
		svc = api.parseFromString(svcs.Service, self._geoDLServiceLiteral)
		mime, data = _dissectSODAFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"POLYGON": ["359.36 30.9845 359.359 30.9845"
					" 359.359 30.985"]
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 2)
		self.assertEqual(hdr["NAXIS3"], 4)

	def testPOLYGONClashesRA(self):
		svc = api.parseFromString(svcs.Service, self._geoDLServiceLiteral)
		self.assertRaisesWithMsg(api.ValidationError,
			"Field RA: Attempt to cut out along axis 1 that has been"
				" modified before.",
			svc.run,
			("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"RA": ["359.36 359.359"],
				"POLYGON": ["359.36 30.9845 359.359 30.9845"
					" 359.359 30.985"]
				}))

	def testEmptyCutout(self):
		svc = api.parseFromString(svcs.Service, self._geoDLServiceLiteral)
		self.assertRaisesWithMsg(soda.EmptyData,
			"",
			svc.run,
			("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"CIRCLE": ["36 48 0.0004"],
				}))

	def testCutoutCIRCLE(self):
		svc = api.parseFromString(svcs.Service, self._geoDLServiceLiteral)
		mime, data = _dissectSODAFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"CIRCLE": ["359.36 30.984 0.0004"]
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
# TODO: I'd really expect NAXIS1==NAXIS2, but I cannot find a mistake
# in my reasoning up to here.  Hm.
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 3)
		self.assertEqual(hdr["NAXIS3"], 4)
	
	def testCIRCLEClashesPOLYGON(self):
		svc = api.parseFromString(svcs.Service, self._geoDLServiceLiteral)
		self.assertRaisesWithMsg(api.ValidationError,
			"Field CIRCLE: Attempt to cut out along axis 1 that has been"
				" modified before.",
			svc.run,
			("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"CIRCLE": ["359.36 30.9845 0.0004"],
				"POLYGON": ["359.36 30.9845 359.359 30.9845"
					" 359.359 30.985"]
				}))

	def testKindPar(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<FEED source="//soda#fits_genKindPar"/>
			</datalinkCore></service>""")
		mime, data = svc.run("dlget", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")],
			"KIND": ["HEADER"],}).original
		self.assertEqual(mime, "application/fits-header")
		self.assertEqual(len(data), 2880)

	def testCutoutHeader(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<metaMaker procDef="//soda#fits_makeWCSParams"/>
				<dataFunction procDef="//soda#fits_makeHDUList"/>
				<dataFunction procDef="//soda#fits_doWCSCutout"/>
				<FEED source="//soda#fits_genKindPar"/>
			</datalinkCore></service>""")
		mime, data = svc.run("dlget", {
			"ID": rscdef.getStandardPubDID("data/excube.fits"),
				"COO_3": ["3753 400000"],
			"KIND": "HEADER",}).original
		self.assertEqual(mime, "application/fits-header")
		self.failUnless("NAXIS3  =                    2" in data)

	def testFITSNoSTC(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<FEED source="//soda#fits_standardDLFuncs"
					accrefPrefix="" stcs=""/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": rscdef.getStandardPubDID("data/excube.fits")}).original
		self.failUnless("<DATA><TABLEDATA>" in data)

	def testPixelMeta(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<FEED source="//soda#fits_genPixelPar"/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": rscdef.getStandardPubDID("data/excube.fits")}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@name='PIXEL_3']/VALUES/MAX"
			)[0].get("value"), "4")
		self.assertEqual(tree.xpath("//PARAM[@name='PIXEL_1']"
			)[0].get("datatype"), "int")

	def testPixelCutout(self):
		svc = api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<FEED source="//soda#fits_standardDLFuncs"
					stcs="" accrefPrefix=""/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = _dissectSODAFile(svc.run("dlget", {
			"ID": rscdef.getStandardPubDID("data/excube.fits"),
				"PIXEL_1": ["4 4"],
				"PIXEL_3": ["2 2"]}).original)
		self.assertEqual(mime, "image/fits")
		self.failUnless("NAXIS1  =                    1" in data)
		self.failUnless("NAXIS2  =                    7" in data)
		self.failUnless("NAXIS3  =                    1" in data)


def _iterWCSSamples():
	for center in [
			(0, 0),
			(10, 45),
			(120, -30),
			(240, 87),
			(0, -90),
			(180, 90)]:
		yield  center, testhelpers.computeWCSKeys(center, (2, 3), cutCrap=True)
	

def _getFakeDescriptorForWCS(wcsDict):
	"""returns something good enough to stand in for a FITSDescriptor
	in SODA code from stuff generated by computeWCSKeys.
	"""
	res = testhelpers.StandIn(hdr=wcsDict,
		changingAxis=lambda *args: None,
		slices=[])
	soda.ensureSkyWCS(res)
	return res


class SODA_POLYGONMetaTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	# generated through maketruth below
	truth = {
		(0, 0): '359.0021009128 -1.4964326084 359.0021009128 1.4994301037 0.9998984794 1.4994291918 0.9998984794 -1.4964316983',
		(10, 45): '8.62481612 43.4950994178 8.5509805405 46.4905074605 11.4519220644 46.490470762 11.3779386981 43.4950663641',
		(120, -30): '118.8301216734 -31.4913388619 118.8649164101 -28.4956276477 121.1373577096 -28.4956087361 121.1722221187 -31.4913175209',
		(240, 87): '227.4781529243 85.3942399052 206.3749183808 88.1983560305 273.6779932638 88.1972488451 252.546147226 85.3938074824',
		(0, -90): '213.690067526 -88.2014209215 326.3628534376 -88.1989264651 33.690067526 -88.1978189291 146.2569707456 -88.2003118463'  ,
		(180, 90): '146.309932474 88.2014209215 33.6371465624 88.1989264651 326.309932474 88.1978189291 213.7430292544 88.2003118463',
		}
	
	proc = api.makeStruct(datalink.MetaMaker, 
			procDef=api.resolveCrossId("//soda#fits_makePOLYGONMeta")
		).compile(parent=testhelpers.getTestRD())

	def _produceKeys(self, sample):
		pos, header = sample
		desc = _getFakeDescriptorForWCS(header)
		return list(self.proc(desc))

	def _runTest(self, sample):
		keys = self._produceKeys(sample)
		self.assertEqual(len(keys), 1)
		key = keys[0]
		self.assertEqual(key.type, "double precision(*)")
		self.assertEqual(key.values.max,
			self.truth[sample[0]])

	def getTruthFor(self, sample):
		key = self._produceKeys(sample)[0]
		points = [float(v) for v in key.values.max.split()]
		return "%r: %r"%(sample[0], key.values.max), [
			('center', sample[0][0], sample[0][1])]+[
			('vertex',)+p for p in utils.grouped(2, points)]

	samples = list(_iterWCSSamples())


class SODA_CIRCLEMetaTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	# generated through maketruth below
	truth = {
		 (0, 0): '0.0000000000 0.0000000000 1.8021810709',
  	(10, 45): '10.0000000000 45.0000000000 1.8021810709',
  	(120, -30): '120.0000000000 -30.0000000000 1.8021810709',
  	(240, 87): '240.0000000000 87.0000000000 1.8021810709',
  	(0, -90): '180.0000000000 -90.0000000000 1.8021810709',
  	(180, 90): '180.0000000000 90.0000000000 1.8021810709',
	}
	
	proc = api.makeStruct(datalink.MetaMaker, 
			procDef=api.resolveCrossId("//soda#fits_makeCIRCLEMeta")
		).compile(parent=testhelpers.getTestRD())

	def _produceKeys(self, sample):
		pos, header = sample
		desc = _getFakeDescriptorForWCS(header)
		return list(self.proc(desc))

	def _runTest(self, sample):
		keys = self._produceKeys(sample)
		self.assertEqual(len(keys), 1)
		key = keys[0]
		self.assertEqual(key.type, "double precision(3)")
		self.assertEqual(key.values.max,
			self.truth[sample[0]])

	def getTruthFor(self, sample):
		from gavo.utils import pgsphere

		key = self._produceKeys(sample)[0]
		circ = pgsphere.SCircle.fromSODA(key.values.max)
		points = [float(v) for v in circ.asPoly().asSODA().split()]
		return "%r: %r"%(sample[0], key.values.max), [
			('center', sample[0][0], sample[0][1])]+[
			('vertex',)+p for p in utils.grouped(2, points)]

	samples = list(_iterWCSSamples())


class SODA_CIRCLECutoutIntervalTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	proc = staticmethod(api.makeStruct(datalink.DataFunction, 
			procDef=api.resolveCrossId("//soda#fits_makeCIRCLESlice")
		).compile(parent=testhelpers.getTestRD()))

	def _runTest(self, sample):
		pos, header = sample
		desc = _getFakeDescriptorForWCS(header)
		soda.ensureSkyWCS(desc)
		args = {"CIRCLE": pos+(0.5,)}
		_ = self.proc(desc, args)
		self.assertEqual(
			desc.slices,
			[(1, 250, 750), (2, 333, 667)])

	samples = list(_iterWCSSamples())


class SODAPOSTest(testhelpers.VerboseTest):
	resources = [("fitsTable", tresc.fitsTable)]

	def _getSvc(self):
		return api.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//soda#fits_genDesc"/>
				<FEED source="//soda#fits_standardDLFuncs"/>
			</datalinkCore></service>""")

	def testPOSError(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field POS: Invalid SIAPv2 geometry: 'Circle 30 40'"
			" (expected a SIAPv2 shape name)",
			self._getSvc().run,
			("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"POS": ["Circle 30 40"],
				}))
	
	def testPOSRange(self):
		mime, data = _dissectSODAFile(self._getSvc().run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"POS": ["RANGE 359.359 359.36 30.9845 30.985"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 2)
		self.assertEqual(hdr["NAXIS3"], 4)

	def testPOSCircle(self):
		mime, data = _dissectSODAFile(self._getSvc().run("dlget", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")],
			"POS": ["CIRCLE 359.359 30.984 0.001"],
			}).original)
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 7)
		self.assertEqual(hdr["NAXIS2"], 7)

	def testPOSPolygon(self):
		mime, data = _dissectSODAFile(self._getSvc().run("dlget", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")],
			"POS": ["POLYGON 359.359 30.984 359.3592 30.985 359.3593 30.986"],
			}).original)
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 2)
		self.assertEqual(hdr["NAXIS2"], 4)


################ Start SDM tests


class SDMDatalinkTest(testhelpers.VerboseTest):
	resources = [("ssaTable", tresc.ssaTestTable)]

	def runService(self, params):
		return api.resolveCrossId("data/ssatest#dlnew").run("dlget", params)

	def testRejectWithoutPUBDID(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field ID: ID is mandatory with dlget",
			self.runService,
			({},))

	def testVOTDelivery(self):
		res = self.runService(
			{"ID": 'ivo://test.inv/test1', "FORMAT": "application/x-votable+xml"})
		mime, payload = res.original
		self.assertEqual(mime, "application/x-votable+xml")
		self.failUnless('xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01'
			in payload)
		self.failUnless('QJtoAAAAAABAm2g' in payload)

	def testTextDelivery(self):
		res = self.runService(
			{"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain"})
		mime, payload = res.original
		self.failUnless(isinstance(payload, str))
		self.failUnless("1754.0\t1754.0\n1755.0\t1753.0\n"
			"1756.0\t1752.0" in payload)

	def testCutoutFull(self):
		res = self.runService(
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["text/plain"], 
				"BAND": ["1.762e-7 1.764e-7"]})
		mime, payload = res.original
		self.assertEqual(payload, 
			'1762.0\t1746.0\n1763.0\t1745.0\n1764.0\t1744.0\n')
		self.failIf('<TR><TD>1756.0</TD>' in payload)

	def testCutoutHalfopen(self):
		res = self.runService(
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["application/x-votable+xml;serialization=tabledata"], 
				"BAND": ["1.927e-7 +Inf"]})
		mime, payload = res.original
		self.failUnless('xmlns:spec="http://www.ivoa.net/xml/SpectrumModel/v1.01'
			in payload)
		self.failUnless('<TR><TD>1927.0</TD><TD>1581.0</TD>' in payload)
		self.failIf('<TR><TD>1756.0</TD>' in payload)
		tree = testhelpers.getXMLTree(payload, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@utype="
			"'spec:Spectrum.Char.SpectralAxis.Coverage.Bounds.Start']"
			)[0].get("value"), "1.927e-07")
		self.assertAlmostEqual(float(tree.xpath("//PARAM[@utype="
			"'spec:Spectrum.Char.SpectralAxis.Coverage.Bounds.Extent']"
			)[0].get("value")), 1e-10)

	def testEmptyCutoutFails(self):
		self.assertRaisesWithMsg(soda.EmptyData,
			"",
			self.runService,
			({"ID": 'ivo://test.inv/test1', 
				"FORMAT": "application/x-votable+xml",
				"BAND": "-Inf 1.927e-8"},))

	def testOriginalCalibOk(self):
		mime, payload = self.runService(
			{"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain", 
				"FLUXCALIB": "UNCALIBRATED"}).original
		self.failUnless(payload.endswith("1928.0	1580.0\n"))

	def testNormalize(self):
		mime, payload = api.resolveCrossId("data/ssatest#dlnew").run("ssap.xml",
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": "application/x-votable+xml;serialization=tabledata", 
				"BAND": ["1.9e-7 1.92e-7"], 
				"FLUXCALIB": "RELATIVE"}).original
		self.failUnless("<TD>1900.0</TD><TD>0.91676" in payload)
		tree = testhelpers.getXMLTree(payload, debug=False)
		self.assertEqual(tree.xpath(
			"//PARAM[@utype='spec:Spectrum.Char.FluxAxis.Calibration']")[0].get(
				"value"),
			"RELATIVE")

	def testBadCalib(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field FLUXCALIB: 'ferpotschket' is not a valid value for FLUXCALIB",
			self.runService,
			({"ID": 'ivo://test.inv/test1', 
				"FORMAT": "text/plain", 
				"FLUXCALIB": ["ferpotschket"]},))

	def testBadPubDID(self):
		self.assertRaisesWithMsg(svcs.UnknownURI,
			"No spectrum with this pubDID known here (pubDID: ivo://test.inv/bad)",
			self.runService,
				({"ID": 'ivo://test.inv/bad'},))

	def testRandomParamFails(self):
		self.assertRaisesWithMsg(api.ValidationError,
			"Field (various): The following parameter(s) are"
			" not accepted by this service: warp",
			self.runService,
			({"ID": 'ivo://test.inv/test1', 
				"warp": "infinity"},))

	def testCoreForgetting(self):
		gns = testhelpers.getMemDiffer()
		res = self.runService(
			{"ID": ['ivo://test.inv/test1'], 
				"FORMAT": ["text/plain"], "BAND": ["1.762e-7 1.764e-7"]})
		del res

		gc.collect()
		ns = gns()
		self.assertEqual(ns, [], "Spectrum cutout left garbage.")


def maketruth(testclass):
	"""writes a VOTable representative of the test class.

	This is because there's nothing like visualisation for getting
	an idea whether these spherical geometry things actually make sense.
	
	This writes 000truth.vot and 000truth.txt, the latter for the class' truth
	attribute.  Open truth.vot in topcat to see what's happening.

	testclass needs to have a gettruth method for this to work.  It has
	to return, for each test, 
	"""
	from gavo.votable import V

	tests = testclass("test00")
	txt, rows  = [], []

	for sample in _iterWCSSamples():
		truthVal, truthPoints = tests.getTruthFor(sample)
		txt.append(truthVal)
		rows.extend(truthPoints)

	vot = V.VOTABLE[V.RESOURCE[
		votable.DelayedTable(
			V.TABLE[
				V.FIELD(name="ptype", datatype="char", arraysize="*"),
				V.FIELD(name="ra", datatype="double", unit="deg"),
				V.FIELD(name="dec", datatype="double", unit="deg")],
			rows, V.BINARY)]]
	with open("000truth.vot", "w") as f:
		votable.write(vot, f)

	with open("000truth.txt", "w") as f:
		f.write("  %s\n"%(",\n  ".join(txt)))


if __name__=="__main__":
#	maketruth(SODA_CIRCLEMetaTest)
	testhelpers.main(SDMDatalinkTest)
