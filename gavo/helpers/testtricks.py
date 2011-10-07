"""
helper functions and classes for unit tests and similar.
"""

from __future__ import with_statement

import contextlib
import os
import subprocess
import tempfile

from gavo import base


class XSDTestMixin(object):
	"""provides a assertValidates method doing XSD validation.

	assertValidates raises an assertion error with the validator's
	messages on an error.  You can optionally pass a leaveOffending
	argument to make the method store the offending document in
	badDocument.xml.

	The whole thing needs Xerces-J in the form of xsdval.class in the
	current directory.

	The validator itself is a java class xsdval.class built by 
	../schemata/makeValidator.py.  If you have java installed, calling
	that in the schemata directory should just work (TM).  With that
	validator and the schemata in place, no network connection should
	be necessary to run validation tests.
	"""
	def assertValidates(self, xmlSource, leaveOffending=False):
		classpath = ":".join(base.getConfig("xsdclasspath"))
		handle, inName = tempfile.mkstemp("xerctest", "rm")
		try:
			with os.fdopen(handle, "w") as f:
				f.write(xmlSource)
			args = ["java", "-cp", classpath, "xsdval", 
				"-n", "-v", "-s", "-f", inName]

			f = subprocess.Popen(args,
				stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			xercMsgs = f.stdout.read()
			status = f.wait()
			if status or "Error]" in xercMsgs:
				if leaveOffending:
					with open("badDocument.xml", "w") as of:
						of.write(xmlSource)
				raise AssertionError(xercMsgs)
		finally:
			os.unlink(inName)


@contextlib.contextmanager
def testFile(destPath, content):
	"""a context manager that provides and deletes content in a file a destPath.

	As usual, you should not use fixed, predictable file names in tmp.
	"""
	with open(destPath, "w") as f:
		f.write(content)
	try:
		yield
	finally:
		os.unlink(destPath)
