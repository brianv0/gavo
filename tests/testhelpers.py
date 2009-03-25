"""
Helper classes for the gavo unittest framework.
"""

import os
import popen2
import sys
import tempfile
import unittest


from gavo import base

# this only needs to be set correctly if you run twisted trial-based tests
testsDir = "/home/msdemlei/gavo/trunk/tests"


class VerboseTest(unittest.TestCase):
	"""contains a few methods for improved error reporting.
	"""
	def assertEqualForArgs(self, callable, result, *args):
		self.assertEqual(callable(*args), result, 
			"Failed for arguments %s.  Expected result is: %s, result found"
			" was: %s"%(str(args), repr(result), repr(callable(*args))))

	def assertRaisesVerbose(self, exception, callable, args, msg):
		try:
			callable(*args)
		except exception:
			return
		except:
			raise
		else:
			raise self.failureException(msg)

	def assertRaisesWithMsg(self, exception, errMsg, callable, args, msg=None):
		try:
			callable(*args)
		except exception, ex:
			if str(ex)!=errMsg:
				raise self.failureException(
					"Expected %r, got %r as exception message"%(errMsg, str(ex)))
		except:
			raise
		else:
			raise self.failureException(msg or "%s not raised"%exception)

	def assertRuns(self, callable, args, msg=None):
		try:
			callable(*args)
		except Exception, ex:
			raise self.failureException("Should run, but raises %s (%s) exception"%(
				ex.__class__.__name__, str(ex)))


class XSDTestMixin(object):
	"""provides a assertValidates method doing XSD validation.

	assertValidates raises an assertion error with the validator's
	messages on an error.  You can optionally pass a leaveOffending
	argument to make the method store the offending document in
	badDocument.xml.

	The whole thing currently needs Xerces including the examples at
	the right location.  You may need to fix classpath if you're not 
	on Debian.

	The validator itself is a java class xsdval.class built by 
	../schemata/makeValidator.py.  If you have java installed, calling
	that in the schemata directory should just work (TM).  With that
	validator and the schemata in place, no network connection should
	be necessary to run validation tests.
	"""
	classpath = (
		".:/usr/share/java/xercesImpl.jar:/usr/share/java/xmlParserAPIs.jar")

	def assertValidates(self, xmlSource, leaveOffending=False):
		if not os.path.exists("xsdval.class"):
			raise AssertionError("Validation test fails since xsdval.class"
				" is not present.  Run python schemata/makeValidator.py")
		handle, inName = tempfile.mkstemp("xerctest", "rm")
		try:
			f = os.fdopen(handle, "w")
			f.write(xmlSource)
			f.close()
			f = popen2.Popen4("java -cp %s xsdval -n -v -s -f '%s'"%(
				self.classpath, inName))
			xercMsgs = f.fromchild.read()
			status = f.wait()
			if status or "Error]" in xercMsgs:
				if leaveOffending:
					of = open("badDocument.xml", "w")
					of.write(xmlSource)
					of.close()
				raise AssertionError(xercMsgs)
		finally:
			os.unlink(inName)


class SamplesBasedAutoTest(type):
	"""A metaclass that builds tests out of a samples attribute of a class.

	To use this, give the class a samples attribute containing a sequence
	of anything, and a _runTest(sample) method receiving one item of
	that sequence.

	The metaclass will create one test<n> method for each sample.
	"""
	def __new__(cls, name, bases, dict):
		for sampInd, sample in enumerate(dict["samples"]):
			def testFun(self, sample=sample):
				self._runTest(sample)
			dict["test%02d"%sampInd] = testFun
		return type.__new__(cls, name, bases, dict)


def getTestRD():
	from gavo import rscdesc
	from gavo.protocols import basic
	return base.caches.getRD(os.path.abspath("test.rd"))


def getTestTable(tableName):
	return getTestRD().getTableDefById(tableName)


def getTestData(dataId):
	return getTestRD().getDataById(dataId)


def trialMain(testClass):
	from twisted.trial import runner
	from twisted.scripts import trial as script
	config = script.Options()
	config.parseOptions()
	trialRunner = script._makeRunner(config)
	if len(sys.argv)>1:
		suite = runner.TestSuite()
		for t in sys.argv[1:]:
			suite.addTest(testClass(t))
	else:
		sys.argv.append(sys.argv[0])
		config.parseOptions()
		suite = script._getSuite(config)
	trialRunner.run(suite)
	

def main(testClass, methodPrefix=None):
	if len(sys.argv)>1:
		suite = unittest.makeSuite(testClass, methodPrefix or sys.argv[1])
		runner = unittest.TextTestRunner()
		runner.run(suite)
	else:
		unittest.main()
