"""
A UWS-based interface to datalink
"""

from __future__ import with_statement

from .. import base
from .. import rscdesc #noflake: cache registration
from . import uws
from . import uwsactions


RENDERER_NAME = "dlasync"


class DLTransitions(uws.ProcessBasedUWSTransitions):
	"""The transition function for datalink jobs.
	"""
	def __init__(self):
		uws.ProcessBasedUWSTransitions.__init__(self, "DL")
	
	def getCommandLine(self, wjob):
		return "gavo", ["gavo", "dlrun", "--", str(wjob.jobId)]


class DLJob(uws.UWSJobWithWD):
	"""a UWS job performing some datalink data preparation.
	"""
	_jobsTDId = "//datalink#datalinkjobs"
	_transitions = DLTransitions()


class DLUWS(uws.UWS):
	"""the worker system for datalink jobs.
	"""
	def __init__(self):
		uws.UWS.__init__(self, DLJob, uwsactions.JobActions())

	@property
	def baseURL(self):
		if self._baseURLCache is None:
			self._baseURLCache = "UNDEFINED YET; TODO"
		return self._baseURLCache

	def getURLForId(self, jobId):
		"""returns a fully qualified URL for the job with jobId.
		"""
		return "%s/%s"%(self.baseURL, jobId)


DL_WORKER = DLUWS()


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
		with DL_WORKER.getJob(jobId) as job:
			print job
	except SystemExit:
		pass
	except uws.JobNotFound:
		base.ui.notifyInfo("giving up non-existing TAP job %s."%jobId)
	except Exception, ex:
		base.ui.notifyError("datalink runner %s major failure"%jobId)
		# try to push job into the error state -- this may well fail given
		# that we're quite hosed, but it's worth the try
		with DL_WORKER.changeableJob(jobId) as wjob:
			wjob.changeToPhase(uws.ERROR, ex)
		raise

