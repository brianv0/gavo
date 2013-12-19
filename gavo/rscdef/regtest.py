"""
A micro-framework for regression tests within RDs.

The basic idea is that there's small pieces of python almost-declaratively
defining tests for a given piece of data.  These things can then be
run while (or rather, after) executing gavo val.
"""

from __future__ import with_statement

import collections
import httplib
import os
import Queue
import random
import re
import sys
import time
import threading
import traceback
import urllib
import urlparse
from cStringIO import StringIO

try:
	from lxml import etree as lxtree
except ImportError:
	# don't fail here, fail when running the test.
	# TODO: add functionality to skip tests with dependencies not satisfied.
	pass

from gavo import base
from gavo import utils
from gavo.base import attrdef
from gavo.imp import argparse
from . import common
from . import procdef

################## Utilities

@utils.memoized
def _loadCreds():
	"""returns a dictionary of auth keys to user/password pairs from
	~/.gavo/test.creds
	"""
	res = {}
	try:
		with open(os.path.join(os.environ["HOME"], ".gavo", "test.creds")) as f:
			for ln in f:
				authKey, user, pw = ln.strip().split()
				res[authKey] = (user, pw)
	except IOError:
		pass
	return res


def getAuthFor(authKey):
	"""returns a header dictionary to authenticate for authKey.

	authKey is a key into ~/.gavo/test.creds.
	"""
	try:
		user, pw = _loadCreds()[authKey]
	except KeyError:
		raise base.NotFoundError(authKey, "Authorization info",
			"~/.gavo/test.creds")
	return {'Authorization': "Basic "+("%s:%s"%(user, pw).encode("base64"))}

################## RD elements

class DynamicOpenVocAttribute(base.AttributeDef):
	"""an attribute that collects arbitrary attributes in a sequence
	of pairs.

	The finished sequence is available as a freeAttrs attribute on the
	embedding instance.  No parsing is done, everything is handled as
	a string.
	"""
	typeDesc_ = "any attribute not otherwise used"

	def __init__(self, name, **kwargs):
		base.AttributeDef.__init__(self, name, **kwargs)

	def feedObject(self, instance, value):
		if not hasattr(instance, "freeAttrs"):
			instance.freeAttrs = []
		instance.freeAttrs.append((self.name_, value))
	
	def feed(self, ctx, instance, value):
		self.feedObject(instance, value)

	def getCopy(self, instance, newParent):
		raise NotImplementedError("This needs some thought")

	def makeUserDoc(self):
		return "(ignore)"

	def iterParentMethods(self):
		def getAttribute(self, name):
			# we need an instance-private attribute dict here:
			if self.managedAttrs is self.__class__.managedAttrs:
				self.managedAttrs = self.managedAttrs.copy()

			try:
				return base.Structure.getAttribute(self, name)
			except base.StructureError: # no "real" attribute, it's a macro def
				self.managedAttrs[name] = DynamicOpenVocAttribute(name)
				# that's a decoy to make Struct.validate see a value for the attribute
				setattr(self, name, None)
				return self.managedAttrs[name]
		yield "getAttribute", getAttribute


class DataURL(base.Structure):
	"""A source document for a regression test.

	These are basically over-complicated specs of URLs.

	The bodies is the path to run the test against.  This is
	interpreted as relative to the RD if there's no leading slash,
	relative to the server if there's a leading slash, and absolute
	if there's a scheme.

	The attributes are translated to parameters, except for a few
	pre-defined names.  If you actually need those as URL parameters,
	should at us and we'll provide some way of escaping these.

	We don't actually parse the URLs coming in here.  GET parameters
	are appended with a & if there's a ? in the existing URL, with a ?
	if not.  Again, shout if this is too dumb for you (but urlparse
	really isn't all that robust either...)
	"""
	name_ = "url"
	
	_base = base.DataContent(description="Base for URL generation; embedded"
		" whitespace will be removed, so you're free to break those whereever"
		" you like.",
		copyable=True)
	
	_httpMethod = base.UnicodeAttribute("httpMethod", 
		description="Request method; usually one of GET or POST",
		default="GET")

	_httpPost = common.ResdirRelativeAttribute("postPayload", 
		default=base.NotGiven,
		description="Path to a file containing material that should go"
		" with a POST request (conflicts with additional parameters).", 
		copyable=True)

	_parset = base.EnumeratedUnicodeAttribute("parSet",
		description="Preselect a default parameter set; form gives what"
			" our framework adds to form queries.", default=base.NotGiven,
		validValues=["form"],
		copyable=True)

	_httpHeaders = base.DictAttribute("httpHeader", 
		description="Additional HTTP headers to pass.",
		copyable=True)

	_httpAuthKey = base.UnicodeAttribute("httpAuthKey",
		description="A key into ~/.gavo.test.creds to find a user/password"
			" pair for this request.",
		default=base.NotGiven,
		copyable=True)

	_rd = common.RDAttribute()

	_open = DynamicOpenVocAttribute("open")

	def getValue(self):
		"""returns a pair of full request URL  and postable payload for this
		test.
		"""
		urlBase = re.sub(r"\s+", "", self.content_)
		if "://" in urlBase:
			# we belive there's a scheme in there
			pass
		elif urlBase.startswith("/"):
			urlBase = base.getConfig("web", "serverurl")+urlBase
		else:
			urlBase = base.getConfig("web", "serverurl"
				)+"/"+self.parent.rd.sourceId+"/"+urlBase

		if self.httpMethod=="POST":
			return urlBase
		else:
			return self._addParams(urlBase, urllib.urlencode(self.getParams()))

	def getParams(self):
		"""returns the URL parameters as a sequence of kw, value pairs.
		"""
		params = getattr(self, "freeAttrs", [])
		if self.parSet=="form":
			params.extend([("__nevow_form__", "genForm"), ("submit", "Go")])
		return params

	def retrieveResource(self):
		"""returns a triple of status, headers, and content for retrieving
		this URL.
		"""
		httpURL, payload = self.getValue(), None
		if self.httpMethod=="POST":
			if self.postPayload:
				with open(self.postPayload) as f:
					payload = f.read()
			else:
				payload = urllib.urlencode(self.getParams)

		scheme, host, path, _, query, _ = urlparse.urlparse(httpURL)
		assert scheme=="http"

		hdrs = {
			"user-agent": "DaCHS regression tester"}
		hdrs.update(self.httpHeader)

		if self.httpAuthKey is not base.NotGiven:
			hdrs.update(getAuthFor(self.httpAuthKey))

		conn = httplib.HTTPConnection(host, timeout=10)
		conn.connect()
		try:
			conn.request(self.httpMethod, path+"?"+query, payload, hdrs)
			resp = conn.getresponse()
			headers = resp.getheaders()
			content = resp.read()
		finally:
			conn.close()
		return resp.status, headers, content

	def _addParams(self, urlBase, params):
		"""a brief hack to add query parameters to GET-style URLs.

		This is a workaround for not trusting urlparse and is fairly easy to
		fool.

		Params must already be fully encoded.
		"""
		if not params:
			return urlBase

		if "?" in urlBase:
			return urlBase+"&"+params
		else:
			return urlBase+"?"+params

	def validate(self):
		if self.postPayload is not base.NotGiven:
			if self.getParams():
				raise base.StructureError("No parameters (or parSets) are"
					" possible with postPayload")
			if self.httpMethod!="POST":
				raise base.StructureError("Only POST is allowed as httpMethod"
					" together with postPayload")
		self._validateNext(DataURL)


class RegTest(procdef.ProcApp):
	"""A regression test.
	"""
	name_ = "regTest"
	requiredType = "regTest"
	formalArgs = "self"

	_title = base.NWUnicodeAttribute("title",
		default=base.Undefined,
		description="A short, human-readable phrase describing what this"
		" test is exercising.")
	
	_url = base.StructAttribute("url",
		childFactory=DataURL,
		default=base.NotGiven,
		description="The source from which to fetch the test data.")

	_rd = common.RDAttribute()

	def retrieveData(self):
		"""returns headers and content when retrieving the resource at url.

		Sets  the headers and data attributes of the test instance.
		"""
		if self.url is base.NotGiven:
			self.status, self.headers, self.data = None, None, None
		else:
			self.status, self.headers, self.data = self.url.retrieveResource()

	def getDataSource(self):
		"""returns a string pointing people to where data came from.
		"""
		if self.url is base.NotGiven:
			return "(Unconditional)"
		else:
			return self.url.getValue()

	def assertHasStrings(self, *strings):
		"""checks that all its arguments are found within content.
		"""
		for phrase in strings:
			assert phrase in self.data, "%s missing"%repr(phrase)

	def assertHTTPStatus(self, expectedStatus):
		assert expectedStatus==self.status, ("Bad status received, %s instead"
			" of %s"%(self.status, expectedStatus))

	def assertValidatesXSD(self):
		"""checks whether the returned data are XSD valid.
		"""
		from gavo.helpers import testtricks
		msgs = testtricks.getXSDErrorsXerces(self.data)
		if msgs:
			raise AssertionError("Response not XSD valid.  Xerces worries"
				" start with\n%s"%(msgs[:160]))


	XPATH_NAMESPACE_MAP = {
		"v2": "http://www.ivoa.net/xml/VOTable/v1.2",
		"v1": "http://www.ivoa.net/xml/VOTable/v1.1",
		"o": "http://www.openarchives.org/OAI/2.0/",
	}

	def assertXpath(self, path, assertions):
		"""checks an xpath assertion.

		path is an xpath (as understood by lxml), with namespace prefixes 
		statically mapped; there's currently v2 (VOTable 1.2), v1 (VOTable 1.1),
		and o (OAI-PMH 2.0).  If you need more prefixes, hack the source
		and feed back your changes (monkeypatching self.XPATH_NAMESPACE_MAP
		is another option).

		path must match exactly one element.

		assertions is a dictionary mapping attribute names to their
		expected value.  Use the key None to check the element content,
		and match for None if you expect an empty element.

		If you need an RE match rather than equality, there's EqualingRE
		in your code's namespace.
		"""
		tree = lxtree.fromstring(self.data)
		res = tree.xpath(path, namespaces=self.XPATH_NAMESPACE_MAP)
		if len(res)==0:
			raise AssertionError("Element not found: %s"%path)
		elif len(res)!=1:
			raise AssertionError("More than one item matched for %s"%path)

		el = res[0]
		for key, val in assertions.iteritems():
			if key is None:
				foundVal = el.text
			else:
				foundVal = el.attrib[key]
			assert val==foundVal, "Trouble with %s: %s (%s, %s)"%(
				key or "content", path, repr(val), repr(foundVal))

	def assertHeader(self, key, value):
		"""checks that header key has value in the response headers.

		keys are compared case-insensitively, values are compared literally.
		"""
		for hKey, hValue in self.headers:
			if hKey.lower()==key.lower():
				if value==hValue:
					break
		else:
			raise AssertionError("Header %s=%s not found in %s"%(
				key, value, self.headers))


class RegTestSuite(base.Structure):
	"""A suite of regression tests.
	"""
	name_ = "regSuite"

	_tests = base.StructListAttribute("tests",
		childFactory=RegTest,
		description="Tests making up this suite",
		copyable=False)
	
	_title = base.NWUnicodeAttribute("title",
		description="A short, human-readable phrase describing what this"
		" suite is about.")

	_sequential = base.BooleanAttribute("sequential",
		description="Set to true if the individual tests need to be run"
			" in sequence.",
		default=False)

	def itertests(self):
		return iter(self.tests)

	def completeElement(self, ctx):
		if self.title is None:
			self.title = "Test suite from %s"%self.parent.sourceId
		self._completeElementNext(base.Structure, ctx)

	def expand(self, *args, **kwargs):
		"""hand macro expansion to the RD.
		"""
		return self.parent.expand(*args, **kwargs)


#################### Running Tests

class TestStatistics(object):
	"""A statistics gatherer/reporter for the regression tests.
	"""
	def __init__(self, verbose=True):
		self.verbose = False
		self.runs = []
		self.oks, self.fails, self.total = 0, 0, 0
		self.globalStart = time.time()
		self.lastTimestamp = time.time()+1
		self.timeSum = 0
	
	def add(self, status, runTime, title, payload, srcRD):
		"""adds a test result to the statistics.

		status is either OK, FAIL, or ERROR, runTime is the time
		spent in running the test, title is the test's title,
		and payload is "something" associated with failures that
		should help diagnosing them.
		"""
		if status=="OK":
			self.oks += 1
		else:
			if self.verbose:
				print ">>>>>>>>", status
			self.fails += 1
		self.total += 1
		self.timeSum += runTime
		self.runs.append((runTime, status, title, str(payload), srcRD))
		self.lastTimestamp = time.time()

	def getReport(self):
		"""returns a string representation of a short report on how the tests
		fared.
		"""
		try:
			return ("%d of %d bad.  avg %.2f, min %.2f, max %.2f. %.1f/s, par %.1f"
				)%(self.fails, self.fails+self.oks, self.timeSum/len(self.runs),
				min(self.runs)[0], max(self.runs)[0], float(self.total)/(
					self.lastTimestamp-self.globalStart),
				self.timeSum/(self.lastTimestamp-self.globalStart))
		except ZeroDivisionError:
			return "No tests run (probably did not find any)."

	def getFailures(self):
		"""returns a string containing some moderately verbose info on the
		failures collected.
		"""
		failures = {}
		for runTime, status, title, payload, srcRD in self.runs:
			if status!="OK":
				failures.setdefault(srcRD, []).append("%s %s"%(status, title))

		return "\n".join("From %s:\n  %s\n\n"%(srcRD, 
				"\n  ".join(badTests))
			for srcRD, badTests in failures.iteritems())

	def save(self, target):
		"""saves the entire test statistics to target.

		This is a pickle of basically what's added with add.  No tools
		for doing something with this are provided so far.
		"""
		with open(target, "w") as f:
			cPickle.dump(self.runs, f)


class TestRunner(object):
	"""A runner for regression tests.

	It is constructed with a sequence of suites (RegTestSuite instances)
	and allows running these in parallel.  It honors the suites' wishes
	as to being executed sequentially.
	"""

# The real trick here are the test suites with state (sequential=True.  For
# those, the individual tests must be serialized, which happens using the magic
# followUp attribute on the tests.

	def __init__(self, suites, verbose=True, dumpNegative=False):
		self.verbose, self.dumpNegative = verbose, dumpNegative
		self.curRunning = {}
		self.threadId = 0
		self._makeTestList(suites)
		self.stats = TestStatistics(verbose=self.verbose)
		self.resultsQueue = Queue.Queue()

	@classmethod
	def fromRD(cls, rd, **kwargs):
		"""constructs a TestRunner for a single ResourceDescriptor.
		"""
		return cls(rd.tests, **kwargs)

	@classmethod
	def fromSuite(cls, suite, **kwargs):
		"""constructs a TestRunner for a RegTestSuite suite
		"""
		return cls([suite], **kwargs)

	@classmethod
	def fromTest(cls, test, **kwargs):
		"""constructs a TestRunner for a single RegTest
		"""
		return cls([base.makeStruct(RegTestSuite, tests=[test],
				parent_=test.parent.parent)], 
			**kwargs)

	def _makeTestList(self, suites):
		"""puts all individual tests from all test suites in a deque.
		"""
		self.testList = collections.deque()
		for suite in suites:
			if suite.sequential:
				self._makeTestsWithState(suite)
			else:
				self.testList.extend(suite.itertests())

	def _makeTestsWithState(self, suite):
		"""helps _makeTestList by putting suite's test in a way that they are
		executed sequentially.
		"""
		# technically, this is done by just entering the suite's "head"
		# and have that pull all the other tests in the suite behind it.
		tests = list(suite.itertests())
		firstTest = tests.pop(0)
		self.testList.append(firstTest)
		for test in tests:
			firstTest.followUp = test
			firstTest = test

	def _spawnThread(self):
		"""starts a new test in a thread of its own.
		"""
		test = self.testList.popleft()
		newThread = threading.Thread(target=self.runOneTest, 
			args=(test, self.threadId))
		newThread.description = test.title
		newThread.setDaemon(True)
		self.curRunning[self.threadId] = newThread
		self.threadId += 1
		newThread.start()

	def runOneTest(self, test, threadId):
		"""runs test and puts the results in the result queue.

		This is usually run in a thread.  However, threadId is only
		used for reporting, so you may run this without threads.

		To support sequential execution, if test has a followUp attribute,
		this followUp is queued after the test has run.
		"""
		startTime = time.time()
		try:
			try:
				curDesc = test.title
				test.retrieveData()
				test.compile()(test)
				self.resultsQueue.put(("OK", test, None, None, time.time()-startTime))

			except KeyboardInterrupt:
				raise

			except AssertionError, ex:
				self.resultsQueue.put(("FAIL", test, ex, None,
					time.time()-startTime))
				# races be damned
				if self.dumpNegative:
					print "Content of failing test:\n%s\n"%test.data

			except Exception, ex:
				f = StringIO()
				traceback.print_exc(file=f)
				self.resultsQueue.put(("ERROR", test, ex, f.getvalue(), 
					time.time()-startTime))

		finally:
			if hasattr(test, "followUp"):
				self.resultsQueue.put(("addTest", test.followUp, None, None, 0))

			if threadId is not None:
				self.resultsQueue.put(("collectThread", threadId, None, None, 0))

	def _printStat(self, state, test, payload, traceback):
		"""gives feedback to the user about the result of a test.
		"""
		if not self.verbose:
			return
		if state=="FAIL":
			print "**** Test failed: %s -- %s\n"%(
				test.title, test.getDataSource())
			print ">>>>", payload
		elif state=="ERROR":
			print "**** Internal Failure: %s -- %s\n"%(test.title, 
				test.url.getValue()[0])
			print traceback

	def _runTestsReal(self, nThreads=8, showDots=False):
		"""executes the tests, taking tests off the queue and spawning
		threads until the queue is empty.

		nThreads gives the number of maximum number threads that run the
		tests at one time.

		showDots, if True, instructs the runner to push one dot to stderr
		per test spawned.
		"""
		while self.testList or self.curRunning:
			while len(self.curRunning)<nThreads and self.testList:
				self._spawnThread()
				if showDots:
					sys.stderr.write(".")
					sys.stderr.flush()

			evType, test, payload, traceback, dt = self.resultsQueue.get(timeout=60)
			if evType=="addTest":
				self.testList.appendleft(test)
			elif evType=="collectThread":
				deadThread = self.curRunning.pop(test)
				deadThread.join()
			else:
				self.stats.add(evType, dt, test.title, "", test.rd.sourceId)
				self._printStat(evType, test, payload, traceback)

		if showDots:
			sys.stderr.write("\n")

	def runTests(self, showDots=False):
		"""executes the tests in a random order and in parallel.
		"""
		random.shuffle(self.testList)
		try:
			self._runTestsReal(showDots=showDots)
		except Queue.Empty:
			sys.stderr.write("******** Hung jobs\nCurrently executing:\n")
			for thread in self.curRunning.values():
				sys.stderr.write("%s\n"%thread.description)

	def runTestsInOrder(self):
		"""runs all tests sequentially and in the order they were added.
		"""
		for test in self.testList:
			self.runOneTest(test, None)
			try:
				while True:
					evType, test, payload, traceback, dt = self.resultsQueue.get(False)
					if evType=="addTest":
						self.testList.appendleft(test)
					else:
						self.stats.add(evType, dt, test.title, "", test.rd.sourceId)
						self._printStat(evType, test, payload, traceback)
			except Queue.Empty:
				pass


################### command line interface


def urlToURL():
	"""converts HTTP (GET) URLs to URL elements.
	"""
#	This is what's invoked by the makeTestURLs command.
	while True:
		parts = urlparse.urlparse(raw_input())
		print "<url %s>%s</url>"%(
			" ".join('%s="%s"'%(k,v[0]) 
				for k,v in urlparse.parse_qs(parts.query).iteritems()),
			parts.path)

def parseCommandLine(args=None):
	"""parses the command line for main()
	"""
	parser = argparse.ArgumentParser(description="Run tests embedded in RDs")
	parser.add_argument("id", type=str,
		help="RD id or cross-RD identifier for a testable thing.")
	parser.add_argument("-v", "--verbose", help="Talk while working",
		action="store_true", dest="verbose")
	parser.add_argument("-d", "--dumpNegative", help="Dump the content of"
		" failing tests to stdout",
		action="store_true", dest="dumpNegative")

	return parser.parse_args(args)


def main(args=None):
	"""user interaction for gavo test.
	"""
	from gavo import api

	args = parseCommandLine(args)
	if '#' in args.id:
		testElement = base.resolveId(None, args.id)
	else:
		testElement = base.caches.getRD(args.id)
	
	runnerArgs = {
		"verbose": args.verbose,
		"dumpNegative": args.dumpNegative,
	}

	if isinstance(testElement, api.RD):
		runner = TestRunner.fromRD(testElement, **runnerArgs)
	elif isinstance(testElement, RegTestSuite):
		runner = TestRunner.fromSuite(testElement, **runnerArgs)
	elif isinstance(testElement, RegTest):
		runner = TestRunner.fromTest(testElement, **runnerArgs)
	else:
		raise base.ReportableError("%s is not a testable element.",
			hint="Only RDs, regSuites, or regTests are eligible for testing.")
	
	runner.runTests(showDots=True)
	print runner.stats.getReport()
	if runner.stats.fails:
		sys.exit(1)
