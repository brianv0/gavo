"""
Tests for the products infrastructure.
"""

from cStringIO import StringIO
import datetime
import os
import struct
import tarfile

from gavo import api
from gavo import base
from gavo import svcs
from gavo.helpers import testhelpers
from gavo.protocols import products
from gavo.utils import fitstools
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
		res = self.tarService.runFromDict(inDict, "form", queryMeta=qm)
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
			"Invalid value for constructor argument to RAccref:"
				" scale='klonk'",
			products.RAccref,
			("testing", {"scale": "klonk"}))

	def testKeyMandatory(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Must give key when constructing RAccref",
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
			"Invalid value for constructor argument to RAccref: sra='huhu'",
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
		inData = {"accref": products.RAccref.fromString(accref)}
		inData.update(moreFields)
		svc = base.caches.getRD("//products").getById("p")
		rows = svc.runFromDict(inData, renderer="get"
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
			"Cannot generate cutouts for anything but FITS yet.",
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

if __name__=="__main__":
	testhelpers.main(RaccrefTest)
