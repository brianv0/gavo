"""
Manipulating UWS jobs through a REST interface.

The result documents are defined through the schema uws-1.0.xsd.

Instead of returning XML, they can also raise WebRedirect exceptions.
However, these are caught in JobResource._redirectAsNecessary and appended
to the base URL auf the TAP service, so you must only give URIs relative
to the TAP service's root URL.

All this probably is only useful for web.taprender.

NOTE: The requests used here are not the normal twisted requests but instead
requests furnished with files and scalars attributes by 
taprender.reparseRequestArgs.
"""

from __future__ import with_statement

import os

from nevow import inevow
from nevow import rend
from nevow import static

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo.protocols import tap
from gavo.protocols import uws
from gavo.utils import stanxml
from gavo.utils import ElementTree
from gavo.votable import V


UWSNamespace = 'http://www.ivoa.net/xml/UWS/v1.0'
XlinkNamespace = "http://www.w3.org/1999/xlink"
stanxml.registerPrefix("uws", UWSNamespace,
	stanxml.schemaURL("uws-1.0.xsd"))
stanxml.registerPrefix("xlink", XlinkNamespace,
	stanxml.schemaURL("xlink.xsd"))


class UWS(object):
	"""the container for elements from the uws namespace.
	"""
	class UWSElement(stanxml.Element):
		_prefix = "uws"

	@staticmethod
	def makeRoot(ob):
		ob._additionalPrefixes = stanxml.xsiPrefix
		ob._mayBeEmpty = True
		return ob

	class job(UWSElement): pass
	class jobs(UWSElement):
		_mayBeEmpty = True

	class parameters(UWSElement): pass

	class destruction(UWSElement): pass
	class endTime(stanxml.NillableMixin, UWSElement): pass
	class executionDuration(UWSElement): pass
	class jobId(UWSElement): pass
	class jobInfo(UWSElement): pass
	class message(UWSElement): pass
	class ownerId(stanxml.NillableMixin, UWSElement): pass
	class phase(UWSElement): pass
	class quote(stanxml.NillableMixin, UWSElement): pass
	class runId(UWSElement): pass
	class startTime(stanxml.NillableMixin, UWSElement): pass
	
	class detail(UWSElement):
		_a_href = None
		_a_type = None
		_name_a_href = "xlink:href"
		_name_a_type = "xlink:type"
	
	class errorSummary(UWSElement):
		_a_type = None  # transient | fatal
		_a_hasDetail = None

	class message(UWSElement): pass

	class jobref(UWSElement):
		_additionalPrefixes = frozenset(["xlink"])
		_a_id = None
		_a_href = None
		_a_type = None
		_name_a_href = "xlink:href"
		_name_a_type = "xlink:type"

	class parameter(UWSElement):
		_a_byReference = None
		_a_id = None
		_a_isPost = None

	class result(UWSElement):
		_additionalPrefixes = frozenset(["xlink"])
		_mayBeEmpty = True
		_a_id = None
		_a_href = None
		_a_type = None
		_name_a_href = "xlink:href"
		_name_a_type = "xlink:type"

	class results(UWSElement):
		_mayBeEmpty = True


def getJobURL(jobId):
	"""returns a URL to access jobId's job info.
	"""
	return "%s/async/%s"%(
		base.caches.getRD(tap.RD_ID).getById("run").getURL("tap"),
		jobId)


def getJobList():
	jobstable = uws.getROJobsTable()
	fields = jobstable.tableDef.columns
	result = UWS.jobs()
	for row in jobstable.iterQuery([
			fields.getColumnByName("jobId"),
			fields.getColumnByName("phase"),], ""):
		result[
			UWS.jobref(id=row["jobId"], href=getJobURL(row["jobId"]))[
				UWS.phase[row["phase"]]]]
	return stanxml.xmlrender(result, "<?xml-stylesheet "
		"href='/static/xsl/uws-joblist-to-html.xsl' type='text/xsl'?>")


def getErrorSummary(job):
# all our errors are fatal, and for now .../error yields the same thing
# as we include here, so we hardcode the attributes.
	try:
			errDesc = job.getError()
	except ValueError:
		return None
	msg = errDesc["msg"]
	if errDesc["hint"]:
		msg = msg+"\n\n -- Hint: "+errDesc["hint"]
	return UWS.errorSummary(type="fatal", hasDetail="false")[
		UWS.message[msg]]


def getParametersElement(job):
	"""returns a UWS.parameters element for job.
	"""
	res = UWS.parameters()
	for key, value in job.iterParameters():
		if isinstance(value, uws.ParameterRef):
			res[UWS.parameter(id=key, byReference=True)[value.url]]
		else:
			res[UWS.parameter(id=key)[str(value)]]
	return res


class _JobActions(object):
	"""A collection of "actions" performed on UWS jobs.

	These correspond to the resources specified in the UWS spec.

	It is basically a dispatcher to JobAction instances which are added
	through the addAction method.
	"""
	actions = {}

	@classmethod
	def addAction(cls, actionClass):
		cls.actions[actionClass.name] = actionClass()

	@classmethod
	def dispatch(cls, action, job, request, segments):
		try:
			resFactory = cls.actions[action]
		except KeyError:
			raise base.ui.logOldExc(
				svcs.UnknownURI("Invalid UWS action '%s'"%action))
		return resFactory.getResource(job, request, segments)
		

class JobAction(object):
	"""an action done to a job.

	It defines methods do<METHOD> that are dispatched through JobActions.

	It must have a name corresponding to the child resource names from
	the UWS spec.
	"""
	name = None

	def getResource(self, job, request, segments):
		if segments:
			raise svcs.UnknownURI("Too many segments")
		try:
			handler = getattr(self, "do"+request.method)
		except AttributeError:
			raise base.ui.logOldExc(svcs.BadMethod(request.method))
		return handler(job, request)


class ErrorResource(rend.Page):
	"""A TAP error message.

	These are constructed with errInfo, which is either an exception or
	a dictionary containing at least type, msg, and hint keys.  Optionally, 
	you can give a numeric httpStatus.
	"""
	def __init__(self, errInfo, httpStatus=400):
		if isinstance(errInfo, Exception):
			errInfo = {
				"msg": unicode(errInfo),
				"type": errInfo.__class__.__name__,
				"hint": getattr(errInfo, "hint", None)}
		if errInfo["type"]=="JobNotFound":
			httpStatus = 404
		self.errMsg, self.httpStatus = errInfo["msg"], httpStatus
		self.hint = errInfo["hint"]

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		request.setResponseCode(self.httpStatus)
		doc = V.VOTABLE[
			V.RESOURCE(type="results") [
				V.INFO(name="QUERY_STATUS", value="ERROR")[
						self.errMsg]]]
		if self.hint:
			doc[V.INFO(name="HINT", value="HINT")[
				self.hint]]
		return doc.render()


class ErrorAction(JobAction):
	name = "error"

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		try:
			excInfo = job.getError()
			return ErrorResource(excInfo, httpStatus=200)
		except ValueError:  # no error posted so far
			pass
		return ""

	doPOST = doGET
_JobActions.addAction(ErrorAction)


class ParameterAction(JobAction):
	name = "parameters"

	def doGET(self, job, request):
		request.setHeader("content-type", "text/xml")
		return UWS.makeRoot(getParametersElement(job))
	
	def doPOST(self, job, request):
		with job.getWritable() as wjob:
			for key, value in request.scalars.iteritems():
				wjob.addParameter(key, value)
		raise svcs.WebRedirect("async/"+job.jobId)

_JobActions.addAction(ParameterAction)

class PhaseAction(JobAction):
	name = "phase"
	timeout = 10  # this is here for testing

	def doPOST(self, job, request):
		newPhase = request.scalars.get("PHASE", None)
		with job.getWritable(self.timeout) as wjob:
			if newPhase=="RUN":
				wjob.changeToPhase(uws.QUEUED)
			elif newPhase=="ABORT":
				wjob.changeToPhase(uws.ABORTED)
			else:
				raise base.ValidationError("Bad phase: %s"%newPhase, "phase")
		raise svcs.WebRedirect("async/"+job.jobId)
	
	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		return job.phase
_JobActions.addAction(PhaseAction)


class _SettableAction(JobAction):
	"""Abstract base for ExecDAction and DestructionAction.
	"""
	def doPOST(self, job, request):
		raw = request.scalars.get(self.name.upper(), None)
		if raw is None:  # with no parameter, fall back to GET
			return self.doGET(job, request)
		try:
			val = self.deserializeValue(raw)
		except ValueError:  
			raise base.ui.logOldExc(uws.UWSError("Invalid %s value: %s."%(
				self.name.upper(), repr(raw)), job.jobId))
		with job.getWritable() as wjob:
			setattr(wjob, self.attName, val)
		raise svcs.WebRedirect("async/"+job.jobId)

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		return self.serializeValue(getattr(job, self.attName))


# XXX TODO: These should probably simply go through uwsjob.addParameter
class ExecDAction(_SettableAction):
	name = "executionduration"
	attName = 'executionDuration'
	serializeValue = str
	deserializeValue = float
_JobActions.addAction(ExecDAction)


class DestructionAction(_SettableAction):
	name = "destruction"
	attName = "destructionTime"
	serializeValue = staticmethod(utils.formatISODT)
	deserializeValue = staticmethod(utils.parseISODT)
_JobActions.addAction(DestructionAction)


class QuoteAction(JobAction):
	name = "quote"

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		if job.quote is None:
			quote = ""
		else:
			quote = str(job.quote)
		return quote
	
_JobActions.addAction(QuoteAction)


class OwnerAction(JobAction):
	# we do not support auth yet, so this is a no-op.
	name = "owner"
	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		if job.owner is None:
			request.write("NULL")
		else:
			request.write(job.owner)
		return ""

_JobActions.addAction(OwnerAction)


def _getResultsElement(job):
	baseURL = getJobURL(job.jobId)+"/results/"
	return UWS.results[[
			UWS.result(id=res["resultName"], href=baseURL+res["resultName"])
		for res in job.getResults()]]


class ResultsAction(JobAction):
	"""Access result (Extension: and other) files in job directory.
	"""
	name = "results"

	def getResource(self, job, request, segments):
		if not segments:
			return JobAction.getResource(self, job, request, segments)

		# first try a "real" UWS result from the job
		if len(segments)==1:
			try:
				fName, resultType = job.getResult(segments[0])
				res = static.File(fName)
				res.type = str(resultType)
				res.encoding = None
				return res
			except base.NotFoundError: # segments[0] does not name a result
				pass                     # fall through to other files

		# if that doesn't work, try to return some other file from the
		# job directory.  This is so we can deliver uploads.
		filePath = os.path.join(job.getWD(), *segments)
		if not os.path.exists(filePath):
			raise svcs.UnknownURI("File not found")
		return static.File(filePath, defaultType="application/octet-stream")

	def doGET(self, job, request):
		return _getResultsElement(job)

_JobActions.addAction(ResultsAction)


def _serializeTime(element, dt):
	if dt is None:
		return element()
	return element[utils.formatISODT(dt)]


class RootAction(JobAction):
	"""Actions for async/jobId.
	"""
	name = ""
	def doDELETE(self, job, request):
		with job.getWritable() as wjob:
			wjob.delete()
		raise svcs.WebRedirect("async")

	def doPOST(self, job, request):
		# (Extension to let web browser delete jobs)
		with job.getWritable() as wjob:
			if utils.getfirst(request.args, "ACTION")=="DELETE":
				self.doDELETE(wjob, request)
			else:
				raise svcs.BadMethod("POST")

	def doGET(self, job, request):
		tree = UWS.makeRoot(UWS.job[
			UWS.jobId[job.jobId],
			UWS.runId[job.runId],
			UWS.ownerId[job.owner],
			UWS.phase[job.phase],
			_serializeTime(UWS.startTime, job.startTime),
			_serializeTime(UWS.endTime, job.endTime),
			UWS.executionDuration[str(job.executionDuration)],
			UWS.destruction[utils.formatISODT(job.destructionTime)],
			getParametersElement(job),
			_getResultsElement(job),
			getErrorSummary(job)])
		return stanxml.xmlrender(tree,
			"<?xml-stylesheet href='%s' type='text/xsl'?>"%
				"/static/xsl/uws-job-to-html.xsl")

_JobActions.addAction(RootAction)


def doJobAction(request, segments):
	"""handles the async UI of UWS.

	Depending on method and segments, it will return various XML strings
	and may cause certain actions.

	Segments must be a tuple with at least one element, the job id.
	"""
	jobId, segments = segments[0], segments[1:]
	if not segments:
		action = ""
	else:
		action, segments = segments[0], segments[1:]
# XXX TODO: We need some parametrization of what UWSJob subclass gets
# used here and in subclasses
	return _JobActions.dispatch(action, 
		tap.ROTAPJob.makeFromId(jobId), request, segments)
