"""
Helper classes for the DaCHS' unit tests.

WARNING: This messes up some global state.  DO NOT import into modules
doing regular work.  testtricks is the module for that kind for stuff.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import BaseHTTPServer
import contextlib
import gc
import os
import pickle
import re
import subprocess
import sys
import threading
import traceback
import unittest
import warnings
from cStringIO import StringIO

from nevow import inevow
from nevow.testutil import FakeRequest
from twisted.python.components import registerAdapter

# This sets up a test environment of the DaCHS software.
#
# To make this work, the current user must be allowed to run
# createdb (in practice, you should have done something like
#
# sudo -u postgres -s `id -nu`
#
# You should be able to tear both ~/_gavo_test and the database 
# down, and this should automatically recreate everything.  That's 
# an integration test for DaCHS, too.
#
# This must be run before anything else from gavo is imported because
# it manipulates the config stuff; this, in turn, runs as soon as
# base is imported.

# The following forces tests to be run from the tests directory.  
# Reasonable, I'd say.
#
# All the custom setup can be suppressed by setting a GAVO_OOTTEST
# env var before importing this.  That's for "out of tree test"
# and is used by the relational registry "unit" tests (and possibly
# others later).
if "GAVO_OOTTEST" in os.environ:
	from gavo import base

else:
	TEST_BASE = os.getcwd()
	originalEnvironment = os.environ.copy()
	os.environ["GAVOCUSTOM"] = "/invalid"
	os.environ["GAVOSETTINGS"] = os.path.join(TEST_BASE, 
		"test_data", "test-gavorc")
	if not os.path.exists(os.environ["GAVOSETTINGS"]):
		warnings.warn("testhelpers imported from non-test directory.  This"
			" is almost certainly not what you want (or set GAVO_OOTTEST).")

	from gavo import base #noflake: import above is conditional
	dbname = "dachstest"
	if not os.path.exists(base.getConfig("rootDir")):
		from gavo.user import initdachs
		try:
			dsn = initdachs.DSN(dbname)
			subprocess.call(["createdb", "--template=template0", 
				"--encoding=UTF-8", "--locale=C", dbname])
			initdachs.createFSHierarchy(dsn, "test")

			with open(os.path.join(
					base.getConfig("configDir"), "defaultmeta.txt"), "a") as f:
				f.write("!organization.description: Mein w\xc3\xbcster Club\n")
				f.write("!contact.email: invalid@whereever.else\n")
			from gavo.base import config
			config.makeFallbackMeta(reload=True)

			os.symlink(os.path.join(TEST_BASE, "test_data"),
				os.path.join(base.getConfig("inputsDir"), "data"))
			os.rmdir(os.path.join(base.getConfig("inputsDir"), "__system"))
			os.symlink(os.path.join(TEST_BASE, "test_data", "__system"),
				os.path.join(base.getConfig("inputsDir"), "__system"))
			os.mkdir(os.path.join(base.getConfig("inputsDir"), "test"))
			initdachs.initDB(dsn)

			from gavo.registry import publication
			from gavo import rsc
			from gavo import rscdesc #noflake: caches registration
			from gavo import base
			publication.updateServiceList([base.caches.getRD("//services")])

			# Import some resources necessary in trial tests
			rsc.makeData(
				base.caches.getRD("data/ssatest").getById("test_import"))
			rsc.makeData(
				base.caches.getRD("//obscore").getById("create"))
			rsc.makeData(
				base.resolveCrossId("//uws#enable_useruws"))
		except:
			traceback.print_exc()
			sys.stderr.write("Creation of test environment failed.  Remove %s\n"
				" before trying again.\n"%(base.getConfig("rootDir")))
			sys.exit(1)

	else:
		# run any pending upgrades (that's a test for them, too... of sorts)
		from gavo.user import upgrade
		upgrade.upgrade()

	# the following only needs to be set correctly if you run 
	# twisted trial-based tests
	testsDir = TEST_BASE


class FakeSimbad(object):
	"""we monkeypatch simbadinterface such that we don't query simbad during
	tests.

	Also, we don't persist cached Simbad responses.  It's a bit sad that
	that functionality therefore doesn't get exercised.
	"""
	simbadData = {'Aldebaran': {'RA': 68.98016279,
  	'dec': 16.50930235,
  	'oname': 'Aldebaran',
  	'otype': 'LP?'},
 	 u'M1': {'RA': 83.63308333, 'dec': 22.0145, 'oname': 'M1', 'otype': 'SNR'},
 	 'Wozzlfoo7xx': None}

	def __init__(self, *args, **kwargs):
		pass
	
	def query(self, ident):
		return self.simbadData.get(ident)




from gavo.imp import testresources
from gavo.imp.testresources import TestResource  #noflake: exported name
from gavo.helpers.testtricks import (  #noflake: exported names
	XSDTestMixin, testFile, getMemDiffer) 

# Here's the deal on TestResource: When setting up complicated stuff for
# tests (like, a DB table), define a TestResource for it.  Override
# the make(dependents) method returning something and the clean(res) 
# method to destroy whatever you created in make().
#
# Then, in VerboseTests, have a class attribute
# resource = [(name1, res1), (name2, res2)]
# giving attribute names and resource *instances*.
# There's an example in adqltest.py
# 
# If you use this and you have a setUp of your own, you *must* call 
# the superclass's setUp method.


class ForkingSubprocess(subprocess.Popen):
	"""A subprocess that doesn't exec but fork.
	"""
	def _execute_child(self, args, executable, preexec_fn, close_fds,
							 cwd, env, universal_newlines,
							 startupinfo, creationflags, shell, to_close,
							 p2cread, p2cwrite,
							 c2pread, c2pwrite,
							 errread, errwrite):
# stolen from 2.7 subprocess.  Unfortunately, I can't just override the
# exec action.

		sys.argv = args
		if executable is None:
				executable = args[0]

		def _close_in_parent(fd):
				os.close(fd)
				to_close.remove(fd)

		# For transferring possible exec failure from child to parent
		# The first char specifies the exception type: 0 means
		# OSError, 1 means some other error.
		errpipe_read, errpipe_write = self.pipe_cloexec()
		try:
				try:
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
										if p2cwrite is not None:
												os.close(p2cwrite)
										if c2pread is not None:
												os.close(c2pread)
										if errread is not None:
												os.close(errread)
										os.close(errpipe_read)

										# When duping fds, if there arises a situation
										# where one of the fds is either 0, 1 or 2, it
										# is possible that it is overwritten (#12607).
										if c2pwrite == 0:
												c2pwrite = os.dup(c2pwrite)
										if errwrite == 0 or errwrite == 1:
												errwrite = os.dup(errwrite)

										# Dup fds for child
										def _dup2(a, b):
												# dup2() removes the CLOEXEC flag but
												# we must do it ourselves if dup2()
												# would be a no-op (issue #10806).
												if a == b:
														self._set_cloexec_flag(a, False)
												elif a is not None:
														os.dup2(a, b)
										_dup2(p2cread, 0)
										_dup2(c2pwrite, 1)
										_dup2(errwrite, 2)

										# Close pipe fds.  Make sure we don't close the
										# same fd more than once, or standard fds.
										closed = set([None])
										for fd in [p2cread, c2pwrite, errwrite]:
												if fd not in closed and fd > 2:
														os.close(fd)
														closed.add(fd)

										if cwd is not None:
												os.chdir(cwd)

										if preexec_fn:
												preexec_fn()

										# Close all other fds, if asked for - after
										# preexec_fn(), which may open FDs.
										if close_fds:
												self._close_fds(but=errpipe_write)

										exitcode = 0
										try:
											executable()
										except SystemExit, ex:
											exitcode = ex.code

										sys.stderr.close()
										sys.stdout.close()
										os._exit(exitcode)

								except:
										exc_type, exc_value, tb = sys.exc_info()
										# Save the traceback and attach it to the exception object
										exc_lines = traceback.format_exception(exc_type,
																													 exc_value,
																													 tb)
										exc_value.child_traceback = ''.join(exc_lines)
										os.write(errpipe_write, pickle.dumps(exc_value))

								os._exit(255)

						# Parent
						if gc_was_enabled:
								gc.enable()
				finally:
						# be sure the FD is closed no matter what
						os.close(errpipe_write)

		finally:
				if p2cread is not None and p2cwrite is not None:
						_close_in_parent(p2cread)
				if c2pwrite is not None and c2pread is not None:
						_close_in_parent(c2pwrite)
				if errwrite is not None and errread is not None:
						_close_in_parent(errwrite)

				# be sure the FD is closed no matter what
				os.close(errpipe_read)


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

	def assertRaisesWithMsg(self, exception, errMsg, callable, args, msg=None,
			**kwargs):
		try:
			callable(*args, **kwargs)
		except exception, ex:
			if errMsg!=str(ex):
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

	def assertEqualToWithin(self, a, b, ratio=1e-7, msg=None):
		"""asserts that abs(a-b/(a+b))<ratio.
		
		If a+b are an underflow, we error out right now.
		"""
		if msg is None:
			msg = "%s != %s to within %s of the sum"%(a, b, ratio)
		denom = abs(a+b)
		self.failUnless(abs(a-b)/denom<ratio, msg)

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
		for name in ["output.stderr", "output.stdout"]:
			try:
				os.unlink(name)
			except os.error:
				pass

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
			with open("output.stdout", "w") as f:
				f.write(out)
			with open("output.stderr", "w") as f:
				f.write(err)
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

	def assertEqualIgnoringAliases(self, result, expectation):
		pat = re.escape(expectation).replace("ASWHATEVER", "AS [a-z]+")+"$"
		if not re.match(pat, result):
			raise AssertionError("%s != %s"%(result, expectation))


_xmlJunkPat = re.compile("|".join([
	'(xmlns(:[a-z0-9]+)?="[^"]*"\s*)',
	'((frame_|coord_system_)?id="[^"]*")',
	'(xsi:schemaLocation="[^"]*"\s*)']))


def cleanXML(aString):
	"""removes IDs and some other detritus from XML literals.

	The result will be invalid XML, and all this assumes the fixed-prefix
	logic of the DC software.

	For new tests, you should just getXMLTree and XPath tests.
	"""
	return re.sub("\s+", " ", _xmlJunkPat.sub('', aString)).strip(
		).replace(" />", "/>").replace(" >", ">")


def _nukeNamespaces(xmlString):
	nsCleaner = re.compile('^(</?)(?:[a-z0-9]+:)')
	return re.sub("(?s)<[^>]*>", 
		lambda mat: nsCleaner.sub(r"\1", mat.group()),
		re.sub('xmlns="[^"]*"', "", xmlString))


def getXMLTree(xmlString, debug=False):
	"""returns an libxml2 etree for xmlString, where, for convenience,
	all namespaces on elements are nuked.

	The libxml2 etree lets you do xpath searching using the xpath method.
	"""
	from lxml import etree as lxtree
	tree = lxtree.fromstring(_nukeNamespaces(xmlString))

	if debug:
		lxtree.dump(tree)
	return tree


def printFormattedXML(xmlString):
	"""pipes xmlString through xmlstarlet fo, pretty-printing it.
	"""
	p = subprocess.Popen("xmlstarlet fo".split(), stdin=subprocess.PIPE)
	p.stdin.write(xmlString)
	p.stdin.close()
	p.wait()


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


class SimpleSampleComparisonTest(VerboseTest):
	"""A base class for tests that simply run a function and compare
	for equality.

	The function to be called is in the functionToRun attribute (wrap
	it in a staticmethod).

	The samples are pairs of (input, output).  Output may be an
	exception (or just the serialised form of the exception).
	"""
	__metaclass__ = SamplesBasedAutoTest

	def _runTest(self, sample):
		val, expected = sample
		try:
			self.assertEqual(self.functionToRun(val),
				expected)
		except AssertionError, ex:
			raise
		except Exception, ex:
			if str(ex)!=str(expected):
				raise


def computeWCSKeys(pos, size, cutCrap=False):
	"""returns a dictionary containing a 2D WCS structure for an image
	centered at pos with angular size.  Both are 2-tuples in degrees.
	"""
	imgPix = (1000., 1000.)
	res = {
		"CRVAL1": pos[0],
		"CRVAL2": pos[1],
		"CRPIX1": imgPix[0]/2.,
		"CRPIX2": imgPix[1]/2.,
		"CUNIT1": "deg",
		"CUNIT2": "deg",
		"CD1_1": size[0]/imgPix[0],
		"CD1_2": 0,
		"CD2_2": size[1]/imgPix[1],
		"CD2_1": 0,
		"NAXIS1": imgPix[0],
		"NAXIS2": imgPix[1],
		"NAXIS": 2,
		"CTYPE1": 'RA---TAN-SIP', 
		"CTYPE2": 'DEC--TAN-SIP',
		"LONPOLE": 180.}
	if not cutCrap:
		res.update({"imageTitle": "test image at %s"%repr(pos),
			"instId": None,
			"dateObs":55300+pos[0], 
			"refFrame": None,
			"wcs_equinox": None,
			"bandpassId": None,
			"bandpassUnit": None,
			"bandpassRefval": None,
			"bandpassLo": pos[0],
			"bandpassHi": pos[0]+size[0],
			"pixflags": None,
			"accref": "image/%s/%s"%(pos, size),
			"accsize": (30+int(pos[0]+pos[1]+size[0]+size[1]))*1024,
			"embargo": None,
			"owner": None,
		})
	return res


class StandIn(object):
	"""A class having the attributes passed as kwargs to the constructor.
	"""
	def __init__(self, **kwargs):
		for key, value in kwargs.items():
			setattr(self, key, value)


def getTestRD(id="test.rd"):
	from gavo import rscdesc  #noflake: import above is conditional
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
		retVal = 2 # in case the callable sys.exits
		try:
			retVal = callable(*args, **kwargs)
		except SystemExit:
			# don't terminate just because someone thinks it's a good idea
			pass
	finally:
		outCont, errCont = sys.stdout.getvalue(), sys.stderr.getvalue()
		sys.stdout, sys.stderr = realOut, realErr
	return retVal, outCont, errCont


class FakeContext(object):
	"""A scaffolding class for testing renderers.

	This will in general not be enough as most actions renderers do will
	require a running reactor, so you need trial.  But sometimes it's
	all synchronous and this will do.
	"""
	def __init__(self, **kwargs):
		self.request = FakeRequest(args=kwargs)
		self.args = kwargs

registerAdapter(lambda ctx: ctx.request, FakeContext, inevow.IRequest)


class CatchallUI(object):
	"""A replacement for base.ui, collecting the messages being sent.

	This is to write tests against producing UI events.  Use it with
	the messageCollector context manager below.
	"""
	def __init__(self):
		self.events = []

	def record(self, evType, args, kwargs):
		self.events.append((evType, args, kwargs))

	def __getattr__(self, attName):
		if attName.startswith("notify"):
			return lambda *args, **kwargs: self.record(attName[6:], args, kwargs)


@contextlib.contextmanager
def messageCollector():
	"""A context manager recording UI events.

	The object returned by the context manager is a CatchallUI; get the
	events accumulated during the run time in its events attribute.
	"""
	tempui = CatchallUI()
	realui = base.ui
	try:
		base.ui = tempui
		yield tempui
	finally:
		base.ui = realui


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


def getServerInThread(data, onlyOnce=False):
	"""runs a server in a thread and returns  thread and base url.

	onlyOnce will configure the server such that it destroys itself
	after having handled one request.  The thread would still need
	to be joined.

	So, better use the DataServer context manager.
	"""
	class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
		def do_GET(self):
			self.wfile.write(data)
		do_POST = do_GET
	
	port = 34000
	httpd = BaseHTTPServer.HTTPServer(('', port), Handler)

	if onlyOnce:
		serve = httpd.handle_request
	else:
		serve = httpd.serve_forever

	t = threading.Thread(target=serve)
	t.setDaemon(True)
	t.start()
	return httpd, t, "http://localhost:%s"%port


@contextlib.contextmanager
def DataServer(data):
	"""a context manager for briefly running a web server returning data.

	This yields the base URL the server is listening on.
	"""
	httpd, t, baseURL = getServerInThread(data)

	yield baseURL

	httpd.shutdown()
	t.join(10)


@contextlib.contextmanager
def userconfigContent(content):
	"""a context manager to temporarily set some content to userconfig.

	This cleans up after itself and clears any userconfig cache before
	it sets to work.

	content are RD elements without the root (resource) tag.
	"""
	userConfigPath = os.path.join(
		base.getConfig("configDir"), "userconfig.rd")
	base.caches.clearForName(userConfigPath[:-3])
	with open(userConfigPath, "w") as f:
		f.write('<resource schema="__system">\n'
			+content
			+'\n</resource>\n')
	try:
		yield
	finally:
		os.unlink(userConfigPath)
	base.caches.clearForName(userConfigPath[:-3])


def main(testClass, methodPrefix=None):
	from gavo import base
	
	if os.environ.get("GAVO_LOG")!="no":
		base.DEBUG = True
		from gavo.user import logui
		logui.LoggingUI(base.ui)
	
	try:
		# two args: first one is class name, locate it in caller's globals
		# and ignore anything before any dot for cut'n'paste convenience
		if len(sys.argv)>2:
			className = sys.argv[-2].split(".")[-1]
			testClass = getattr(sys.modules["__main__"], className)
		
		# one arg: test method prefix on testClass
		if len(sys.argv)>1:
			suite = unittest.makeSuite(testClass, methodPrefix or sys.argv[-1],
				suiteClass=testresources.OptimisingTestSuite)
		else:  # Zero args, emulate unittest.run behaviour
			suite = testresources.TestLoader().loadTestsFromModule(
				sys.modules["__main__"])

		runner = unittest.TextTestRunner(
			verbosity=int(os.environ.get("TEST_VERBOSITY", 1)))
		runner.run(suite)
	except (SystemExit, KeyboardInterrupt):
		raise
	except:
		base.showHints = True
		from gavo.user import errhandle
		traceback.print_exc()
		errhandle.raiseAndCatch(base)
