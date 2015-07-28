"""
Support for UWSes defined in user RDs.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

import datetime

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdesc #noflake: for registration
from gavo import utils
from gavo.protocols import uws
from gavo.protocols import uwsactions


class UserUWSTransitions(uws.ProcessBasedUWSTransitions):
	"""The transition function for user-defined UWSes.
	"""
	def __init__(self):
		uws.ProcessBasedUWSTransitions.__init__(self, "User")

	def queueJob(self, newState, wjob, ignored):
		"""puts a job on the queue.
		"""
		uws.ProcessBasedUWSTransitions.queueJob(self, newState, wjob, ignored)
		wjob.uws.scheduleProcessQueueCheck()

	def getCommandLine(self, wjob):
		args = ["gavo", "uwsrun", "--", str(wjob.jobId)]
		if base.DEBUG:
			args[1:1] = ["--debug", "--traceback"]
		return "gavo", args


class UserUWSJobType(uws.UWSJobType):
	"""A metaclass for the base of UserUWSJobs.

	We need this as UserUWSJobBase's constructor has to return
	specialised classes depending on the service.  Now, we could
	have used a factory function, but I wanted to keep the class
	attributes.

	Worse, the UWS doesn't really know the originating service either.
	So, we're resorting to criminality (stealVar): If it's possible
	that a user UWS job is created, somewhere in the stack there
	needs to be a local variable called __uws_originating_service
	with the id of the service.
	"""
	userUWSJobClasses = {}

	def __call__(self, properties, workerSystem, writable):
		if properties["jobClass"] is None:
			jobClass = utils.stealVar("_uws_originating_service")
			properties["jobClass"] = jobClass
		else:
			jobClass = properties["jobClass"]

		if jobClass not in self.userUWSJobClasses:
			self.userUWSJobClasses[jobClass] = makeUserUWSJobClass(jobClass)
		return self.userUWSJobClasses[jobClass](
			properties, workerSystem, writable)


class UserUWSJobBase(uws.UWSJobWithWD):
	"""A UWS job performing a job specified by a core.

	This only has the rudimentary basic parameters for UWS jobs.
	UserUWS creates extra classes by service from this.
	"""
	__metaclass__ = UserUWSJobType

	_jobsTDId = "//uws#userjobs"
	_transitions = UserUWSTransitions()


def makeUWSJobParameterFor(inputKey):
	"""returns a uws.JobParameter instance for inputKey.
	"""
	class SomeParameter(uws.JobParameter):
		name = inputKey.name
		_deserialize = inputKey._parse
		_serialize = inputKey._unparse
	return SomeParameter


def makeUserUWSJobClass(svcId):
	"""returns a class object for representing UWS jobs processing requests
	for the service at svcId.
	"""
	svc = base.resolveCrossId(svcId)
	
	class UserUWSJob(uws.UWSJobWithWD):
		_transitions = UserUWSJobBase._transitions

	for key in svc.getInputKeysFor("uws.xml"):
		setattr(UserUWSJob, "_parameter_"+key.name,
			makeUWSJobParameterFor(key))
	
	return UserUWSJob


class UserUWS(uws.UWSWithQueueing):
	"""A UWS for "user jobs", i.e., generic things an a core.

	These dynamically create job classes based on the processing core's
	parameters.  To make this happen, we'll need to override some of the
	common UWS functions.
	"""
	jobClass = UserUWSJobBase

	def getURLForId(self, jobId):
		return base.resolveCrossId(self.getJob(jobId).jobClass).getURL(
			"uws.xml")+"/"+jobId

	def getParamsFromRequest(self, wjob, request, service):
		for key, value in request.args.iteritems():
			wjob.setSerializedPar(key, " ".join(value))

USER_WORKER = UserUWS(UserUWSJobBase, uwsactions.JobActions())


####################### CLI

def parseCommandLine():
	from gavo.imp import argparse
	parser = argparse.ArgumentParser(description="Run an asynchronous"
		" generic job (used internally)")
	parser.add_argument("jobId", type=str, help="UWS id of the job to run")
	return parser.parse_args()


def main():
	args = parseCommandLine()
	jobId = args.jobId
	try:
		job = USER_WORKER.getJob(jobId)
		with job.getWritable() as wjob:
			wjob.change(phase=uws.EXECUTING, startTime=datetime.datetime.utcnow())

		service = base.resolveCrossId(job.jobClass)
		inputTable = rsc.TableForDef(service.core.inputTable)

		for parName, value in job.parameters.iteritems():
			inputTable.setParam(parName, value)

		data = service._runWithInputTable(
			service.core, inputTable, None).original

		# Our cores either return a table, a pair of mime and data,
		# or None (in which case they added the results themselves)
		if isinstance(data, tuple):
			mime, payload = data
			with job.openResult(mime, "result") as destF:
				destF.write(payload)

		elif isinstance(data, rsc.Data):
			destFmt = inputTable.getParam("responseformat", 
				"application/x-votable+xml")
			with job.openResult(destFmt, "result") as destF:
				formats.formatData(destFmt, data, destF, False)

		elif data is None:
			pass

		else:
			raise NotImplementedError("Cannot handle a service %s result yet."%
				repr(data))
		
		with job.getWritable() as wjob:
			wjob.change(phase=uws.COMPLETED)

	except SystemExit:
		pass
	except uws.JobNotFound:
		base.ui.notifyInfo("Giving up non-existing UWS job %s."%jobId)
	except Exception, ex:
		base.ui.notifyError("UWS runner %s major failure"%jobId)
		# try to push job into the error state -- this may well fail given
		# that we're quite hosed, but it's worth the try
		USER_WORKER.changeToPhase(jobId, uws.ERROR, ex)
		raise
