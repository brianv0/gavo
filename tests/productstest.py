"""
Tests for the products infrastructure.
"""

from cStringIO import StringIO
import datetime
import os
import struct
import tarfile

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.protocols import datalink
from gavo.protocols import products
from gavo.utils import fitstools
from gavo.utils import pyfits
from gavo.web import producttar

import tresc


class _TestWithProductsTable(testhelpers.VerboseTest):
	resources = [('conn', tresc.prodtestTable), ('users', tresc.testUsers)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.service = api.getRD("//products").getById("p")


class TarTest(_TestWithProductsTable):
	def setUp(self):
		_TestWithProductsTable.setUp(self)
		self.tarService = self.service.rd.getById("getTar")

	def _getTar(self, inDict, qm=None):
		res = self.tarService.run("form", inDict, queryMeta=qm)
		dest = StringIO()
		producttar.getTarMaker()._productsToTar(res.original, dest)
		return dest.getvalue()

	def _assertIsTar(self, res):
		f = tarfile.open("data.tar", "r:*", StringIO(res))
		f.close()

	def testFreeNoAuth(self):
		res = self._getTar({"pattern": "test.prodtest#data/b.imp"})
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)

	def testAllNoAuth(self):
		res = self._getTar({"pattern": "test.prodtest#%"})
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failUnless("This file is embargoed.  Sorry" in res)
		self.failIf("\nobject: gabriel" in res)
	
	def testAllWithAuth(self):
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "X_test", "megapass"
		res = self._getTar({"pattern": "test.prodtest#%"}, qm)
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failIf("This file is embargoed.  Sorry" in res)
		self.failUnless("\nobject: gabriel" in res)
	
	def testAllWithWrongAuth(self):
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "Y_test", "megapass"
		res = self._getTar({"pattern": "test.prodtest#%"}, qm)
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failUnless("This file is embargoed.  Sorry" in res)
		self.failIf("\nobject: gabriel" in res)


class _FakeRequest(object):
	def __init__(self, **kwargs):
		self.args = dict((key, [value]) for key, value in kwargs.iteritems())


class RaccrefTest(_TestWithProductsTable):

	# tests for dcc: with SDM VOTables are in ssatest.py

	def	testBadConstructurVals(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field accref: Invalid value for constructor argument to RAccref:"
				" scale='klonk'",
			products.RAccref,
			("testing", {"scale": "klonk"}))

	def testKeyMandatory(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field accref: Must give key when constructing RAccref",
			products.RAccref.fromRequest,
			("/", _FakeRequest(scale="2")))

	def testPathFromKey(self):
		pk = products.RAccref.fromRequest("/", _FakeRequest(key="abc"))
		self.assertEqual(pk.accref, "abc")

	def testExtraParamsIgnored(self):
		pk = products.RAccref("name", {"sra": "3", "ignored": True})
		self.assertEqual(pk.accref, "name")
		self.assertEqual(pk.params, {"sra": 3.})

	def testSerialization(self):
		pk = products.RAccref(
			"extra weird/product+name%something.fits",
			{"scale": "4"})
		self.assertEqual(str(pk),
			"extra%20weird/product%2Bname%25something.fits?scale=4")

	def testFromRequestSimple(self):
		pk = products.RAccref.fromRequest("extra weird+key", 
			_FakeRequest(scale=None))
		self.assertEqual(pk.accref, "extra weird+key")
		self.assertEqual(pk.params, {})

	def testFromStringWithArgs(self):
		pk = products.RAccref.fromString(
			"extra%20weird&?%2bkey?ra=2&sra=0.5&dec=4&sdec=0.75")
		self.assertEqual(pk.accref, "extra weird&?+key")
		self.assertEqual(pk.params, {"ra": 2, "sra":0.5, "dec":4, "sdec":0.75})

	def testFromStringWithoutArgs(self):
		pk = products.RAccref.fromString("extra%20weird&%2bkey")
		self.assertEqual(pk.accref, "extra weird&+key")
		self.assertEqual(pk.params, {})
	
	def testBadFromString(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field accref: Invalid value for constructor argument to RAccref:"
			" sra='huhu'",
			products.RAccref.fromString,
			("worz?sra=huhu",))

	def testProductsRowRaises(self):
		nonExProd = products.RAccref("junkomatix/@@ridiculosa")
		self.assertRaisesWithMsg(base.NotFoundError, 
			"accref 'junkomatix/@@ridiculosa' could not be located in product table",
			lambda: nonExProd.productsRow,
			())

	def testProductsRowReturns(self):
		prod = products.RAccref("data/a.imp")
		self.assertEqual(prod.productsRow, {
			'embargo': datetime.date(2030, 12, 31), 
			'accessPath': 'data/a.imp', 
			'mime': 'text/plain', 
			'owner': 'X_test', 
			'accref': 'data/a.imp', 
			'sourceTable': 'test.prodtest'})


class ProductsCoreTest(_TestWithProductsTable):
	def _getProductFor(self, accref, moreFields={}):
		inData = {"accref": [products.RAccref.fromString(accref)]}
		inData.update(moreFields)
		svc = base.caches.getRD("//products").getById("p")
		rows = svc.run("get", inData, 
			).original.getPrimaryTable().rows
		self.assertEqual(len(rows), 1)
		return rows[0]["source"]

	def _getOutput(self, prod):
		return "".join(prod.iterData())

	def testBasic(self):
		res = self._getProductFor("data/b.imp")
		self.failUnless(isinstance(res, products.FileProduct))
		self.failUnless(self._getOutput(res).startswith(
			"alpha: 03 34 33.45"))

	def testNonExistingProduct(self):
		res = self._getProductFor("junk/kotter")
		self.failUnless(isinstance(res, products.NonExistingProduct))
		self.assertRaisesWithMsg(IOError,
			"junk/kotter does not exist",
			self._getOutput,
			(res,))
		self.assertRaisesWithMsg(svcs.UnknownURI,
			"junk/kotter",
			res.renderHTTP,
			(None,))
	
	def testRemovedProduct(self):
		srcPath = os.path.join(base.getConfig("inputsDir"), "data", "b.imp")
		os.rename(srcPath, srcPath+".bak")
		try:
			res = self._getProductFor("data/b.imp")
			self.failUnless(isinstance(res, products.InvalidProduct))
		finally:
			os.rename(srcPath+".bak", srcPath)

	def testProtectedProductUnauth(self):
		res = self._getProductFor("data/a.imp")
		self.failUnless(isinstance(res, products.UnauthorizedProduct))

	def testProtectedProductWithMoreArg(self):
		res = self._getProductFor("data/a.imp?scale=2")
		self.failUnless(isinstance(res, products.UnauthorizedProduct))

	def testProtectedProductBadAuth(self):
		res = self._getProductFor("data/a.imp",
			{"user": "Y_test", "password": "megapass"})
		self.failUnless(isinstance(res, products.UnauthorizedProduct))

	def testProtectedAuth(self):
		res = self._getProductFor("data/a.imp",
			{"user": "X_test", "password": "megapass"})
		self.failUnless(isinstance(res, products.FileProduct))
		self.failUnless(self._getOutput(res).startswith(
			"alpha: 23 34 33.45"))

	def testRemoteProduct(self):
		with tresc.prodtestTable.prodtblRow(accessPath="http://foo.bar"):
			res = self._getProductFor("just.testing/nowhere")
			self.failUnless(isinstance(res, products.RemoteProduct))
			self.assertRaisesWithMsg(svcs.WebRedirect,
				"This is supposed to redirect to http://foo.bar",
				res.renderHTTP,
				(None,))

	def testInvalidProduct(self):
		with tresc.prodtestTable.prodtblRow(accessPath="/non/existing/file"):
			res = self._getProductFor("just.testing/nowhere")
			self.failUnless(isinstance(res, products.InvalidProduct))
			self.assertRaises(svcs.UnknownURI,
				res.renderHTTP,
				None)

	def testScaledProduct(self):
		prod = self._getProductFor("data/b.imp?scale=3")
	
	def testCutoutProduct(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field accref: Cannot generate cutouts for anything but FITS yet.",
			self._getProductFor,
			("data/b.imp?ra=3&dec=4&sra=2&sdec=4",))


class _FITSTable(tresc.RDDataResource):
	"""at least one FITS file in the products table.
	"""
	dataId = "import_fitsprod"

_fitsTable = _FITSTable()


class MangledFITSProductsTest(testhelpers.VerboseTest):
	resources = [("fitsTable", _fitsTable)]

	def testScaledFITS(self):
		prod = products.getProductForRAccref("data/ex.fits?scale=3")
		resFile = StringIO("".join(prod.iterData()))
		hdr = fitstools.readPrimaryHeaderQuick(resFile)
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["BITPIX"], -32)
		self.failUnless("getproduct/data/ex.fits" in hdr["FULLURL"])
		self.assertAlmostEqual(
			struct.unpack("!f", resFile.read(4))[0],
			7437.5556640625)

# Revive when (and if) we do cutouts in pure python; right now, there's
# no cutout binary in the test sandbox
#	def testCutoutFITS(self):
#		prod = products.getProductForRAccref("data/ex.fits?ra=168.24389&dec=22.21526&sra=0.0085&sdec=0.0142")
#		open("zw.fits", "w").write("".join(prod.iterData()))


class DatalinkElementTest(testhelpers.VerboseTest):
	resources = [("prodtestTable", tresc.prodtestTable)]
	
	def testStandardDescGenWorks(self):
		ivoid = rscdef.getStandardPubDID(
			os.path.join(base.getConfig("inputsDir"), 
				"data/a.imp"))
		dg = base.parseFromString(datalink.DescriptorGenerator,
			'<descriptorGenerator procDef="//datalink#fromStandardPubDID"/>'
			).compile(self)
		res = dg(ivoid, {})
		self.assertEqual(res.accref, "data/a.imp")
		self.assertEqual(res.owner, "X_test")
		self.assertEqual(res.mime, "text/plain")
		self.assertEqual(res.accessPath, "data/a.imp")

	def testProductsGenerator(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<dataFunction procDef="//datalink#generateProduct"/>
				<metaMaker><code>yield MS(InputKey, name="ignored")</code></metaMaker>
				</datalinkCore>
			</service>""")
		res = svc.run("form", {"PUBDID": rscdef.getStandardPubDID(
			"data/b.imp"), "ignored": 0.4}).original
		self.assertEqual("".join(res.iterData()), 'alpha: 03 34 33.45'
			'\ndelta: 42 34 59.7\nobject: michael\nembargo: 2003-12-31\n')

	def testProductsGeneratorMimecheck(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<dataFunction procDef="//datalink#generateProduct">
					<bind name="requireMimes">["image/fits"]</bind></dataFunction>
					<metaMaker><code>yield MS(InputKey, name="ignored")</code></metaMaker>
				</datalinkCore>
			</service>""")
		self.assertRaisesWithMsg(base.ValidationError,
			"Field PUBDID: Document type not supported: text/plain",
			svc.run,
			("form", {"PUBDID": rscdef.getStandardPubDID("data/b.imp"),
				"ignored": 0.5}))

	def testProductsGeneratorFailure(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<dataFunction procDef="//datalink#generateProduct">
					<code>descriptor.data = None
					</code></dataFunction>
					<metaMaker><code>yield MS(InputKey, name="ignored")
					</code></metaMaker>
				</datalinkCore>
			</service>""")
		self.assertRaisesWithMsg(base.ReportableError,
			"Internal Error: a first data function did not create data.",
			svc.run,
			("form", {"PUBDID": rscdef.getStandardPubDID("data/b.imp"),
				"ignored": 0.4}))

	def testProductsMogrifier(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<dataFunction procDef="//datalink#generateProduct"/>
				<inputKey name="addto" type="integer" multiplicity="single"/>
				<dataFunction>
					<setup>
						<code>
							from gavo.protocols import products
							class MogrifiedProduct(products.ProductBase):
								def __init__(self, input, offset):
									self.input, self.offset = input, offset
									products.ProductBase.__init__(self,
										input.sourceSpec, input.contentType)

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
			"PUBDID": [rscdef.getStandardPubDID("data/b.imp")], 
			"addto": ["4"]}).original.iterData())
		self.assertEqual(res, 
			"eptle>$47$78$77289\x0ehipxe>$86$78$9=2;\x0e"
			"sfnigx>$qmgleip\x0eiqfevks>$6447156175\x0e")


class _MetaMakerTestData(testhelpers.TestResource):
# test data for datalink metadata generation 
	def make(self, dependents):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
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
					yield LinkDef("http://foo/bar", "test/junk", "related")
					yield LinkDef("http://foo/baz", "test/gold", "unrelated")
					</code>
				</metaMaker>
				<dataFunction procDef="//datalink#generateProduct"/>

				<dataFunction procDef="//datalink#generateProduct"/>
			</datalinkCore>
			</service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("form", {
			"PUBDID": [rscdef.getStandardPubDID("data/b.imp")]}).original
		return (mime, testhelpers.getXMLTree(data),
			list(votable.parseString(data).next()))


class DatalinkMetaMakerTest(testhelpers.VerboseTest):
	resources = [("serviceResult", _MetaMakerTestData()),
		("prodtestTable", tresc.prodtestTable)]

	def testMimeOk(self):
		self.assertEqual(self.serviceResult[0], "application/x-votable+xml")

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

	def testLinkRowsPresent(self):
		rows = self.serviceResult[2]
		self.assertEqual(rows, [
				['http://foo/bar', 'test/junk', 'related'],
				['http://foo/baz', 'test/gold', 'unrelated']])
	
	def testAccessURLPresent(self):
		tree = self.serviceResult[1]
		self.assertEqual(
			tree.xpath("//PARAM[@utype='datalink:accessURL']")[0].get("value"),
			"http://localhost:8080/data/test/foo/dlget")


class DatalinkFITSTest(testhelpers.VerboseTest):
	resources = [("fitsTable", _fitsTable)]

	def testMakeDescriptor(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<metaMaker><code>
					assert descriptor.hdr["EQUINOX"]==2000.
					assert (map(int, descriptor.skyWCS.wcs_sky2pix([(166, 20)], 0)[0])
						==[7261, 7984])
					if False:
						yield
				</code></metaMaker>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlget", {
			"PUBDID": [rscdef.getStandardPubDID("data/ex.fits")]}).original
		tree = testhelpers.getXMLTree(data)
		self.assertEqual(tree.xpath("//PARAM[@name='RA_MIN']")[0].get("unit"),
			"deg")
		self.assertEqual(tree.xpath("//PARAM[@name='RA_MAX']/VALUES/MIN"
			)[0].get("value")[:7], "168.243")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC_MIN']/VALUES/MAX"
			)[0].get("value"), "22.2192872351")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC_MAX']/DESCRIPTION"
			)[0].text, "The latitude coordinate, upper limit")

	def testMakeCubeDescriptor(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlget", {
			"PUBDID": [rscdef.getStandardPubDID("data/excube.fits")]}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@name='RA_MAX']/VALUES/MIN"
			)[0].get("value"), "359.3580942")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC_MIN']/VALUES/MAX"
			)[0].get("value"), "30.9848485045")
		self.assertEqual(tree.xpath("//PARAM[@name='COO_3_MIN']/VALUES/MIN"
			)[0].get("value"), "3749.0")
		self.assertEqual(tree.xpath("//PARAM[@name='COO_3_MIN']/VALUES/MAX"
			)[0].get("value"), "3755.0")

	def testCutoutNoSpatialCube(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<dataFormatter procDef="//datalink#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = svc.run("dlget", {
				"PUBDID": [rscdef.getStandardPubDID("data/excube.fits")],
				"COO_3_MIN": ["3753"],
				"COO_3_MAX": ["3755"],
				}).original

		self.assertEqual(mime, "application/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 11)
		self.assertEqual(hdr["NAXIS2"], 7)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testCutoutCube(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<dataFormatter procDef="//datalink#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = svc.run("dlget", {
				"PUBDID": [rscdef.getStandardPubDID("data/excube.fits")],
				"RA_MAX": ["359.36"],
				"RA_MIN": ["359.359"],
				"DEC_MAX": ["30.9845"],
				"DEC_MIN": ["30.985"],
				"COO_3_MIN": ["3753"],
				"COO_3_MAX": ["3755"],
				}).original

		self.assertEqual(mime, "application/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 2)
		self.assertEqual(hdr["NAXIS3"], 2)


if __name__=="__main__":
	testhelpers.main(DatalinkFITSTest)
