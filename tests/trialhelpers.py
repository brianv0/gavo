"""
Helpers for trial-based tests, in particular retrieving pages.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import os
import urlparse
import warnings
from cStringIO import StringIO

from nevow import context
from nevow import inevow
from nevow import util
from nevow import testutil
from nevow import url
from twisted.trial.unittest import TestCase as TrialTest
from twisted.python import failure  #noflake: exported name
from twisted.internet import defer

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc

base.setConfig("web", "enabletests", "True")
from gavo.web import weberrors
from gavo.web import root


def _requestDone(result, request, ctx):
	if isinstance(result, basestring):
		if result:
			request.write(result)
	elif isinstance(result, url.URL):
		request.code = 303
		request.headers["location"] = str(result)
	elif hasattr(result, "renderHTTP"):
		return _deferredRender((result, ()), ctx)
	else:
		warnings.warn("Unsupported render result: %s"%repr(result))
	request.d.callback(request.accumulator)
	return request.accumulator, request


def _renderCrashAndBurn(failure, ctx):
	return _renderException(failure, ctx)


def _renderException(failure, ctx):
	return _doRender(
		weberrors.getDCErrorPage(failure), ctx, formatExcs=False)


def _doRender(page, ctx, formatExcs=True):
	request = inevow.IRequest(ctx)
	if not hasattr(page, "renderHTTP"):
		return _requestDone(page, request, ctx)
		
	d = util.maybeDeferred(page.renderHTTP,
		context.PageContext(
			tag=page, parent=context.RequestContext(tag=request)))

	d.addCallback(_requestDone, request, ctx)
	if formatExcs:
		d.addErrback(_renderCrashAndBurn, ctx)
	return d


def _deferredRender(res, ctx):
	page, segments = res
	if segments:
		return util.maybeDeferred(page.locateChild,
			ctx, segments
			).addCallback(_deferredRender, ctx
			).addErrback(_renderException, ctx)

	else:
		try:
			return _doRender(page, ctx)
		except:
			assert False, "Exceptions should not escape from _doRender"


class FakeFieldStorage(object):
	filename = None
	def __init__(self, args):
		self.args = args

	def __iter__(self):
		return iter(self.args)
	
	def getfirst(self, key):
		return self.args[key][0]
	
	def __getitem__(self, key):
		return self.args[key][0]

	def keys(self):
		return self.args.keys()

	@property
	def file(self):
		return StringIO(self.args[0])


class FakeRequest(testutil.AccumulatingFakeRequest):
	"""A Request for testing purpuses.

	We have a version of our own for this since nevow's has a 
	registerProducer that produces an endless loop with push
	producers (which is what we have).
	"""
	def __init__(self, *args, **kwargs):
		self.finishDeferred = defer.Deferred()
		testutil.AccumulatingFakeRequest.__init__(self, *args, **kwargs)

	def registerProducer(self, producer, isPush):
		self.producer = producer
		if not isPush:
			testutil.AccumulatingFakeRequest.registerProducer(
				self, producer, isPush)

	def unregisterProducer(self):
		del self.producer

	def notifyFinish(self):
		return self.finishDeferred


def _buildRequest(method, path, rawArgs, requestClass=FakeRequest):
	args = {}
	for k, v in rawArgs.iteritems():
		if isinstance(v, list):
			args[k] = v
		else:
			args[k] = [v]
	if path.startswith("http://"):
		path = urlparse.urlparse(path).path
	req = requestClass(uri="/"+path, args=args)
	# Service for my TAPRequest hack (see web.taprender).
	req.fields = FakeFieldStorage(args)
	req.headers = {}
	req.method = method
	return req


def getRequestContext(path, method="GET", args=None, 
		requestMogrifier=None, requestClass=FakeRequest):
	if args is None:
		args = {}
	req = _buildRequest(method, "http://localhost"+path, args, 
		requestClass=requestClass)
	if requestMogrifier is not None:
		requestMogrifier(req)
	ctx = context.WovenContext()
	ctx.remember(req)
	return ctx


def runQuery(page, method, path, args, requestMogrifier=None,
		requestClass=FakeRequest):
	"""runs a query on a page.

	The query should look like it's coming from localhost.

	The thing returns a deferred firing a pair of the result (a string)
	and the request (from which you can glean headers and such).
	"""
	ctx = getRequestContext(path, method, args, requestMogrifier,
		requestClass=requestClass)
	segments = tuple(path.split("/"))[1:]
	return util.maybeDeferred(
			page.locateChild, ctx, segments
		).addCallback(_deferredRender, ctx)


class RenderTest(TrialTest):
	"""a base class for tests of twisted web resources.
	"""
	renderer = None # Override with the resource to be tested.

	def assertStringsIn(self, result, strings, inverse=False, 
			customTest=None):
		content = result[0]
		try:
			for s in strings:
				if inverse:
					self.failIf(s in content, "'%s' in remote.data"%s)
				else:
					self.failIf(s not in content, "'%s' not in remote.data"%s)

			if customTest is not None:
				customTest(content)
		except AssertionError:
			with open("remote.data", "w") as f:
				f.write(content)
			raise
		return result
	
	def assertResultHasStrings(self, method, path, args, strings, 
			rm=None, inverse=False, customTest=None):
		return runQuery(self.renderer, method, path, args, rm,
			).addCallback(self.assertStringsIn, strings, inverse=inverse,
			customTest=customTest)

	def assertGETHasStrings(self, path, args, strings, rm=None,
			customTest=None):
		return self.assertResultHasStrings("GET", 
			path, args, strings, rm, customTest=customTest)

	def assertGETLacksStrings(self, path, args, strings, rm=None):
		return self.assertResultHasStrings("GET", 
			path, args, strings, rm, inverse=True)

	def assertPOSTHasStrings(self, path, args, strings, rm=None):
		return self.assertResultHasStrings("POST", path, args, strings,
			rm)

	def assertStatus(self, path, status, args={}, rm=None):
		return runQuery(self.renderer, "GET", path, args).addCallback(
			lambda res: self.assertEqual(res[1].code, status))

	def assertGETRaises(self, path, args, exc, alsoCheck=None):
		def cb(res):
			raise AssertionError("%s not raised (returned %s instead)"%(
				exc, res))
		def eb(failure):
			failure.trap(exc)
			if alsoCheck is not None:
				alsoCheck(failure)

		return runQuery(self.renderer, "GET", path, args
			).addCallback(cb
			).addErrback(eb)


class ArchiveTest(RenderTest):
	renderer = root.ArchiveService()


def provideRDData(rdName, ddId, _imported=set()):
	"""makes ddId from rdName and returns a cleanup function.

	This is for creating temporary data for tests; it's supposed to be used
	as in::

		atexit.register(provideRDData("test", "import_fitsprod"))
	
	This keeps track of (rdName, ddId) pairs it's already loaded and
	doesn't import them again.
	"""
	if (rdName, ddId) in _imported:
		return lambda: None

	dd = testhelpers.getTestRD(rdName).getById(ddId)
	dataCreated = rsc.makeData(dd)
	_imported.add((rdName, ddId))

	# may be gone in atexit
	nvArg = rsc.parseNonValidating

	def cleanup():
		dataCreated.dropTables(nvArg)
	
	return cleanup


if os.environ.get("GAVO_LOG")!="no":
	from gavo.user import logui
	logui.LoggingUI(base.ui)
