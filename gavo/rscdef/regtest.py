"""
A micro-framework for regression tests within RDs.

The basic idea is that there's small pieces of python almost-declaratively
defining tests for a given piece of data.  These things can then be
run while (or rather, after) executing gavo val.
"""

from __future__ import with_statement

import collections
import Queue
import random
import time
import threading
import traceback
from cStringIO import StringIO

from gavo import base
from . import procdef


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
	
	_base = base.DataContent(description="Base for URL generation",
		copyable=True)

	def __init__(self, *args, **kwargs):
		base.Structure.__init__(self, *args, **kwargs)
		# capture extra parameters for URL use
		self.managedAttrs = self.managedAttrs.copy()
		self.extraAttrs = []

	def getAttribute(self, name):
		# this is a helper to let DataURL accept arbitrary parameters.
		try:
			return base.Structure.getAttribute(self, name)
		except base.StructureError: # no "real" attribute, it's a macro def
			self.extraAttrs.append(name)
			self.managedAttrs[name] = attrdef.UnicodeAttribute(name)
			return self.managedAttrs[name]

	def getValue(self):
		"""returns a pair of full request URL  and postable payload for this
		test.
		"""
		urlBase = self.content_
		if "://" in urlBase:
			# we belive it's a scheme
			pass
		elif urlBase.startswith("/"):
			urlBase = base.getConfig("web", "serverurl")+urlBase
		else:
			urlBase = base.getConfig("web", "serverurl"
				)+"/"+self.parent.parent.parent.sourceId+"/"+urlBase

		return urlBase


class RegTest(procdef.ProcApp):
	"""A regression test.
	"""
	name_ = "regTest"
	requiredType = "regTest"
	formalArgs = "self"

	_title = base.UnicodeAttribute("title",
		default=base.Undefined,
		description="A short, human-readable phrase describing what this"
		" test is exercising.")
	
	_url = base.StructAttribute("url",
		childFactory=DataURL,
		default=base.NotGiven,
		description="The source from which to fetch the test data.")
	

class RegTestSuite(base.Structure):
	"""A suite of regression tests.
	"""
	name_ = "regSuite"

	_tests = base.StructListAttribute("tests",
		childFactory=RegTest,
		description="Tests making up this suite",
		copyable=False)
	
	_description = base.UnicodeAttribute("description",
		description="A short, human-readable phrase describing what this"
		" suite is about.")

	_sequential = base.BooleanAttribute("sequential",
		description="Set to true if the individual tests need to be run"
			" in sequence.",
		default=False)

	def itertests(self):
		return iter(self.tests)


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
	
	def add(self, status, runTime, title, payload):
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
		self.runs.append((runTime, status, title, str(payload)))
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
			return "No report yet"

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

	def __init__(self, suites, verbose=True):
		self.verbose = verbose
		self.curRunning = {}
		self.threadId = 0
		self._makeTestList(suites)
		self.stats = TestStatistics(verbose=self.verbose)
		self.resultsQueue = Queue.Queue()

	@classmethod
	def fromRD(cls, rd, verbose=False):
		"""constructs a TestRunner for a single ResourceDescriptor.
		"""
		return cls(rd.tests, verbose=verbose)

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
				test.compile(test)(test)
				self.resultsQueue.put(("OK", test, None, None, time.time()-startTime))

			except KeyboardInterrupt:
				raise

			except AssertionError, ex:
				self.resultsQueue.put(("FAIL", test, ex, None,
					time.time()-startTime))
				# races be damned
				if hasattr(test, "lastResult"):
					with open("lastResult", "w") as f:
						f.write(test.lastResult)

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
			print "**** Test failed: %s -- %s\n"%(test.title, test.url)
			print ">>>>", payload
		elif state=="ERROR":
			print "**** Internal Failure: %s -- %s\n"%(test.title, test.url)
			print traceback

	def _runTestsReal(self, nThreads=8):
		"""executes the tests, taking tests off the queue and spawning
		threads until the queue is empty.

		nThreads gives the number of maximum number threads that run the
		tests at one time.
		"""
		while self.testList or self.curRunning:
			while len(self.curRunning)<nThreads and self.testList:
				self._spawnThread()
			evType, test, payload, traceback, dt = self.resultsQueue.get(timeout=60)
			if evType=="addTest":
				self.testList.appendleft(test)
			elif evType=="collectThread":
				deadThread = self.curRunning.pop(test)
				deadThread.join()
			else:
				self.stats.add(evType, dt, test.title, "")
				self._printStat(evType, test, payload, traceback)

	def runTests(self):
		"""executes the tests in a random order and in parallel.
		"""
		random.shuffle(self.testList)
		try:
			self._runTestsReal()
		except Queue.Empty:
			print "******** Hung jobs"
			print "Currently executing:"
			for thread in self.curRunning.values():
				print thread.description

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
						self.stats.add(evType, dt, test.title, "")
						self._printStat(evType, test, payload, traceback)
			except Queue.Empty:
				pass


