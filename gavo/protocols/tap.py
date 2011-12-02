"""
TAP: schema maintenance, job/parameter definition incl. upload and UWS actions.
"""

from __future__ import with_statement

import os
import signal
import subprocess
import warnings
from cStringIO import StringIO

from pyparsing import ParseException
from twisted.internet import reactor
from twisted.internet import protocol
import twisted.internet.utils

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import utils
from gavo.protocols import uws
from gavo.utils import codetricks


RD_ID = "__system__/tap"


# A mapping of values of TAP's FORMAT parameter to our formats.format codes,
# IANA mimes and user-readable labels.
# Used below (1st element of value tuple) and for registry purposes.
FORMAT_CODES = {
	"application/x-votable+xml": 
		("votable", "application/x-votable+xml", "VOTable, binary", 
			"ivo://ivoa.net/std/TAPRegExt#output-votable-binary"),
	"text/xml": 
		("votable", "text/xml", "VOTable, binary",
			"ivo://ivoa.net/std/TAPRegExt#output-votable-binary"),
	"votable": 
		("votable", "application/x-votable+xml", "VOTable, binary",
			"ivo://ivoa.net/std/TAPRegEXT#output-votable-binary"),
	"application/x-votable+xml;encoding=tabledata":
		("votabletd", "application/x-votable+xml;encoding=tabledata", 
			"VOTable, tabledata",
			"ivo://ivoa.net/std/TAPRegEXT#output-votable-td"),
	"votable/td":
		("votabletd", "application/x-votable+xml;encoding=tabledata", 
			"VOTable, tabledata",
			"ivo://ivoa.net/std/TAPRegEXT#output-votable-td"),
	"text/csv": 
		("csv", "text/csv", "CSV without column labels", None),
	"csv": ("csv+header", "text/csv;header=present", 
			"CSV with column labels", None),
	"text/csv;header=present": 
		("csv+header", "text/csv;header=present",
			"CSV with column labels", None),
	"text/tab-separated-values": 
		("tsv", "text/tab-separated-values", 
			"Tab separated values", None),
	"tsv": 
		("tsv", "text/tab-separated-values", 
			"Tab separated values", None),
	"application/fits": 
		("fits", "application/fits", "FITS binary table", None),
	"fits":
		("fits", "application/fits", "FITS binary table", None),
	"text/html": 
		("html", "text/html", "HTML table", None),
	"html": 
		("html", "text/html", "HTML table", None),
}


# this is used below in for registry purposes (values are pairs of
# IVOA id and a human-readable label).
SUPPORTED_LANGUAGES = {
	"ADQL": ("ivo://ivoa.net/std/ADQL#v2.0", "ADQL 2.0"),
	"ADQL-2.0": ("ivo://ivoa.net/std/ADQL#v2.0", "ADQL 2.0"),
}


# A list of supported upload methods.  This is only used in the registry
# interface right now.
UPLOAD_METHODS = {
	"upload-inline": "POST inline upload",
	"upload-http": "http URL",
	"upload-https": "https URL",
	"upload-ftp": "ftp URL",
}


class TAPError(base.Error):
	"""TAP-related errors, mainly to communicate with web renderers.

	TAPErrors are constructed with a displayable message (may be None to
	autogenerate one) and optionally a source exception and a hint.
	"""
	def __init__(self, msg, sourceEx=None, hint=None):
		base.Error.__init__(self, msg, hint=hint)
		self.msg = msg
		self.sourceEx = sourceEx
	
	def __str__(self):
		if self.msg:
			return self.msg
		elif self.sourceEx:
			return "TAP operation failed (%s, %s)"%(
				self.sourceEx.__class__.__name__,
				str(self.sourceEx))
		else:
			return "Unspecified TAP related error"


######################## registry interface helpers

def getSupportedLanguages():
	"""returns a list of tuples for the supported languages.

	This is tap.SUPPORTED_LANGUAGES in a format suitable for the
	TAP capabilities element.

	Each tuple is made up of (name, version, description, ivo-id).
	"""
	langs = []
	for fullName, (ivoId,descr) in SUPPORTED_LANGUAGES.iteritems():
		try:
			name, version = fullName.split("-", 1)
		except ValueError: 
			# fullName has no version info, there must be at least one entry
			# that includes a version, so skip this one.
			continue
		langs.append((name, version, descr, ivoId))
	return langs


def getSupportedOutputFormats():
	"""yields tuples for the supported output formats.

	This is tap.OUTPUT_FORMATS in a format suitable for the
	TAP capabilities element.

	Each tuple is made up of (mime, aliases, description, ivoId).
	"""
	codes, descrs, ivoIds = {}, {}, {}
	for code, (_, outputMime, descr, ivoId) in FORMAT_CODES.iteritems():
		codes.setdefault(outputMime, set()).add(code)
		descrs[outputMime] = descr
		ivoIds[outputMime] = ivoId
	for mime in codes:
		# mime never is an alias of itself
		codes[mime].discard(mime)
		yield mime, codes[mime], descrs[mime], ivoIds[mime]


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
	rd.setProperty("moribund", "True") # the embedded grammar take this
	                                   # to mean "kill this"
	publishToTAP(rd, connection)
	rd.clearProperty("moribund")


def getAccessibleTables():
	"""returns a list of qualified table names for the TAP-published tables.
	"""
	tapRD = base.caches.getRD(RD_ID)
	td = tapRD.getById("tables")
	table = rsc.TableForDef(td)
	res = [r["table_name"] for r in 
		table.iterQuery([td.getColumnByName("table_name")], "",
			limits=("order by table_name", {}))]
	table.close()
	return res


########################## The TAP UWS job


@utils.memoized
def getUploadGrammar():
	from pyparsing import (Word, ZeroOrMore, Suppress, StringEnd,
		alphas, alphanums, CharsNotIn)
	# Should we allow more tableNames?
	with utils.pyparsingWhitechars(" \t"):
		tableName = Word( alphas+"_", alphanums+"_" )
		# What should we allow/forbid in terms of URIs?
		uri = CharsNotIn(" ;,")
		uploadSpec = tableName("name") + "," + uri("uri")
		uploads = uploadSpec + ZeroOrMore(
			Suppress(";") + uploadSpec) + StringEnd()
		uploadSpec.addParseAction(lambda s,p,t: (t["name"], t["uri"]))
		return uploads


def parseUploadString(uploadString):
	"""iterates over pairs of tableName, uploadSource from a TAP upload string.
	"""
	try:
		res = getUploadGrammar().parseString(uploadString).asList()
		return res
	except ParseException, ex:
		raise base.ValidationError(
			"Syntax error in UPLOAD parameter (near %s)"%(ex.loc), "UPLOAD",
			hint="Note that we only allow regular SQL identifiers as table names,"
				" i.e., basically only alphanumerics are allowed.")


class LangParameter(uws.ProtocolParameter):
	name = "LANG"

	@classmethod
	def addParam(cls, value, job):
		if value not in SUPPORTED_LANGUAGES:
			raise base.ValidationError("This service does not support the"
				" query language %s"%value, "LANG")
		job.parameters["LANG"] = value


class QueryParameter(uws.ProtocolParameter):
	name = "QUERY"


class FormatParameter(uws.ProtocolParameter):
	name = "FORMAT"


class MaxrecParameter(uws.ProtocolParameter):
	name = "MAXREC"
	_serialize, _deserialize = str, int


class LocalFile(object):
	"""A sentinel class representing a file within a job work directory
	(as resulting from an upload).
	"""
	def __init__(self, jobId, wd, fileName):
		self.jobId, self.fileName = jobId, fileName
		self.fullPath = os.path.join(wd, fileName)

	def __str__(self):
		# stringify to a URL for easy UPLOAD string generation.
		# This smells of a bad idea.  If you change it, change UPLOAD.getParam.
		return self.getURL()

	def getURL(self):
		"""returns the URL the file is retrievable under for the life time of
		the job.
		"""
		return base.caches.getRD(RD_ID).getById("run").getURL("tap",
			absolute=True)+"/async/%s/results/%s"%(
				self.jobId,
				self.fileName)


class _FakeUploadedFile(object):
# File uploads without filenames are scalars containing a string.
# This class lets them work as uploaded files in _saveUpload.
	def __init__(self, name, content):
		self.filename = name
		self.file = StringIO(content)


class UploadParameter(uws.ProtocolParameter):
# the way this is specified, inline uploads are quite tricky. 
# To obtain the data, we must access the request, which we don't have
# here.  Since I happen to think this is a major wart in the spec,
# I solve this through a major wart: I get the request from some
# frame upstack.
	name = "UPLOAD"
	@classmethod
	def addParam(cls, value, job):
		if not value.strip():
			return
		newUploads = []
		for tableName, upload in parseUploadString(value):
			if upload.startswith("param:"):
				newUploads.append(
					(tableName, cls._saveUpload(job, upload[6:])))
			else:
				newUploads.append((tableName, upload))
		job.parameters["UPLOAD"] = job.parameters.get("UPLOAD", []
			)+newUploads

	@classmethod
	def getParam(cls, job):
		return ";".join("%s,%s"%p for p in job.parameters["UPLOAD"])

	@classmethod
	def _cleanName(cls, rawName):
		# returns a name hopefully suitable for the file system
		return rawName.encode("quoted-printable").replace('/', "=2F")

	@classmethod
	def _saveUpload(cls, job, uploadName):
		# I deeply detest this UPLOAD spec...  To express this, I'm stealing
		# the server request object from a higher stack frame.  This must
		# be a request that has been processed by taprender.reparseRequestArgs.
		# This function returns a LocalFile instance.
		try:
			uploadData = codetricks.stealVar("request").files[uploadName]
		except KeyError:
			# if no file name has been passed, the upload will end up in
			# scalars; I should probably do away with the whole files vs.
			# scalars business and the reparseRequestArgs nonsense.
			# Think about it.
			try:
				uploadData = _FakeUploadedFile(uploadName,
					codetricks.stealVar("request").scalars[uploadName])
			except KeyError:
				raise base.ui.logOldExc(
					base.ValidationError("No upload '%s' found"%uploadName, "UPLOAD"))
		destFName = cls._cleanName(uploadData.filename)
		with job.openFile(destFName, "w") as f:
			f.write(uploadData.file.read())
		return LocalFile(job.jobId, job.getWD(), destFName)


class _TAPJobMixin(object):
	protocolParameters = uws.UWSParameters(uws.UWSJob.protocolParameters,
		*utils.iterDerivedClasses(uws.ProtocolParameter, globals().values()))


class ROTAPJob(_TAPJobMixin, uws.ROUWSJob):
	"""an ROUWSJob with TAP protocol parameters.
	"""
	def getWritable(self, timeout=10):
		return TAPJob.makeFromId(self.jobId, timeout=timeout)


class TAPJob(_TAPJobMixin, uws.UWSJob):
	"""a UWSJob with TAP protocol parameters.
	"""


########################## Maintaining TAP jobs


def _replaceFDs(inFName, outFName):
# This is used for clean forking and doesn't actually belong here.
# utils.ostricks should take this.
  """closes all (findable) file descriptors and replaces stdin with inF
  and stdout/err with outF.
  """
  for fd in range(255, -1, -1):
    try:
      os.close(fd)
    except os.error:
      pass
  ifF, outF = open(inFName), open(outFName, "w")
  os.dup(outF.fileno())



class _TAPBackendProtocol(protocol.ProcessProtocol):
	"""The protocol used for taprunners when spawning them under a twisted
	reactor.
	"""
	def __init__(self, jobId):
		self.jobId = jobId

	def outReceived(self, data):
		base.ui.notifyInfo("TAP client %s produced output: %s"%(
			self.jobId, data))
	
	def errReceived(self, data):
		base.ui.notifyInfo("TAP client %s produced an error message: %s"%(
			self.jobId, data))
	
	def processEnded(self, statusObject):
		"""tries to ensure the job is in an admitted end state.
		"""
		try:
			with uws.UWSJob.makeFromId(self.jobId) as job:
			
				if job.phase==uws.QUEUED or job.phase==uws.EXECUTING:
					try:
						raise uws.UWSError("Job hung in %s"%job.phase, job.jobId)
					except uws.UWSError, ex:
						job.changeToPhase(uws.ERROR, ex)
		except uws.JobNotFound: # job already deleted
			pass


class TAPActions(uws.UWSActions):
	"""The transition function for TAP jobs.

	There's a hack here: After each transition, when you've released
	your lock on the job, call checkProcessQueue (in reality, only
	PhaseAction does this).
	"""
	def __init__(self):
		uws.UWSActions.__init__(self, "TAP", [
			(uws.PENDING, uws.QUEUED, "queueJob"),
			(uws.PENDING, uws.ABORTED, "markAborted"),
			(uws.QUEUED, uws.ABORTED, "markAborted"),
			(uws.EXECUTING, uws.COMPLETED, "completeJob"),
			(uws.EXECUTING, uws.ABORTED, "killJob"),
			(uws.EXECUTING, uws.ERROR, "errorOutJob"),
# Unknown is abused here as "forked, but not up yet"
# Thus, it's to be treated more or less like executing
			(uws.UNKNOWN, uws.COMPLETED, "completeJob"),
			(uws.UNKNOWN, uws.ABORTED, "killJob"),
			(uws.UNKNOWN, uws.ERROR, "errorOutJob"),
			(uws.COMPLETED, uws.ERROR, "ignoreAndLog"),
			])
		# _processQueueDirty is set if the QUEUED jobs are expected
		# to have a chance to get run; this is set by action
		self._processQueueDirty = False

	def _startJobTwisted(self, job):
		"""starts a job when we're running within a twisted reactor.
		"""
		pt = reactor.spawnProcess(_TAPBackendProtocol(job.jobId),
			"gavo", args=["gavo", "tap", "--", str(job.jobId)],
				env=os.environ)
		job.pid = pt.pid
		job.phase = uws.UNKNOWN

	def _startJobNonTwisted(self, job):
		"""forks off a new job when (hopefully) a manual child reaper is in place.
		"""
		try:
			pid = os.fork()
			if pid==0:
				_replaceFDs("/dev/zero", "/dev/null")
				os.execlp("gavo", "gavo", "--disable-spew", 
					"tap", "--", job.jobId)
			elif pid>0:
				job.pid = pid
				job.phase = uws.UNKNOWN
			else:
				raise Exception("Could not fork")
		except Exception, ex:
			job.changeToPhase(uws.ERROR, ex)
	
	def _startJob(self, job):
		"""causes a process to be started that executes job.

		This dispatches according to whether or not we are within a twisted
		event loop, mostly for testing support.
		"""
		if reactor.running:
			return self._startJobTwisted(job)
		else:
			return self._startJobNonTwisted(job)

	def _manuallyErrorOutJob(self, writableJobsTable, jobId, errMsg):
		job = ROTAPJob(jobId)
		with job.getWritable() as wj:
			wj.setError(errMsg)
			base.ui.notifyError("Stale/dead taprunner: '%s'"%errmsg)
			wj.changeToPhase(uws.ERROR)

	def _ensureJobsAreRunning(self):
		"""pushes all executing jobs that silently died to ERROR.
		"""
		jt = uws.getROJobsTable()
		for jobId, pid in  jt.iterquery([
					jt.tableDef.getColumnByName("jobId"),
					jt.tableDef.getColumnByName("pid")],
				"phase='EXECUTING'"):

			if pid is None:
				self._manuallyErrorOutJob(jobId,
					"EXECUTING job %s had no pid."%jobId)
			else:
				try:
					os.waitpid(pid, os.WNOHANG)
				except os.error: # child presumably is dead
					self._manuallyErrorOutJob(jobId,
						"EXECUTING job %s has silently died."%jobId)

	def _processQueue(self):
		"""tries to take jobs from the queue.

		This function is called whenever a job is queued and on transitions
		from EXECUTING so somewhere else.

		Currently, the jobs with the earliest destructionTime are processed
		first.  That's, of course, completely ad-hoc.

		job is the job that initiated the action.  We need it since it's
		likely it is being manipulated, and so we need to commit all its
		changes.  Also, it needs updating at the end of this function.
		"""
		if uws.countQueuedJobs()==0:
			return
		runcountGoal = base.getConfig("async", "maxTAPRunning")

		jobsTable = uws.getROJobsTable()
		try:
			started = 0
			for row in  list(jobsTable.iterQuery(
					[jobsTable.tableDef.getColumnByName("jobId")],
					"phase=%(phase)s", {"phase": uws.QUEUED},
					limits=('ORDER BY destructionTime ASC', {}))):
				if uws.countRunningJobs()>=runcountGoal:
					break
				self._startJob(TAPJob(row["jobId"]))
				started += 1
			
			if started==0:
				# No jobs could be started.  This may be fine when long-runnning
				# jobs  block job submission, but for catastrophic taprunner
				# failures we want to make sure all jobs we think are executing
				# actually are.  If they've silently died, we log that and
				# push them to error.
				self._ensureJobsAreRunning()
		except Exception, ex:
			base.ui.notifyError("Error during queue processing, TAP"
				" is probably botched now.")

	def checkProcessQueue(self):
		if self._processQueueDirty:
			self._processQueueDirty = False
			self._processQueue()

	def queueJob(self, newState, job, ignored):
		"""starts a job.

		The method will venture a guess whether there is a twisted reactor
		and dispatch to _startReactorX methods based on this guess.
		"""
		job.phase = uws.QUEUED
		self._processQueueDirty = True

	def errorOutJob(self, newPhase, job, ignored):
		self.flagError(newPhase, job, ignored)
		self._processQueueDirty = True

	def completeJob(self, newPhase, job, ignored):
		job.phase = newPhase
		self._processQueueDirty = True

	def killJob(self, newState, job, ignored):
		"""tries to kill -INT the pid the job has registred.

		This will raise a TAPError with some description if that's not possible
		for some reason.

		This does not actually change the job's state.  That's the job of
		the child taprunner.
		"""
		try:
			try:
				pid = job.pid
				if pid is None:
					raise TAPError("Job is not running")
				os.kill(pid, signal.SIGINT)
			except TAPError:
				raise
			except Exception, ex:
				raise TAPError(None, ex)
		finally:
			self._processQueueDirty = True

	def markAborted(self, newState, job, ignored):
		"""simply marks job as aborted.

		This is what happens if you abort a job from QUEUED or
		PENDING.
		"""
		job.phase = uws.ABORTED
		job.endTime = datetime.datetime.utcnow()

	def ignoreAndLog(self, newState, job, exc):
		base.ui.logErrorOccurred("Request to push COMPLETED job to ERROR: %s"%
			str(exc))
uws.registerActions(TAPActions)
