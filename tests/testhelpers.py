"""
Helper classes for the gavo unittest framework.
"""

from __future__ import with_statement

import cPickle as pickle
import gc
import inspect
import os
import popen2
import re
import subprocess
import sys
import traceback
import tempfile
import unittest
from cStringIO import StringIO

from gavo.imp import testresources
from gavo.imp.testresources import TestResource

# Here's the deal on TestResource: When setting up complicated stuff for
# tests (like, a DB table), define a TestResource for it.  Override
# the make() method returning something and the clean() method to destroy
# whatever you created in make().
#
# Then, in VerboseTests, have a class attribute
# resource = [(name1, res1), (name2, res2)]
# giving attribute names and resource *instances*.
# There's an example in adqltest.py
# 
# If you use this and you have a setUp of your own, you *must* call 
# the superclass's setUp method.

# Do we want this?  I think it's currently not used.
testsDir = "/home/msdemlei/gavo/trunk/tests"


class ForkingSubprocess(subprocess.Popen):
	"""A subprocess that doesn't exec but fork.
	"""
	def _execute_child(self, args, executable, preexec_fn, close_fds,
						   cwd, env, universal_newlines,
						   startupinfo, creationflags, shell,
						   p2cread, p2cwrite,
						   c2pread, c2pwrite,
						   errread, errwrite):
# stolen from 2.5 subprocess.  Unfortunately, I can't just override the
# exec action.
			"""Execute program (POSIX version)"""

			if isinstance(args, basestring):
				args = [args]
			else:
				args = list(args)

			if shell:
				args = ["/bin/sh", "-c"] + args

			if executable is None:
				executable = args[0]

			gc_was_enabled = gc.isenabled()
			# Disable gc to avoid bug where gc -> file_dealloc ->
			# write to stderr -> hang.  http://bugs.python.org/issue1336
			gc.disable()
			try:
				self.pid = os.fork()
			except:
				if gc_was_enabled:
					gc.enable()
				raise
			self._child_created = True
			if self.pid == 0:
				# Child
				try:
					# Close parent's pipe ends
					if p2cwrite:
						os.close(p2cwrite)
					if c2pread:
						os.close(c2pread)
					if errread:
						os.close(errread)

					# Dup fds for child
					if p2cread:
						os.dup2(p2cread, 0)
					if c2pwrite:
						os.dup2(c2pwrite, 1)
					if errwrite:
						os.dup2(errwrite, 2)

					# Close pipe fds.  Make sure we don't close the same
					# fd more than once, or standard fds.
					if p2cread and p2cread not in (0,):
						os.close(p2cread)
					if c2pwrite and c2pwrite not in (p2cread, 1):
						os.close(c2pwrite)
					if errwrite and errwrite not in (p2cread, c2pwrite, 2):
						os.close(errwrite)

					# Close all other fds, if asked for
					if close_fds:
						self._close_fds()

					if cwd is not None:
						os.chdir(cwd)

					if preexec_fn:
						apply(preexec_fn)
				
					exitcode = 0
					sys.argv = args
					try:
						executable()
					except SystemExit, ex:
						exitcode = ex.code
					sys.stderr.close()
					sys.stdout.close()
					os._exit(exitcode)

				except:
					traceback.print_exc()
				# This exitcode won't be reported to applications, so it
				# really doesn't matter what we return.
				os._exit(255)

			# Parent
			if gc_was_enabled:
				gc.enable()
			if p2cread and p2cwrite:
				os.close(p2cread)
			if c2pwrite and c2pread:
				os.close(c2pwrite)
			if errwrite and errread:
				os.close(errwrite)


class VerboseTest(testresources.ResourcedTestCase):
	"""A TestCase with a couple of convenient assert methods.
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
			if msg is None:
				msg = ("Should run, but raises %s (%s) exception"%(
					ex.__class__.__name__, str(ex)))
			raise self.failureException(msg)

	def assertAlmostEqualVector(self, first, second, places=7, msg=None):
		try:
			for f, s in zip(first, second):
				self.assertAlmostEqual(f, s, places)
		except AssertionError:
			if msg:
				raise AssertionError(msg)
			else:
				raise AssertionError("%s != %s within %d places"%(
					first, second, places))
	
	def assertOutput(self, toExec, argList, expectedStdout=None, 
			expectedStderr="", expectedRetcode=0, input=None,
			stdoutStrings=None):
		"""checks that execName called with argList has the given output and return
		value.

		expectedStdout and expectedStderr can be functions.  In that case,
		the output is passed to the function, and an assertionError is raised
		if the functions do not return true.

		The 0th argument in argList is automatically added, only pass "real"
		command line arguments.

		toExec may also be a zero-argument python function.  In that case, the
		process is forked and the function is called, with sys.argv according to
		argList.  This helps to save startup time for python main functions.
		"""
		if isinstance(toExec, basestring):
			p = subprocess.Popen([toExec]+argList, executable=toExec, 
				stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
		else:
			p = ForkingSubprocess(["test harness"]+argList, executable=toExec, 
				stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
		out, err = p.communicate(input=input)
		retcode = p.wait()

		try:
			self.assertEqual(expectedRetcode, retcode)

			if isinstance(expectedStderr, basestring):
				self.assertEqual(err, expectedStderr)
			else:
				self.failUnless(expectedStderr(err))
		except AssertionError:
			with open("output.stderr", "w") as f:
				f.write(out)
			raise

		try:
			if isinstance(expectedStdout, basestring):
				self.assertEqual(out, expectedStdout)
			elif expectedStdout is not None:
				self.failUnless(expectedStdout(out))
			if stdoutStrings:
				for s in stdoutStrings:
					self.failIf(s not in out, "%s missing"%s)
		except AssertionError:
			with open("output.stdout", "w") as f:
				f.write(out)
			raise


_xmlJunkPat = re.compile("|".join([
	'(xmlns(:[a-z0-9]+)?="[^"]*"\s*)',
	'((frame_|coord_system_)?id="[^"]*")',
	'(xsi:schemaLocation="[^"]*"\s*)']))

def cleanXML(aString):
	"""removes IDs and some other detritus from XML literals.

	The result will be invalid XML, and all this assumes the fixed-prefix
	logic of the DC software.  Still, it may help making tests against XML
	literals a bit more stable.
	"""
	return re.sub("\s+", " ", _xmlJunkPat.sub('', aString)).strip()


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
		for sampInd, sample in enumerate(dict.get("samples", ())):
			def testFun(self, sample=sample):
				self._runTest(sample)
			dict["test%02d"%sampInd] = testFun
		return type.__new__(cls, name, bases, dict)


def getTestRD(id="test.rd"):
	from gavo import rscdesc
	from gavo.protocols import basic
	from gavo.web import resourcebased  # for registration of the form renderer
	from gavo import base
	return base.caches.getRD("data/%s"%id)


def getTestTable(tableName, id="test.rd"):
	return getTestRD(id).getTableDefById(tableName)


def getTestData(dataId):
	return getTestRD().getDataById(dataId)


def captureOutput(callable, args=(), kwargs={}):
	"""runs callable(*args, **kwargs) and captures the output.

	The function returns a tuple of return value, stdout output, stderr output.
	"""
	realOut, realErr = sys.stdout, sys.stderr
	sys.stdout, sys.stderr = StringIO(), StringIO()
	try:
		retVal = callable(*args, **kwargs)
	finally:
		outCont, errCont = sys.stdout.getvalue(), sys.stderr.getvalue()
		sys.stdout, sys.stderr = realOut, realErr
	return retVal, outCont, errCont


def main(testClass, methodPrefix=None):
	if len(sys.argv)>2:
		testClass = inspect.stack()[1][0].f_globals[sys.argv[-2]]
	if len(sys.argv)>1:
		suite = unittest.makeSuite(testClass, methodPrefix or sys.argv[-1],
			suiteClass=testresources.OptimisingTestSuite)
		runner = unittest.TextTestRunner()
		runner.run(suite)
	else:
		unittest.main()


try:
# do a q'n'd test setup of the DC software if possible.  It would probably
# be better to use stuff like testEnv tresc.py had until rev. 1328 and
# have tests declare they need this -- but aw, there's little to be gained
# by this sort of bureaucracy.
	from gavo import base
	origInputs = base.getConfig("inputsDir")
	base.setConfig("inputsDir", os.getcwd())
	os.environ["GAVO_INPUTSDIR"] = os.getcwd()
	base.setDBProfile("test")
except ImportError:
	pass
