"""
A UWS-based interface to datalink.

TODO: There's quite a bit of parallel between this and useruws.  This
should probably be reformulated along the lines of useruws.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import cPickle as pickle
import datetime

from gavo import base
from gavo import utils
from gavo import rscdesc #noflake: cache registration
from gavo.protocols import products
from gavo.protocols import uws
from gavo.protocols import uwsactions


class DLTransitions(uws.ProcessBasedUWSTransitions):
	"""The transition function for datalink jobs.
	"""
	def __init__(self):
		uws.ProcessBasedUWSTransitions.__init__(self, "DL")

	def queueJob(self, newState, wjob, ignored):
		uws.ProcessBasedUWSTransitions.queueJob(self, newState, wjob, ignored)
		return self.startJob(uws.EXECUTING, wjob, ignored)

	def getCommandLine(self, wjob):
		return "gavo", ["gavo", "dlrun", "--", str(wjob.jobId)]


class ServiceIdParameter(uws.JobParameter):
	"""A fully qualified id of the DaCHS service to execute the datalink
	request.
	"""


class ArgsParameter(uws.JobParameter):
	"""all parameters passed to the datalink job as a request.args dict.

	The serialised representation is the pickled dict.  Pickle is ok as
	the string never leaves our control (the network serialisation is
	whatever comes in via the POST).
	"""
	@staticmethod
	def _deserialize(pickled):
		return pickle.loads(pickled)
	
	@staticmethod
	def _serialize(args):
		return pickle.dumps(args)


class DLJob(uws.UWSJobWithWD):
	"""a UWS job performing some datalink data preparation.

	In addition to UWS parameters, it has

	* serviceid -- the fully qualified id of the service that will process
	  the request
	* datalinkargs -- the parameters (in request.args form) of the
	  datalink request.
	"""
	_jobsTDId = "//datalink#datalinkjobs"
	_transitions = DLTransitions()

	_parameter_serviceid = ServiceIdParameter
	_parameter_datalinkargs = ArgsParameter

	def _setParamsFromDict(self, args):
		"""stores datalinkargs from args.

		As there's only one common UWS for all dlasync services, we have
		to steal the service object from upstack at the moment.  Let's see
		if there's a way around that later.
		"""
		self.setPar("datalinkargs", args)
		self.setPar("serviceid", utils.stealVar("service").getFullId())


class DLUWS(uws.UWS):
	"""the worker system for datalink jobs.
	"""
	joblistPreamble = ("<?xml-stylesheet href='/static"
		"/xsl/dlasync-joblist-to-html.xsl' type='text/xsl'?>")
	jobdocPreamble = ("<?xml-stylesheet href='/static/xsl/"
		"dlasync-job-to-html.xsl' type='text/xsl'?>")

	_baseURLCache = None

	def __init__(self):
		uws.UWS.__init__(self, DLJob, uwsactions.JobActions())

	@property
	def baseURL(self):
		return base.makeAbsoluteURL("datalinkuws")

	def getURLForId(self, jobId):
		"""returns a fully qualified URL for the job with jobId.
		"""
		return "%s/%s"%(self.baseURL, jobId)



DL_WORKER = DLUWS()

####################### nevow simulation
# This is so we can handle nevow resources coming back from datalink.
# Factor this out?  This is essentially stolen from trialhelpers,
# and we might just put that somewhere where it's useful.

import warnings
from nevow import inevow
from nevow import context
from nevow import testutil
from twisted.internet import defer
from twisted.internet import reactor


def _requestDone(result, request, ctx):
	"""essentially calls renderHTTP on result and stops the reactor.

	This is a helper for our nevow simulation.
	"""
	if isinstance(result, basestring):
		if result:
			request.write(result)
	elif hasattr(result, "renderHTTP"):
		return _doRender(result, ctx)
	else:
		warnings.warn("Unsupported async datalink render result: %s"%repr(result))
	request.d.callback(request.accumulator)
	reactor.stop()
	return request.accumulator, request


def _renderCrashAndBurn(failure, ctx):
	"""stops the reactor and returns a failure.

	This is a helper for our nevow simulation.
	"""
	reactor.stop()
	return failure


def _doRender(page, ctx):
	"""returns a deferred firing the result of page.renderHTTP(ctx).

	This is a helper for our nevow simulation.
	"""
	request = inevow.IRequest(ctx)
	if not hasattr(page, "renderHTTP"):
		return _requestDone(page, request, ctx)
		
	d = defer.maybeDeferred(page.renderHTTP,
		context.PageContext(
			tag=page, parent=context.RequestContext(tag=request)))

	d.addCallback(_requestDone, request, ctx)
	d.addErrback(_renderCrashAndBurn, ctx)
	return d


class FakeRequest(testutil.AccumulatingFakeRequest):
	"""A nevow Request for local data accumulation.

	We have a version of our own for this since nevow's has a 
	registerProducer that produces an endless loop with push
	producers (which is what we have).
	"""
	def __init__(self, destFile, *args, **kwargs):
		self.finishDeferred = defer.Deferred()
		testutil.AccumulatingFakeRequest.__init__(self, *args, **kwargs)
		self.destFile = destFile
	
	def write(self, stuff):
		self.destFile.write(stuff)

	def registerProducer(self, producer, isPush):
		self.producer = producer
		if not isPush:
			testutil.AccumulatingFakeRequest.registerProducer(
				self, producer, isPush)

	def unregisterProducer(self):
		del self.producer

	def notifyFinish(self):
		return self.finishDeferred


def _getRequestContext(destFile):
	"""returns a very simple nevow context writing to destFile.
	"""
	req = FakeRequest(destFile)
	ctx = context.WovenContext()
	ctx.remember(req)
	return ctx


def writeResultTo(page, destFile):
	"""arranges for the result of rendering the nevow resource page 
	to be written to destFile.

	This uses a very simple simulation of nevow rendering, so a few
	tricks are possible.  Also, it actually runs a reactor to do its magic.
	"""
	ctx = _getRequestContext(destFile)

	def _(func, ctx):
		return defer.maybeDeferred(func, ctx
			).addCallback(_doRender, ctx)

	reactor.callWhenRunning(_, page.renderHTTP, ctx)
	reactor.run()
	return inevow.IRequest(ctx)



####################### CLI

def parseCommandLine():
	from gavo.imp import argparse
	parser = argparse.ArgumentParser(description="Run an asynchronous datalink"
		" job (used internally)")
	parser.add_argument("jobId", type=str, help="UWS id of the job to run")
	return parser.parse_args()


def main():
	args = parseCommandLine()
	jobId = args.jobId
	try:
		job = DL_WORKER.getJob(jobId)
		with job.getWritable() as wjob:
			wjob.change(phase=uws.EXECUTING, startTime=datetime.datetime.utcnow())

		service = base.resolveCrossId(job.parameters["serviceid"])
		args = job.parameters["datalinkargs"]
		data = service.run("dlget", args).original

		# Unfortunately, datalink cores can in principle return all kinds
		# of messy things that may not even be representable in plain files
		# (e.g., nevow resources returning redirects).  We hence only
		# handle (mime, payload) and (certain) Product instances here
		# and error out otherwise.
		if isinstance(data, tuple):
			mime, payload = data
			with job.openResult(mime, "result") as destF:
				destF.write(payload)

		elif isinstance(data, products.ProductBase):
			# We could run renderHTTP and grab the content-type from there
			# (which probably would be better all around).  For now, don't
			# care:
			with job.openResult("application/octet-stream", "result") as destF:
				for chunk in data.iterData():
					destF.write(chunk)

		elif hasattr(data, "renderHTTP"):
			# these are nevow resources.  Let's run a reactor so these properly
			# work.
			with job.openResult(type, "result") as destF:
				req = writeResultTo(data, destF)
			job.fixTypeForResultName("result", req.headers["content-type"])

		else:
			raise NotImplementedError("Cannot handle a service %s result yet."%
				repr(data))
		
		with job.getWritable() as wjob:
			wjob.change(phase=uws.COMPLETED)

	except SystemExit:
		pass
	except uws.JobNotFound:
		base.ui.notifyInfo("Giving up non-existing datalink job %s."%jobId)
	except Exception, ex:
		base.ui.notifyError("Datalink runner %s major failure"%jobId)
		# try to push job into the error state -- this may well fail given
		# that we're quite hosed, but it's worth the try
		DL_WORKER.changeToPhase(jobId, uws.ERROR, ex)
		raise


if __name__=="__main__":
	# silly test code, not normally reached
	from nevow import rend
	import os
	class _Foo(rend.Page):
		def __init__(self, stuff):
			self.stuff = stuff

		def renderHTTP(self, ctx):
			if self.stuff=="booga":
				return "abc"
			else:
				return defer.maybeDeferred(_Foo, "booga").addBoth(self.cleanup)

		def cleanup(self, res):
			print "cleaning up"
			return res

	with open("bla", "w") as f:
		writeResultTo(_Foo("ork"), f)
	with open("bla") as f:
		print f.read()
	os.unlink("bla")

