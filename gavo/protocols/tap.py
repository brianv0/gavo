"""
Code to help TAP.
"""

from __future__ import with_statement

import os
import signal
import subprocess

from pyparsing import ParseException

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import utils
from gavo.protocols import uws
from gavo.utils import codetricks


RD_ID = "__system__/tap"
TAP_VERSION = "1.0"


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


########################## The TAP UWS job


def _makeUploadGrammar():
	from pyparsing import (Word, ZeroOrMore, Suppress, StringEnd,
		alphas, alphanums, CharsNotIn)
	# Should we allow more tableNames?
	tableName = Word( alphas+"_", alphanums+"_" )
	# What should we allow/forbid in terms of URIs?
	uri = CharsNotIn(" ;,")
	uploadSpec = tableName("name") + "," + uri("uri")
	uploads = uploadSpec + ZeroOrMore(
		Suppress(";") + uploadSpec) + StringEnd()
	uploadSpec.addParseAction(lambda s,p,t: (t["name"], t["uri"]))
	return uploads


getUploadGrammar = utils.CachedGetter(_makeUploadGrammar)


def parseUploadString(uploadString):
	"""iterates over pairs of tableName, uploadSource from a TAP upload string.
	"""
	try:
		return getUploadGrammar().parseString(uploadString).asList()
	except ParseException, ex:
		raise base.ValidationError("Syntax error in upload string (near %s)"%(
			ex.loc), "UPLOAD")


class LangParameter(uws.ProtocolParameter):
	name = "LANG"

	@classmethod
	def addParam(cls, value, job):
		if value not in set(["ADQL", "ADQL-2.0"]):
			raise base.ValidationError("This service does not support the"
				" query language %s"%value, "LANG")
		job.parameters["LANG"] = value


class QueryParameter(uws.ProtocolParameter):
	name = "QUERY"


class FormatParameter(uws.ProtocolParameter):
	name = "FORMAT"

	@classmethod
	def addParam(cls, value, job):
		formats.checkFormatIsValid(value)
		job.parameters["FORMAT"] = value


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
			raise base.ValidationError("No upload '%s' found"%uploadName, "UPLOAD")
		destFName = cls._cleanName(uploadData.filename)
		with job.openFile(destFName, "w") as f:
			f.write(uploadData.file.read())
		return LocalFile(job.jobId, job.getWD(), destFName)


class TAPJob(uws.UWSJob):
	"""An asynchronous TAP job.
	"""
	protocolParameters = uws.UWSParameters(uws.UWSJob.protocolParameters,
		*utils.iterDerivedClasses(uws.ProtocolParameter, globals().values()))


########################## Maintaining TAP jobs

class TAPActions(uws.UWSActions):
# XXX TODO: Implement a real queue rather than starting blindly
	def __init__(self):
		uws.UWSActions.__init__(self, "TAP", [
			(uws.PENDING, uws.QUEUED, "startJob"),
			(uws.QUEUED, uws.ABORTED, "noOp"),
			(uws.EXECUTING, uws.COMPLETED, "noOp"),
			(uws.EXECUTING, uws.ABORTED, "killJob"),
			])
	
	def startJob(self, newState, job, ignored):
		"""forks off a new Job.
		"""
		try:
			child = subprocess.Popen(["gavo", "--disable-spew", "--", 
				"tap", job.jobId])
			job.phase = uws.QUEUED
			job.pid = child.pid
		except Exception, ex:
			job.changeToPhase(uws.ERROR, ex)


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
