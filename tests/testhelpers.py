"""
Helper classes for the gavo unittest framework.
"""

import os
import popen2
import tempfile
import unittest


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

