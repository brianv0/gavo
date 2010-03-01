"""
Code to help TAP.
"""

from __future__ import with_statement

import os
import signal
import subprocess

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
	rd.clearProperty("moribund")



########################## Maintaining TAP job

class TAPActions(uws.UWSActions):
	def __init__(self):
		uws.UWSActions.__init__(self, "TAP", [
			(uws.PENDING, uws.QUEUED, "noOp"),
			(uws.PENDING, uws.EXECUTING, "startJob"),
			(uws.QUEUED, uws.EXECUTING, "startJob"),
			(uws.QUEUED, uws.ABORTED, "noOp"),
			(uws.EXECUTING, uws.COMPLETED, "noOp"),
			(uws.EXECUTING, uws.ABORTED, "killJob"),
			])
	
	def startJob(self, newState, job, ignored):
		"""forks off a new Job.
		"""
		child = subprocess.Popen(["gavo", "tap", job.jobId])
		job.pid = child.pid
		job.phase = uws.EXECUTING

	def killJob(self, newState, job, ignored):
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


uws.registerActions(TAPActions)
