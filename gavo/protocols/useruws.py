"""
Support for UWSes defined in user RDs.

To understand this, start at makeUWSForService.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cPickle as pickle
import datetime
import weakref

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdesc #noflake: for registration
from gavo import svcs
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


def makeUWSJobParameterFor(inputKey):
	"""returns a uws.JobParameter instance for inputKey.
	"""
	class SomeParameter(uws.JobParameter):
		name = inputKey.name
		_deserialize = inputKey._parse
		_serialize = inputKey._unparse
	return SomeParameter


class UserUWSJobBase(uws.UWSJobWithWD):
	"""The base class for the service-specific user UWS jobs.

	(i.e., the things that the UserUWSJobFactory spits out)
	"""
	_transitions = UserUWSTransitions()
	_jobsTDId = "//uws#userjobs"


def makeUserUWSJobClass(service):
	"""returns a class object for representing UWS jobs processing requests
	for service
	"""
	class UserUWSJob(UserUWSJobBase):
		pass

	defaults = {}
	for ik in service.getInputKeysFor("uws.xml"):
		if ik.type=="file":
			# these are handled by UPLOAD
			setattr(UserUWSJob, "_parameter_upload", uws.UploadParameter())
			setattr(UserUWSJob, "_parameter_"+ik.name, uws.FileParameter())
			continue

		setattr(UserUWSJob, "_parameter_"+ik.name,
			makeUWSJobParameterFor(ik))
		defaults[ik.name] = ik.values.default

	defaultStr = pickle.dumps(defaults, protocol=2
		).encode("zlib").encode("base64")
	del defaults
	def _(cls):
		return defaultStr
	
	UserUWSJob._default_parameters = classmethod(_)
	UserUWSJob._default_jobClass = classmethod(
		lambda _, v=service.getFullId(): v)
	
	return UserUWSJob


class UserUWS(uws.UWSWithQueueing):
	"""A UWS for "user jobs", i.e., generic things an a core.

	These dynamically create job classes based on the processing core's
	parameters.  To make this happen, we'll need to override some of the
	common UWS functions.
	"""
	joblistPreamble = ("<?xml-stylesheet href='/static"
		"/xsl/useruws-joblist-to-html.xsl' type='text/xsl'?>")
	jobdocPreamble = ("<?xml-stylesheet href='/static/xsl/"
		"useruws-job-to-html.xsl' type='text/xsl'?>")

	def __init__(self, service, jobActions):
		self.runcountGoal = base.getConfig("async", "maxUserUWSRunningDefault")
		self.service = weakref.proxy(service)
		uws.UWSWithQueueing.__init__(self, 
			makeUserUWSJobClass(service), jobActions)

	def _makeMoreStatements(self, statements, jobsTable):
		# for user UWSes, we only want jobs from our service in the job
		# list resource.  We change the respective queries; we don't
		# change getById and getAllIds, though, as they're used internally
		# and could influence, e.g., queueing and such.

		# jobClass values in principle are controlled, so literal inclusion
		# in the queries should be safe.  Let's just add a little extra for
		# defensiveness:
		jobClass = self.service.getFullId().replace("'", "")
		td = jobsTable.tableDef

		statements["getIdsAndPhases"] = jobsTable.getQuery(
				[td.getColumnByName("jobId"), td.getColumnByName("phase")], 
				"jobClass='%s'"%jobClass)
		statements["getIdsAndPhasesForOwner"] = jobsTable.getQuery(
			[td.getColumnByName("jobId"), td.getColumnByName("phase")], 
				"owner=%%(owner)s AND jobClass='%s'"%jobClass, 
				{"owner": ""})
		uws.UWSWithQueueing._makeMoreStatements(self, statements, jobsTable)

	def getURLForId(self, jobId):
		return self.service.getURL("uws.xml")+"/"+jobId

	def _getJob(self, jobId, conn, writable=False):
		"""returns the named job as uws.UWS._getJob.

		However, in a user UWS, there can be jobs from multiple services.
		It would be nonsense to load another UWS's job's parameters into our
		job class.  To prevent this, we redirect if we find the new job's
		class isn't ours. On the web interface, that should do the trick.  
		Everywhere else, this may not be entirely clear but still prevent 
		major confusion.

		This is repeating code from uws.UWS._getJob; some refactoring at
		some point would be nice.
		"""
		statementId = 'getById'
		if writable:
			statementId = 'getByIdEx'
		res = self.runCanned(statementId, {"jobId": jobId}, conn)
		if len(res)!=1:
			raise uws.JobNotFound(jobId)
	
		if res[0]["jobClass"]!=self.service.getFullId():
			raise svcs.WebRedirect(
				base.resolveCrossId(res[0]["jobClass"]).getUWS().getURLForId(jobId))

		return self.jobClass(res[0], self, writable)


		
def makeUWSForService(service):
	"""returns a UserUWS instance tailored to service.

	All these share a jobs table, but the all have different job
	classes with the parameters custom-made for the service's core.

	A drawback of this is that each UWS created in this way runs the
	job table purger again.  That shouldn't be a problem per se but
	may become cumbersome at some point.  We can always introduce a
	class Attribute on UserUWS to keep additional UWSes from starting
	cron jobs of their own.
	"""
	return UserUWS(service, uwsactions.JobActions())


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
	with base.getTableConn() as conn:
		svcId = list(
			conn.query("SELECT jobclass FROM uws.userjobs WHERE jobId=%(jobId)s",
				{"jobId": jobId}))[0][0]
	service = base.resolveCrossId(svcId)

	try:
		job = service.getUWS().getJob(jobId)
		with job.getWritable() as wjob:
			wjob.change(phase=uws.EXECUTING, startTime=datetime.datetime.utcnow())

		service = base.resolveCrossId(job.jobClass)
		inputTable = rsc.TableForDef(service.core.inputTable)
		inputTable.job = job

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
		service.getUWS().changeToPhase(jobId, uws.ERROR, ex)
		raise
