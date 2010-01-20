"""
Code to help TAP.
"""

from __future__ import with_statement

import os
import signal

from gavo import base
from gavo import rsc
from gavo.protocols import uws


RD_ID = "__system__/tap"


class TAPError(base.Error):
	"""TAP-related errors, mainly to communicate with web renderers.

	TAPErrors are constructed with a displayable message (may be None to
	autogenerate one) and optionally a source exception and a hint.
	"""
	def __init__(self, msg, sourceEx=None, hint=None):
		gavo.Error.__init__(self, msg, hint=hint)
		self.sourceEx = sourceEx
	
	def __str__(self):
		if self.message:
			return self.message
		elif self.sourceEx:
			return "TAP operation failed (%s, %s)"%(
				self.sourceEx.__class__.__name__,
				str(self.sourceEx))
		else:
			return "Unspecified TAP related error"


######################## maintaining TAP schema

def publishToTAP(rd, connection):
	"""publishes info for all ADQL-enabled tables of rd to the TAP_SCHEMA.
	"""
	# first check if we have any adql tables at all, and don't attempt
	# anything if we don't (this is cheap optimizing and keeps TAP_SCHEMA
	# from being created on systems that don't do ADQL.
	for table in rd.tables:
		if table.adql:
			break
	else:
		return
	tapRD = base.caches.getRD(RD_ID)
	for ddId in ["importTablesFromRD", "importColumnsFromRD", 
			"importFkeysFromRD"]:
		dd = tapRD.getById(ddId)
		rsc.makeData(dd, forceSource=rd, parseOptions=rsc.parseValidating,
			connection=connection)


def unpublishFromTAP(rd, connection):
	"""removes all information originating from rd from TAP_SCHEMA.
	"""
	rd.setProperty("moribund", "True") # the embedded grammars take this
	                                   # to mean "kill this"
	publishToTAP(rd, connection)


######################## running TAP jobs

def _runTAP(jobId):
	"""sets up an execution environment for a TAP processor and starts the job.
	"""
# set signal handler
# build data for core
# fix job's pid to the pid of the worker process
# start ADQL job
# write VOTable to job.wd
# transition to completed

def _forkTAPJob(job):
	jobId = job.jobId
	# Close the job before forking to avoid inheriting it
	job.close()
	pid = os.fork()
	if pid==0:
		# child
		_runTAP(jobId)
		os._exit(0)
	else:
		# parent
		with uws.makeFromId(jobId) as job:
			job.pid = pid


########################## Maintaining TAP job

class TAPActions(uws.UWSActions):
	def __init__(self):
		uws.UWSActions.__init__(self, "TAP", [
			(uws.QUEUED, uws.EXECUTING, "startJob"),
			(uws.QUEUED, uws.ABORTED, "markNewState"),
			(uws.EXECUTING, uws.COMPLETED, "markNewState"),
			(uws.EXECUTING, uws.ABORTED, "killJob"),
			])
	
	def startJob(self, newState, job):
		"""forks off a new Job.
		"""
		try:
			_forkTAPJob(job)
		except Exception, ex:
			job.addError(ex)

	def killJob(self, newState, job):
		"""tries to kill -TERM the pid the job has registred.

		This will raise a TAPError with some description if that's not possible
		for some reason.

		This does not actually change the job's state.  That's the job of
		the child taprunner.
		"""
		try:
			pid = job.pid
			if pid is None:
				raise TAPError("Job is not running")
			os.kill(pid, signal.SIGTERM)
		except TAPError:
			raise
		except Exception, ex:
			raise TAPError(None, ex)


	def markNewState(self, newState, job):
		"""just notes that job is now in newState.
		"""
		job.phase = newState
