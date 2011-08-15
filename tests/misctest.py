"""
Some unit tests not yet fitting anywhere else.
"""

from cStringIO import StringIO
import cgi
import contextlib
import datetime
import httplib
import new
import os
import shutil
import sys
import tempfile
import types
import unittest

import numpy

from gavo import base
from gavo import helpers
from gavo import rscdef
from gavo import rscdesc
from gavo import votable
from gavo import stc
from gavo import utils
from gavo.base import valuemappers
from gavo.helpers import filestuff
from gavo.helpers import testhelpers
from gavo.protocols import creds
from gavo.utils import DEG
from gavo.utils import pyfits
from gavo.utils import stanxml
from gavo.utils import pgsphere
from gavo.votable import tapquery

import tresc


class RenamerDryTest(unittest.TestCase):
	"""tests for some aspects of the file renamer without touching the file system.
	"""
	def testSerialization(self):
		"""tests for correct serialization of clobbering renames.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', '2': '3', '1': '2'}
		self.assertEqual(f.makeRenameProc(fileMap),
			[('b', 'c'), ('a', 'b'), ('2', '3'), ('1', '2')])
	
	def testCycleDetection(self):
		"""tests for cycle detection in renaming recipies.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', 'c': 'a'}
		self.assertRaises(filestuff.Error, f.makeRenameProc, fileMap)


class RenamerWetTest(unittest.TestCase):
	"""tests for behaviour of the file renamer on the file system.
	"""
	def setUp(self):
		def touch(name):
			f = open(name, "w")
			f.close()
		self.testDir = tempfile.mkdtemp("testrun")
		for fName in ["a.fits", "a.txt", "b.txt", "b.jpeg", "foo"]:
			touch(os.path.join(self.testDir, fName))

	def tearDown(self):
		shutil.rmtree(self.testDir, onerror=lambda exc: None)

	def testOperation(self):
		"""tests an almost-realistic application
		"""
		f = filestuff.FileRenamer.loadFromFile(
			StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		found = set(os.listdir(self.testDir))
		expected = set(["b.fits", "b.txt", "c.txt", "c.jpeg", "bar"])
		self.assertEqual(found, expected)
	
	def testNoClobber(self):
		"""tests for effects of repeated application.
		"""
		f = filestuff.FileRenamer.loadFromFile(
			StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		self.assertRaises(filestuff.Error, f.renameInPath, self.testDir)


class TimeCalcTest(testhelpers.VerboseTest):
	"""tests for time transformations.
	"""
	def testJYears(self):
		self.assertEqual(stc.jYearToDateTime(1991.25),
			datetime.datetime(1991, 04, 02, 13, 30, 00))
		self.assertEqual(stc.jYearToDateTime(2005.0),
			datetime.datetime(2004, 12, 31, 18, 0))
	
	def testRoundtrip(self):
		for yr in range(2000):
			self.assertAlmostEqual(2010+yr/1000., stc.dateTimeToJYear(
				stc.jYearToDateTime(2010+yr/1000.)), 7,
				"Botched %f"%(2010+yr/1000.))

	def testBYears(self):
		self.assertEqual(stc.bYearToDateTime(1950.0),
			datetime.datetime(1949, 12, 31, 22, 9, 46, 861900))
	
	def testBRoundtrip(self):
		for yr in range(2000):
			self.assertAlmostEqual(1950+yr/1000., stc.dateTimeToBYear(
				stc.bYearToDateTime(1950+yr/1000.)), 7,
				"Botched %f"%(1950+yr/1000.))

	def testBesselLieske(self):
		"""check examples from Lieske, A&A 73, 282.
		"""
		for bessel, julian in [
				(1899.999142, 1900),
				(1900., 1900.000858),
				(1950., 1949.999790),
				(1950.000210, 1950.0),
				(2000.0, 1999.998722),
				(2000.001278, 2000.0)]:
			self.assertAlmostEqual(stc.dateTimeToJYear(stc.bYearToDateTime(bessel)),
				julian, places=5)


class ProcessorTest(testhelpers.VerboseTest):
	"""tests for some aspects of helper file processors.

	Unfortunately, sequencing is important here, so we do it all in
	one test.  I guess one should rethink things here, but for now let's
	keep things simple.
	"""
	_rdText = """<resource schema="filetest"><data id="import">
		<sources pattern="*.fits"/><fitsProdGrammar/>
		</data></resource>"""

	def _writeFITS(self, destPath, seed):
		hdu = pyfits.PrimaryHDU(numpy.zeros((2,seed+1), 'i2'))
		hdu.header.update("SEED", seed, "initial number")
		hdu.header.update("WEIRD", "W"*seed)
		hdu.header.update("RECIP", 1./(1+seed))
		hdu.writeto(destPath)

	def setUp(self):
		self.resdir = os.path.join(base.getConfig("tempDir"), "filetest")
		self.origInputs = base.getConfig("inputsDir")
		base.setConfig("inputsDir", base.getConfig("tempDir"))
		if os.path.exists(self.resdir): # Leftover from previous run?
			return
		os.mkdir(self.resdir)
		for i in range(10):
			self._writeFITS(os.path.join(self.resdir, "src%d.fits"%i), i)
		f = open(os.path.join(self.resdir, "filetest.rd"), "w")
		f.write(self._rdText)
		f.close()

	def tearDown(self):
		base.setConfig("inputsDir", self.origInputs)
		shutil.rmtree(self.resdir, True)

	class SimpleProcessor(helpers.HeaderProcessor):
		def __init__(self, *args, **kwargs):
			helpers.HeaderProcessor.__init__(self, *args, **kwargs)
			self.headersBuilt = 0

		def _isProcessed(self, srcName):
			return self.getPrimaryHeader(srcName).has_key("SQUARE")

		def _getHeader(self, srcName):
			hdr = self.getPrimaryHeader(srcName)
			hdr.update("SQUARE", hdr["SEED"]**2)
			self.headersBuilt += 1
			return hdr

	def _getHeader(self, srcName):
		hdus = pyfits.open(os.path.join(self.resdir, srcName))
		hdr = hdus[0].header
		hdus.close()
		return hdr

	def _testPlainRun(self):
		# procmain reads argv, don't confuse it
		sys.argv = ["test"]
		# Normal run, no headers present yet
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 10)
		self.failUnless(os.path.exists(
			os.path.join(self.resdir, "src9.fits.hdr")))
		self.failUnless(self._getHeader("src9.fits.hdr").has_key("SQUARE"))
		# we don't run with applyHeaders here
		self.failIf(self._getHeader("src9.fits").has_key("SQUARE"))

	def _testRespectCaches(self):
		"""tests that no processing is done when cached headers are there.

		This needs to run after _testPlainRun.
		"""
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 0)
	
	def _testNoCompute(self):
		"""tests that no computations take place with --no-compute.
		"""
		sys.argv = ["misctest.py", "--no-compute"]
		os.unlink(os.path.join(self.resdir, "src4.fits.hdr"))
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(proc.headersBuilt, 0)

	def _testRecompute(self):
		"""tests that missing headers are recomputed.

		This needs to run before _testApplyCaches and after _testNoCompute.
		"""
		sys.argv = ["misctest.py"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 1)

	def _testApplyCaches(self):
		"""tests the application of headers to sources.

		This needs to run after _testPlainRun
		"""
		sys.argv = ["misctest.py", "--apply"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 0)
		self.failUnless(self._getHeader("src9.fits").has_key("SQUARE"))
		# see if data survived
		hdus = pyfits.open(os.path.join(self.resdir, "src9.fits"))
		na = hdus[0].data
		self.assertEqual(na.shape, (2, 10))
	
	def _testForcedRecompute(self):
		"""tests for working --reprocess.
		"""
		sys.argv = ["misctest.py", "--reprocess"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(proc.headersBuilt, 10)

	def _testBugfix(self):
		"""tests for working --reprocess --apply.

		This must run last since we're monkeypatching SimpleProcessor.
		"""
		def newGetHeader(self, srcName):
			hdr = self.getPrimaryHeader(srcName)
			hdr.update("SQUARE", hdr["SEED"]**3)
			self.headersBuilt += 1
			return hdr
		sys.argv = ["misctest.py", "--reprocess", "--apply"]
		self.SimpleProcessor._getHeader = new.instancemethod(newGetHeader,
			None, self.SimpleProcessor)
		sys.argv = ["misctest.py", "--reprocess"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(self._getHeader("src6.fits.hdr")["SQUARE"], 216)

	def testAll(self):
		self._testPlainRun()
		self._testRespectCaches()
		self._testNoCompute()
		self._testRecompute()
		self._testForcedRecompute()
		self._testApplyCaches()
		self._testForcedRecompute()
		self._testBugfix()


class RemoteURLTest(testhelpers.VerboseTest):
	"""tests for urlopenRemote rejecting unwanted URLs.
	"""
	def testNoFile(self):
		self.assertRaises(IOError,
			utils.urlopenRemote, "file:///etc/passwd")
	
	def testHTTPConnect(self):
		# this assumes nothing actually listens on 57388
		self.assertRaisesWithMsg(IOError,
			"Could not open URL http://localhost:57388: Connection refused",
			utils.urlopenRemote, ("http://localhost:57388",))

	def testMalformedURL(self):
		self.assertRaisesWithMsg(IOError, 
			'Could not open URL /etc/passwd: unknown url type: /etc/passwd',
			utils.urlopenRemote, ("/etc/passwd",))


class StanXMLTest(testhelpers.VerboseTest):
	class Model(object):
		class MEl(stanxml.Element): 
			_local = True
		class Root(MEl):
			_childSequence = ["Child", "Nilble"]
		class Child(MEl):
			_childSequence = ["Foo", None]
		class Other(MEl):
			pass
		class Nilble(stanxml.NillableMixin, MEl):
			_a_restatt = None

	def testNoTextContent(self):
		M = self.Model
		self.assertRaises(stanxml.ChildNotAllowed, lambda:M.Root["abc"])
	
	def testTextContent(self):
		M = self.Model
		data = M.Root[M.Child[u"a\xA0bc"]]
		self.assertEqual(data.render(), '<Root><Child>a&#160;bc</Child></Root>')

	def testRetrieveText(self):
		M = self.Model
		data = M.Other["thrown away", M.Other["mixed"], " remaining "]
		self.assertEqual(data.text_, " remaining ")

	def testNillableNil(self):
		M = self.Model
		rendered = M.Root[M.Nilble()].render()
		self.failUnless('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
			in rendered)
		self.failUnless('Nilble xsi:nil="true"' in rendered)
	
	def testNillableNonNil(self):
		M = self.Model
		rendered = M.Root[M.Nilble["Value"]].render()
		self.failUnless("<Nilble>Value</Nilble>" in rendered)
		self.failIf('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
			in rendered)
	
	def testNillableAttribute(self):
		M = self.Model
		rendered = M.Root[M.Nilble(restatt="x")].render()
		self.failUnless('<Nilble restatt="x" xsi:nil="true" />' in rendered)


class TestGroupsMembership(testhelpers.VerboseTest):
	resources = [('querier', tresc.testUsers)]

	def testGroupsForUser(self):
		"""tests for correctness of getGroupsForUser.
		"""
		self.assertEqual(creds.getGroupsForUser("X_test", "wrongpass"),
			set(), "Wrong password should yield empty set but doesn't")
		self.assertEqual(creds.getGroupsForUser("X_test", "megapass"),
			set(["X_test", "Y_test"]))
		self.assertEqual(creds.getGroupsForUser("Y_test", "megapass"),
			set(["Y_test"]))


_obscoreRDTrunk = """<resource schema="test" resdir="data">
			<table id="glob" onDisk="True" mixin="//products#table">
				<mixin %s>//obscore#publish</mixin>
			</table>
			<data id="import">
				<dictlistGrammar>
					<rowfilter procDef="//products#define">
						<bind key="table">"test.glob"</bind>
						<bind key="accref">@accref</bind>
						<bind key="path">@accref</bind>
						<bind key="fsize">22</bind>
					</rowfilter>
				</dictlistGrammar>
				<make table="glob"/>
			</data></resource>"""


class ObscoreTest(testhelpers.VerboseTest):

	def testTypeRequired(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At (4, 3): Mixin parameter productType mandatory",
			base.parseFromString,
			(rscdesc.RD, _obscoreRDTrunk%""))

	def testRestriction(self):
		self.assertRaises(base.StructureError,
			base.parseFromString,
			rscdesc.RD, _obscoreRDTrunk%'productType="\'image\'" ',
			context=base.ParseContext(restricted=True))

	def testObscoreProperty(self):
		rd = base.parseFromString(rscdesc.RD, 
			_obscoreRDTrunk%'productType="\'image\'" ')
		viewPart = rd.tables[0].properties["obscoreClause"]
		self.failUnless("'image' AS dataproduct_type")
		self.failUnless("$COMPUTE AS obs_publisher_did")
		self.failUnless("size/1024 AS access_estsize")
		self.failUnless("NULL AS s_region")

	def testObscoreLateMixin(self):
		rd = base.parseFromString(rscdesc.RD, 
			_obscoreRDTrunk%'productType="\'image\'" ')
		for script in rd.getById("import").makes[0].scripts:
			if script.id=="addTableToObscoreSources":
				break
		else:
			self.fail("addTableToObscoreSources not added -- did obscore#publish"
				" run?")


class _ObscorePublishedTable(testhelpers.TestResource):

	resources = [('conn', tresc.dbConnection)]

	def make(self, dependents):
		conn = dependents["conn"]
		from gavo import rsc
		dd = base.parseFromString(rscdesc.RD, 
			_obscoreRDTrunk%'productType="\'image\'" '
			'collectionName="\'testing detritus\'"').getById("import")
		dd.rd.sourceId = "__testing__"
		return rsc.makeData(dd, forceSource=[{"accref": "foo/bar"}],
			connection=conn)

	def clean(self, data):
		conn = data.tables["glob"].connection
		try:
			data.drop(data.dd, connection=conn)
			conn.commit()
		except:
			import traceback
			traceback.print_exc()
			conn.rollback()
		res = list(data.tables["glob"].query("select sqlFragment"
			" from ivoa._obscoresources where tableName='test.glob'"))
		# Yes, this is a test within a test resource.  It's most
		# convenient this way.  I'm sorry.
		assert len(res)==0


class ObscorePublishedTest(testhelpers.VerboseTest):

	resources = [('data', _ObscorePublishedTable())]

	def testJoinPresent(self):
		res = list(self.data.tables["glob"].query("select sqlFragment"
			" from ivoa._obscoresources where tableName='test.glob'"))
		self.assertEqual(len(res), 1)
		self.failUnless("'ivo://%s/getproduct#' || accref AS obs_publisher_did"%
			base.getConfig('ivoa', 'authority') in res[0][0])

	def testDataIsInObscore(self):
		from gavo import rsc
		oct = rsc.TableForDef(
			base.caches.getRD("//obscore").getById("ObsCore"),
			connection=self.data.tables["glob"].connection)
		res = list(oct.iterQuery(oct.tableDef,
			"obs_id='foo/bar'"))
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0]["dataproduct_type"], 'image')
		self.assertEqual(res[0]["access_estsize"], 0)

	def testAccessibleThroughADQL(self):
		from gavo.protocols import adqlglue
		from gavo.formats import votablewrite
		querier = base.SimpleQuerier(
			connection=self.data.tables["glob"].connection)
		res = adqlglue.query(querier, "select * from ivoa.ObsCore where"
			" obs_collection='testing detritus'")
		self.failUnless('<TD>http://localhost:8080/getproduct?key=foo/bar</TD>'
			in votablewrite.getAsVOTable(res, tablecoding="td"))


@contextlib.contextmanager
def _fakeHTTPLib(respData="", respStatus=200, 
		mime="application/x-votable", exception=None):
	"""runs a test with a fake httplib connection maker.

	This is for TapquerySyncTest and similar.
	"""
	class FakeResult(object):
		status = respStatus

		def getheader(self, key):
			if key.lower()=='content-type':
				return mime
			else:
				ddt

		def read(self):
			return respData

	class FakeInfo(object):
		pass

	class FakeConnection(object):
		def __init__(self, *args, **kwargs):
			pass

		def request(self, method, path, data, headers):
			FakeInfo.lastData = data
			if exception is not None:
				raise exception

		def getresponse(self, *args, **kwargs):
			return FakeResult()

		def close(self):
			pass
	
	origConn = httplib.HTTPConnection
	httplib.HTTPConnection = FakeConnection
	try:
		yield FakeInfo
	finally:
		httplib.HTTPConnection = origConn



def _scaffoldSyncJob(job, **kwargs):
	job.postToService = types.MethodType(_makeFakeResponder(**kwargs), job)


class TapquerySyncTest(testhelpers.VerboseTest):
# Tests for the tapquery sync object; since TAP queries are expensive,
# we only test things that don't actually run a query.  For more extensive
# exercising, see the taptest RD at the GAVO DC.
	endpoint = "http://dachstest"

	def testNoResult(self):
		job = votable.ADQLSyncJob(self.endpoint, 
			"select * from tap_schema.tables")
		self.assertRaisesWithMsg(tapquery.Error,
			"No result in so far",
			job.openResult,
			())

	def testWrongStatus(self):
		with _fakeHTTPLib(respData="oops", respStatus=404):
			job = votable.ADQLSyncJob(self.endpoint, 
				"select * from tap_schema.tables")
			self.assertRaises(tapquery.WrongStatus, job.start)
			self.assertEqual(job.getErrorFromServer(), "oops")

	def testHTTPError(self):
		import socket
		with _fakeHTTPLib(respData="oops", exception=socket.error("timeout")):
			job = votable.ADQLSyncJob(self.endpoint, 
				"select * from tap_schema.tables")
			self.assertRaises(tapquery.NetworkError, job.start)
			self.assertEqual(job.getErrorFromServer(), 
				'Problem connecting to dachstest (timeout)')

	def testTAPError(self):
		with _fakeHTTPLib(respData="""<VOTABLE version="1.2" xmlns:vot="http://www.ivoa.net/xml/VOTable/v1.2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.ivoa.net/xml/VOTable/v1.2 http://vo.ari.uni-heidelberg.de/docs/schemata/VOTable-1.2.xsd"><RESOURCE type="results"><INFO name="QUERY_STATUS" value="ERROR">Could not parse your query: Expected "SELECT" (at char 0), (line:1, col:1)</INFO></RESOURCE></VOTABLE>""", respStatus=400):
			job = votable.ADQLSyncJob(self.endpoint, 
				"selct * from tap_schema.tables")
			self.assertRaises(tapquery.WrongStatus, job.start)
			self.assertEqual(job.getErrorFromServer(), 
				'Could not parse your query: Expected "SELECT" (at char 0),'
				' (line:1, col:1)')

	def testConstructionParameters(self):
		with _fakeHTTPLib(respData="ok") as fakeInfo:
			job = votable.ADQLSyncJob(self.endpoint, 
				"select * from tap_schema.tables", userParams={"MAXREC": 0})
			job.start()
			self.assertEqual(cgi.parse_qs(fakeInfo.lastData)["MAXREC"], ["0"])
		
	def testLaterParameters(self):
		with _fakeHTTPLib(respData="ok") as fakeInfo:
			job = votable.ADQLSyncJob(self.endpoint, 
				"select * from tap_schema.tables")
			job.setParameter("MAXREC", 0)
			job.start()
			self.assertEqual(cgi.parse_qs(fakeInfo.lastData)["MAXREC"], ["0"])


class MatrixTest(testhelpers.VerboseTest):
	def testVecMul(self):
		mat = utils.Matrix3([1, 0, 1], [-1, 1, 0], [0, -1, -1])
		self.assertEqual(mat.vecMul((3, 8, -1)), (2, 5, -7))
	
	def testMatMul(self):
		mat1 = utils.Matrix3([1, 0, 1], [-1, 1, 0], [0, -1, -1])
		mat2 = utils.Matrix3(*mat1.getColumns())
		self.assertEqual(mat1.matMul(mat2), utils.Matrix3(
			(2, -1, -1), (-1, 2, -1), (-1, -1, 2)))


class PgSphereDryTest(testhelpers.VerboseTest):
# Tests for pgsphere interface that don't need DB connectivity
# (others are in dbtest)
	def _assertCircleBecomesPolygon(self, alpha, delta, radius):
		alpha, delta, radius = alpha*DEG, delta*DEG, radius*DEG
		c = pgsphere.SCircle(pgsphere.SPoint(alpha, delta), radius)
		centerVec = utils.spherToCart(alpha, delta)
		for pt in c.asPoly().points:
			circleVec = utils.spherToCart(pt.x, pt.y)
			self.assertAlmostEqual(utils.spherDist(circleVec, centerVec), radius)
	
	def testCircle1AsPoly(self):
		self._assertCircleBecomesPolygon(0, 90, 3)

	def testCircle2AsPoly(self):
		self._assertCircleBecomesPolygon(0, 0, 8)

	def testCircle3AsPoly(self):
		self._assertCircleBecomesPolygon(80, -10, 20)

	def testCircle4AsPoly(self):
		self._assertCircleBecomesPolygon(120, -80, 1)

	def testCircle5AsPoly(self):
		self._assertCircleBecomesPolygon(220, -45, 1)

	def testCircle6AsPoly(self):
		self._assertCircleBecomesPolygon(320, 45, 90)

	def testPolyAsPoly(self):
		p = pgsphere.SPoly([pgsphere.SPoint(*p) for p in
			((0.5, 0.4), (1, -0.2), (1.5, 0))])
		self.failUnless(p.asPoly() is p)
	
	def testNormSboxAsPoly(self):
		b = pgsphere.SBox(pgsphere.SPoint(0.2, -0.5), pgsphere.SPoint(2, 0.1))
		self.assertEqual(b.asPoly(),
			pgsphere.SPoly([pgsphere.SPoint(*p) for p in
			((0.2, -0.5), (0.2, 0.1), (2, 0.1), (2, -0.5))]))

	def testInvSboxAsPoly(self):
		b = pgsphere.SBox(pgsphere.SPoint(2, 0.1), pgsphere.SPoint(-0.1, -0.5))
		self.assertEqual(b.asPoly(),
			pgsphere.SPoly([pgsphere.SPoint(*p) for p in
			((-0.1, -0.5), (-0.1, 0.1), (2, 0.1), (2, -0.5))]))

if __name__=="__main__":
	testhelpers.main(PgSphereDryTest)
