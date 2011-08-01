"""
Tests for the products infrastructure.
"""

from cStringIO import StringIO
import os
import tarfile

from gavo import api
from gavo import base
from gavo import svcs
from gavo.helpers import testhelpers
from gavo.protocols import products
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


class FatProductTest(testhelpers.VerboseTest):
	def testBadConstructorArg(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Invalid constructor argument(s) to FatProductKey: klonk",
			products.FatProductKey,
			(), key="testing", klonk=0)

	def testBadConstructurVals(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Invalid value for constructor argument to FatProductKey:"
				" scale='klonk'",
			products.FatProductKey,
			(), key="testing", scale="klonk")

	def testKeyMandatory(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Must give key when constructing FatProductKey",
			products.FatProductKey,
			(), scale="2")

	def testSerialization(self):
		pk = products.FatProductKey(
			key="extra weird/product+name%something.fits",
			scale=4)
		self.assertEqual(str(pk),
			"extra+weird%2Fproduct%2Bname%25something.fits&scale=4")

	def testFromRequestSimple(self):
		class req(object):
			args = {"key": ["extra weird+key"], "scale": []}
		pk = products.FatProductKey.fromRequest(req)
		self.assertEqual(pk, products.FatProductKey(
			key="extra weird+key"))

	def testFromBadRequest(self):
		class req(object):
			args = {"scale": ["3"]}
		self.assertRaisesWithMsg(base.ValidationError,
			"Must give key when constructing FatProductKey",
			products.FatProductKey.fromRequest,
			(req,))

	def testFromString(self):
		self.assertEqual(products.FatProductKey.fromString(
			"extra%20weird%2bkey&ra=2&sra=0.5&dec=4&sdec=0.75"),
			products.FatProductKey(key="extra weird+key", ra=2,
				sra=0.5, dec=4, sdec=0.75))
	
	def testBadFromString(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Invalid constructor argument(s) to FatProductKey: klonk",
			products.FatProductKey.fromString,
			("worz&klonk=huhu",))


class ProductsCoreTest(_TestWithProductsTable):
	def _getProductFor(self, accref, moreFields={}):
		inData = {"accref": products.FatProductKey.fromString(accref)}
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
		res = self._getProductFor("data/a.imp&scale=2")
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

	def testScaledProduct(self):
		res = self._getProductFor("data/b.imp&scale=3")
		self.failUnless(isinstance(res, products.ScaledProduct))
		self.assertRaisesWithMsg(NotImplementedError,
			"Cannot scale yet",
			self._getOutput, 
			(res,))
	
	def testCutoutProduct(self):
		res = self._getProductFor("data/b.imp&ra=3&dec=4&sra=2&sdec=4")
		self.failUnless(isinstance(res, products.CutoutProduct))
		self.assertRaisesWithMsg(NotImplementedError,
			"Cannot generate cutouts for anything but FITS yet.",
			self._getOutput, 
			(res,))


if __name__=="__main__":
	testhelpers.main(TarTest)
