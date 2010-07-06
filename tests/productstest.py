"""
XXX TODO: Resurrect this; this stuff is now synchronous and can thus
be tested with the normal unittest framework.  You'll need to change
ProductCoreTest and then derive it from testhelpers.VerboseTest.

Tests for the products infrastructure.
"""

'''
from cStringIO import StringIO
import os
import unittest

from twisted.trial.unittest import TestCase as TrialTest

from gavo import config, sqlsupport, record
from gavo.parsing import importparser, resource
from gavo.web import product, service, standardcores, common, creds

import testhelpers


creds.adminProfile = "test"


def importSomeProducts():
	config.setDbProfile("test")
	rd = testhelpers.getRd("data/test")
	tableDef = rd.getTableDefByName("prodtest")
	res = resource.Resource(rd)
	res.importData(None, ["productimport"])
	res.export("sql", ["productimport"])


def forgetSomeProducts():
	rd = importparser.getRd("test")
	tableDef = rd.getTableDefByName("prodtest")
	tw = rsc.TableForDef(tableDef)
	tw.drop().commit().close()


def createTestUser():
	querier = sqlsupport.SimpleQuerier(useProfile="test")
	try:
		creds._addUser(querier, "test", "megapass")
	except creds.ArgError:  # user probably still exists from a previous run
		pass
	querier.commit()


def deleteTestUser():
	return
	querier = sqlsupport.SimpleQuerier(useProfile="test")
	creds._delUser(querier, "test")
	querier.finish()


class ProductCoreTest(object):
	"""tests for the products core.
	"""
	timeout = 10

	def setUp(self):
		importSomeProducts()
		self.rd = importparser.getRd("__system__/products/products")
		self.core = product.ProductCore(self.rd, {})
		self.service = service.Service(self.rd, {"condDescs":
			record.DataFieldList([standardcores.CondDesc.fromInputKey(f)
				for f in self.core.getInputFields()])})
		self.service.set_core(self.core)

	def tearDown(self):
		forgetSomeProducts()
	
	def _testCoreRun(self, input, checker, queryMeta=common.emptyQueryMeta):
		"""runs input through the core, sending the result to the checker callback.
		"""
		return self.core.run(
			self.service.getInputData(input), queryMeta
			).addCallback(checker)

	def _makeChecker(self, resLen, res0class, res0path, res0mime):
		def checkResult(res):
			rows = res.getPrimaryTable().rows
			self.assertEqual(len(rows), resLen)
			rsc = rows[0]["source"]
			self.assert_(isinstance(rsc, res0class), "Product returned has"
				" class %s instead of %s"%(rsc.__class__.__name__,
					res0class.__name__))
			self.assertEqual(rsc.sourcePath, res0path)
			self.assertEqual(rsc.contentType, res0mime)
			return rsc
		return checkResult

	def testNormal(self):
		"""tests for resolution of "normal" products.
		"""
		return self._testCoreRun({"key": "data/b.imp"}, self._makeChecker(
			1, product.PlainProduct, '/home/msdemlei/gavo/trunk/tests/data/b.imp',
			'application/octet-stream'))

	def testRestrictedAnonymous(self):
		"""tests for resolution of restricted products for an anonymous user.
		"""
		return self._testCoreRun({"key": "data/a.imp"}, self._makeChecker(
			1, product.UnauthorizedProduct, 
			'/home/msdemlei/gavo/trunk/tests/data/a.imp', 
			'application/octet-stream'))

	def testRestrictedGoodAuth(self):
		"""tests for return of a protected product with good cred.
		"""
		createTestUser()
		defaultChecker = self._makeChecker(1, product.PlainProduct, 
			'/home/msdemlei/gavo/trunk/tests/data/a.imp', 
			'application/octet-stream')

		def checkResult(res):
			deleteTestUser()   # stale user will stay on error...
			rsc = defaultChecker(res)
			# make sure we can write the thing
			f = StringIO()
			rsc(f)
			self.assertEqual(f.getvalue(), 'alpha: 23 34 33.45\ndelta:'
				' -45 34 59.7\nobject: gabriel\nembargo: 2030-12-31\n')

		qm = common.QueryMeta()
		qm["user"], qm["password"] = "test", "megapass"
		return self._testCoreRun({"key": "data/a.imp"}, checkResult, qm)

	def testRestrictedBadAuth(self):
		"""tests for return of a protected product with bad cred.
		"""
		createTestUser()

		defaultChecker = self._makeChecker(1, product.UnauthorizedProduct, 
			'/home/msdemlei/gavo/trunk/tests/data/a.imp', 
			'application/octet-stream')

		def checkResult(res):
			deleteTestUser()   # stale user will stay on error...
			defaultChecker(res)

		qm = common.QueryMeta()
		qm["user"], qm["password"] = "test", "wrong"
		return self._testCoreRun({"key": "data/a.imp"}, checkResult, qm)

	def testCutout(self):
		"""tests for processing cutouts.
		"""
		defaultChecker = self._makeChecker(1, product.CutoutProduct,
			None, 'image/fits')

		def checkResult(res):
			rsc = defaultChecker(res)
			self.assertEqual(rsc.fullFilePath,
				'/home/msdemlei/gavo/trunk/tests/data/b.imp')

		return self._testCoreRun(
			{"key": "data/b.imp&ra=10.2&dec=14.53&sra=0.4&sdec=3.4"}, 
			checkResult)


if __name__=="__main__":
	testhelpers.trialMain(ProductCoreTest)
'''
