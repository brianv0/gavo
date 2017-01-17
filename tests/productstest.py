"""
Tests for the products infrastructure.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from cStringIO import StringIO
import datetime
import gc
import os
import struct
import tarfile

from nevow.testutil import FakeRequest

from gavo.helpers import testhelpers

from gavo import api
from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.helpers import testtricks
from gavo.protocols import datalink
from gavo.protocols import products
from gavo.utils import fitstools
from gavo.utils import pyfits
from gavo.web import producttar
from gavo.web import vosi

import tresc


class StandardPubDIDTest(testhelpers.VerboseTest):
	def testMakeSPD(self):
		self.assertEqual(rscdef.getStandardPubDID("a/b/c"),
			"ivo://x-unregistred/~?a/b/c")
	
	def testParseSPD(self):
		self.assertEqual(
			rscdef.getAccrefFromStandardPubDID("ivo://x-unregistred/~?a/b/c"),
			"a/b/c")
	
	def testRejectParseSPD(self):
		self.assertRaisesWithMsg(ValueError,
			"'ivo://quatsch/batsch' is not a pubDID within this data center",
			rscdef.getAccrefFromStandardPubDID,
			("ivo://quatsch/batsch",))


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
			'datalink': None,
			'preview': 'data/broken.imp',
			'preview_mime': "text/plain",
			'sourceTable': 'test.prodtest'})

	def testPreview(self):
		prod = products.RAccref.fromString("data/a.imp?preview=true")
		self.assertEqual(prod.params, {"preview": True})


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

# TODO: have test scaffolding (ex.fits?) to actually make these work
	def testScaledProduct(self):
		prod = self._getProductFor("data/b.imp?scale=3")
		self.assertEqual(str(prod), "<Invalid product data/b.imp?scale=3>")
	
	def testCutoutProduct(self):
		res = self._getProductFor("data/b.imp?ra=3&dec=4&sra=2&sdec=4")
		self.assertEqual(str(res), "<Invalid product data/b.imp?"
			"sdec=4.0&dec=4.0&ra=3.0&sra=2.0>")


class _FakeProduct(products.ProductBase):
	def iterData(self):
		yield "1234"
		yield "1234"
		yield "    "*10
		yield "end"


class FileIntfTest(ProductsCoreTest):
	def testFallbackBuffering(self):
		p = _FakeProduct(products.RAccref.fromString("data/a.imp"))
		self.assertEqual(p.read(1), "1")
		self.assertEqual(p.read(1), "2")
		self.assertEqual(p.read(7), "341234 ")
		rest = p.read()
		self.assertEqual(len(rest), 42)
		self.assertEqual(rest[-4:], " end")
		p.close()
	
	def testNativeRead(self):
		p = self._getProductFor("data/a.imp")
		self.assertEqual(p.read(10), "alpha: 23 ")
		self.failUnless(isinstance(p._openedInputFile, file))
		p.close()
		self.assertEqual(p._openedInputFile, None)


class StaticPreviewTest(testhelpers.VerboseTest):

	resources = [('conn', tresc.prodtestTable), ('users', tresc.testUsers)]

	def testStaticPreviewLocal(self):
		prod = products.getProductForRAccref("data/a.imp?preview=True")
		self.failUnless(isinstance(prod, products.StaticPreview))
		self.assertEqual(prod.read(200), 'kaputt.\n')

	def testStaticPreviewRemote(self):
		prod = products.getProductForRAccref("data/b.imp?preview=True")
		self.failUnless(isinstance(prod, products.RemotePreview))
		self.assertEqual(str(prod),
			'<Remote image/jpeg at http://example.com/borken.jpg>')


class AutoPreviewTest(testhelpers.VerboseTest):

	resources = [('fits', tresc.fitsTable)]

	def testAutoPreviewMiss(self):
		prod = products.getProductForRAccref("data/ex.fits?preview=True")
		self.failUnless(isinstance(prod, products.FileProduct))

	def testAutoPreviewHit(self):
		cacheLocation = products.PreviewCacheManager.getCacheName(
			"data/ex.fits")
		with testtricks.testFile(os.path.basename(cacheLocation),
				"Abc, die Katze", inDir=os.path.dirname(cacheLocation)):
			prod = products.getProductForRAccref("data/ex.fits?preview=True")
			self.failUnless(isinstance(prod, products.StaticPreview))
			self.assertEqual(prod.read(200), "Abc, die Katze")


class MangledFITSProductsTest(testhelpers.VerboseTest):
	resources = [("fitsTable", tresc.fitsTable)]

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

	def testCutoutFITS(self):
		prod = products.getProductForRAccref(
			"data/ex.fits?ra=168.24511&dec=22.214493&sra=0.001&sdec=0.001")
		stuff = prod.read()
		self.failUnless("NAXIS1  =                    4" in stuff)
		self.failUnless("NAXIS2  =                    5" in stuff)
		self.failUnless(" \xa8D\xaaG" in stuff)

	def testPreviewFITS(self):
		stuff = products.computePreviewFor(
			products.getProductForRAccref("data/ex.fits"))
		self.assertTrue("JFIF" in stuff)

	def testPreviewCutout(self):
		stuff = products.computePreviewFor(
			products.getProductForRAccref(
			"data/ex.fits?ra=168.24572&dec=22.214473&sra=0.005&sdec=0.005"))
		self.assertTrue("JFIF" in stuff)


class _GlobalFITSLinks(testhelpers.TestResource):
	resources = [("fitsTable", tresc.fitsTable)]

	def make(self, deps):
		svc = api.getRD("//products").getById("dl")
		data, metadata = votable.loads(svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")]}).original[1])
		res = {}
		for link in metadata.iterDicts(data):
			res.setdefault(link["semantics"], []).append(link)
		return res


class GlobalDatalinkTest(testhelpers.VerboseTest):
	resources = [("links", _GlobalFITSLinks())]

	def testNumberOfLinks(self):
		self.assertEqual(sum(len(r) for r in self.links.values()), 2)
	
	def testDatasetMeta(self):
		r, = self.links["#this"]
		self.assertEqual(tuple(r[s] for s in 
			"content_length description error_message content_type ID".split()),
			(5760, "The full dataset.", None, "image/fits",
				"ivo://x-unregistred/~?data/excube.fits"))
	
	def testDatasetURL(self):
		self.assertEqual(self.links["#this"][0]["access_url"],
			"http://localhost:8080/getproduct/data/excube.fits")

	def testPreviewMeta(self):
		r, = self.links["#preview"]
		self.assertEqual(tuple(r[s] for s in 
			"content_length description error_message content_type ID".split()),
			(None, "A preview for the dataset.", None, None,
				"ivo://x-unregistred/~?data/excube.fits"))
	
	def testPreviewURL(self):
		self.assertEqual(self.links["#preview"][0]["access_url"],
			"http://localhost:8080/getproduct/data/excube.fits?preview=True")


# Most datalink/SODA tests now in sodatest.py.  We should drop
# legacy (atomic parameters) datalink support and remove everything
# from here to EOF then.

def _dissectDLFile(datalinkFile):
	"""returns mime and content for a datalink File.

	It also calls cleanup(), if it's there -- basically, that's stuff
	nevow does for us in actual action.
	"""
	content = datalinkFile.fp.getContent()
	datalinkFile.fp.remove()
	if hasattr(datalinkFile, "cleanup"):
		datalinkFile.cleanup(None)
	return datalinkFile.type, content


class DatalinkFITSTest(testhelpers.VerboseTest):
	resources = [("fitsTable", tresc.fitsTable)]

	def testNotFound(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta, dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc">
					<bind key="accrefStart">"data/"</bind>
				</descriptorGenerator>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": ["ivo://junky.ivorn/made/up"]}).original
		self.assertEqual("application/x-votable+xml;content=datalink", mime)
		self.failUnless("<TR><TD>ivo://junky.ivorn/made/up</TD><TD></TD>"
			"<TD></TD><TD>NotFoundFault: Not a pubDID from this site.</TD>" in data)

	def testMakeDescriptor(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc">
					<bind key="accrefStart">"data/"</bind>
				</descriptorGenerator>
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

		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/ex.fits")]}).original
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
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams">
					<bind key="axisMetaOverrides">{
						"RA": {"ucd": "pos.eq.ra;meta.special"},
						3:    {"name": "ANGSTROMS", "unit": "0.1nm"}}
					</bind>
				</metaMaker>
				<FEED source="//datalink#fits_standardLambdaCutout"
					spectralAxis="3"
					wavelengthUnit="'0.1nm'"/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()

		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")]}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@name='RA_MAX']")[0].get("ucd"),
			"par.max;pos.eq.ra;meta.special")
		self.assertEqual(tree.xpath("//PARAM[@name='RA_MAX']/VALUES/MIN"
			)[0].get("value"), "359.3580942")
		self.assertEqual(tree.xpath("//PARAM[@name='DEC_MIN']/VALUES/MAX"
			)[0].get("value"), "30.9848485045")
		self.assertEqual(tree.xpath("//PARAM[@name='ANGSTROMS_MIN']/VALUES/MIN"
			)[0].get("value"), "3749.0")
		self.assertEqual(tree.xpath("//PARAM[@name='ANGSTROMS_MIN']/VALUES/MAX"
			)[0].get("value"), "3755.0")
		lmaxPar = tree.xpath("//PARAM[@name='LAMBDA_MAX']")[0]
		self.assertEqual(lmaxPar.get("ucd"), "par.max;em.wl")
		self.assertEqual(lmaxPar.get("unit"), "m")
		self.assertEqual(lmaxPar.xpath("VALUES/MAX")[0].get("value"),
			"3.755e-07")

	def testCutoutNoSpatialCube(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<dataFormatter procDef="//datalink#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectDLFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"COO_3_MIN": ["3753"],
				"COO_3_MAX": ["3755"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 11)
		self.assertEqual(hdr["NAXIS2"], 7)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testCutoutLAMBDACube(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<FEED source="//datalink#fits_standardLambdaCutout"
					spectralAxis="3"
					wavelengthUnit="'0.1nm'"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<dataFormatter procDef="//datalink#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectDLFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"LAMBDA_MIN": ["3.755e-7"],
				"RA_MIN": ["359.359"],
				"DEC_MIN": ["30.39845"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 8)
		self.assertEqual(hdr["NAXIS2"], 7)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testCutoutCube(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<dataFormatter procDef="//datalink#fits_formatHDUs"/>
			</datalinkCore></service>""")

		mime, data = _dissectDLFile(svc.run("dlget", {
				"ID": [rscdef.getStandardPubDID("data/excube.fits")],
				"RA_MAX": ["359.36"],
				"RA_MIN": ["359.359"],
				"DEC_MAX": ["30.9845"],
				"DEC_MIN": ["30.985"],
				"COO_3_MIN": ["3753"],
				"COO_3_MAX": ["3755"],
				}).original)

		self.assertEqual(mime, "image/fits")
		hdr = fitstools.readPrimaryHeaderQuick(StringIO(data))
		self.assertEqual(hdr["NAXIS1"], 4)
		self.assertEqual(hdr["NAXIS2"], 2)
		self.assertEqual(hdr["NAXIS3"], 2)

	def testKindPar(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<FEED source="//datalink#fits_genKindPar"/>
			</datalinkCore></service>""")
		mime, data = svc.run("dlget", {
			"ID": [rscdef.getStandardPubDID("data/excube.fits")],
			"KIND": ["HEADER"],}).original
		self.assertEqual(mime, "application/fits-header")
		self.assertEqual(len(data), 2880)

	def testCutoutHeader(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker procDef="//datalink#fits_makeWCSParams"/>
				<dataFunction procDef="//datalink#fits_makeHDUList"/>
				<dataFunction procDef="//datalink#fits_doWCSCutout"/>
				<FEED source="//datalink#fits_genKindPar"/>
			</datalinkCore></service>""")
		mime, data = svc.run("dlget", {
			"ID": rscdef.getStandardPubDID("data/excube.fits"),
				"COO_3_MIN": "3753",
			"KIND": "HEADER",}).original
		self.assertEqual(mime, "application/fits-header")
		self.failUnless("NAXIS3  =                    2" in data)

	def testFITSNoSTC(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<FEED source="//datalink#fits_standardDLFuncs"
					accrefStart="" stcs=""/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": rscdef.getStandardPubDID("data/excube.fits")}).original
		self.failUnless("<DATA><TABLEDATA>" in data)

	def testPixelMeta(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<FEED source="//datalink#fits_genPixelPar"/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": rscdef.getStandardPubDID("data/excube.fits")}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(tree.xpath("//PARAM[@name='PIXEL_3_MIN']/VALUES/MAX"
			)[0].get("value"), "4")
		self.assertEqual(tree.xpath("//PARAM[@name='PIXEL_1_MAX']"
			)[0].get("datatype"), "int")

	def testPixelCutout(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<FEED source="//datalink#fits_standardDLFuncs"
					stcs="" accrefStart=""/>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = _dissectDLFile(svc.run("dlget", {
			"ID": rscdef.getStandardPubDID("data/excube.fits"),
				"PIXEL_1_MIN": "4", "PIXEL_1_MAX": "4",
				"PIXEL_3_MIN": "2", "PIXEL_3_MAX": "2"}).original)
		self.assertEqual(mime, "image/fits")
		self.failUnless("NAXIS1  =                    1" in data)
		self.failUnless("NAXIS2  =                    7" in data)
		self.failUnless("NAXIS3  =                    1" in data)


class DatalinkSTCTest(testhelpers.VerboseTest):
	resources = [("fitsTable", tresc.fitsTable)]

	def testSTCDefsPresent(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta,dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker>
					<setup>
						<code>
							parSTC = stc.parseQSTCS("PositionInterval ICRS BARYCENTER"
								' "RA_MIN" "DEC_MIN" "RA_MAX" "DEC_MAX"')
						</code>
					</setup>
					<code>
						for name in ["RA", "DEC"]:
							for ik in genLimitKeys(MS(InputKey, name=name, stc=parSTC)):
								yield ik
					</code>
				</metaMaker>
			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/ex.fits")]}).original
		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(len(tree.xpath(
			"//GROUP[@utype='stc:CatalogEntryLocation']/PARAM")), 4)
		self.assertEqual(len(tree.xpath(
			"//GROUP[@utype='stc:CatalogEntryLocation']/PARAMref")), 4)
		self.assertEqual(tree.xpath(
			"//PARAM[@utype='stc:AstroCoordSystem.SpaceFrame.ReferencePosition']"
			)[0].get("value"), "BARYCENTER")

		# follow a reference
		id = tree.xpath("//PARAMref[@utype='stc:AstroCoordArea"
			".Position2VecInterval.HiLimit2Vec.C2']")[0].get("ref")
		self.assertEqual(tree.xpath("//PARAM[@ID='%s']"%id)[0].get("name"),
			"DEC_MAX")

	def testTwoSystems(self):
		svc = base.parseFromString(svcs.Service, """<service id="foo"
				allowed="dlmeta, dlget">
			<datalinkCore>
				<descriptorGenerator procDef="//datalink#fits_genDesc"/>
				<metaMaker>
					<setup>
						<code>
							parSTC = stc.parseQSTCS("PositionInterval ICRS BARYCENTER"
								' "RA_MIN" "DEC_MIN" "RA_MAX" "DEC_MAX"')
						</code>
					</setup>
					<code>
						for name in ["RA", "DEC"]:
							for ik in genLimitKeys(MS(InputKey, name=name, stc=parSTC)):
								yield ik
					</code>
				</metaMaker>
				<metaMaker>
					<setup>
						<code>
							parSTC = stc.parseQSTCS("PositionInterval GALACTIC"
								' "LAMB_MIN" "BET_MIN" "LAMB_MAX" "BET_MAX"')
						</code>
					</setup>
					<code>
						for name in ["LAMB", "BET"]:
							for ik in genLimitKeys(MS(InputKey, name=name, stc=parSTC)):
								yield ik
					</code>
				</metaMaker>

			</datalinkCore></service>""")
		svc.parent = testhelpers.getTestRD()
		mime, data = svc.run("dlmeta", {
			"ID": [rscdef.getStandardPubDID("data/ex.fits")]}).original

		tree = testhelpers.getXMLTree(data, debug=False)
		self.assertEqual(len(tree.xpath(
			"//GROUP[@utype='stc:CatalogEntryLocation']")), 2)
		ids = [el.get("ref") for el in
				tree.xpath("//PARAMref[@utype='stc:AstroCoordArea"
				".Position2VecInterval.HiLimit2Vec.C2']")]
		names = set(tree.xpath("//PARAM[@ID='%s']"%id)[0].get("name")
			for id in ids)
		self.assertEqual(names, set(["DEC_MAX", "BET_MAX"]))


class MiscTest(testhelpers.VerboseTest):
	def testMediaGuessFITS(self):
		self.assertEqual(products.guessMediaType("foo/bar/gaz42h+88.old.fits"),
			"image/fits")

	def testMediaGuessVOTable(self):
		self.assertEqual(products.guessMediaType("bal.vot"),
			'application/x-votable+xml')

	def testFallback(self):
		self.assertEqual(products.guessMediaType("voo/bar.d/basz"),
			"application/octet-stream")


if __name__=="__main__":
	testhelpers.main(DatalinkFITSTest)
