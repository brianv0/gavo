"""
Helper classes for the gavo unittest framework.
"""

import os
import popen2
import sys
import tempfile
import unittest

from gavo import resourcecache
from gavo.parsing import importparser


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

class XSDTestMixin(object):
	"""provides a assertValidates method doing XSD validation.
	
	assertValidates an assertion error with the validator's messages on an
	error.  You can optionally pass a leaveOffending argument to make the
	method store the offending document in badDocument.xml.

	The whole thing currently needs Xerces including the examples at the
	right location.  This clearly is crap, and I'll think of something better
	at some point.  You may need to fix classpath
	"""
	classpath = ("/usr/share/doc/libxerces2-java-doc/examples/xercesSamples.jar:"
	"/usr/share/java/xercesImpl.jar:/usr/share/java/xmlParserAPIs.jar")

	def assertValidates(self, xmlSource, leaveOffending=False):
		# http://apache.org/xml/properties/schema/external-schemaLocation ?
		handle, inName = tempfile.mkstemp("xerctest", "rm")
		try:
			f = os.fdopen(handle, "w")
			f.write(xmlSource)
			f.close()
			f = popen2.Popen4("java -cp %s dom.Counter -n -v -s -f '%s'"%(
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


def getTestRD():
	return resourcecache.getRd(os.path.abspath("test.vord"))


def getTestTable(tableName):
	return getTestRD().getTableDefByName(tableName)


def getTestData(dataId):
	return getTestRD().getDataById(dataId)


def main(testClass, methodPrefix=None):
	if len(sys.argv)>1:
		suite = unittest.makeSuite(testClass, methodPrefix or sys.argv[1])
		runner = unittest.TextTestRunner()
		runner.run(suite)
	else:
		unittest.main()
