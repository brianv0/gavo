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

from nevow import static

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import utils
from gavo.protocols import tap
from gavo.protocols import uws
from gavo.utils import stanxml
from gavo.utils import ElementTree


UWSNamespace = 'http://www.ivoa.net/xml/UWS/v1.0rc3'
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

	class NillableMixin(object):
		_mayBeEmpty = True
		_a_nil = None
		_name_a_nil = "xsi:nil"


	class job(UWSElement): pass
	class jobs(UWSElement):
		_mayBeEmpty = True

	class parameters(UWSElement): pass

	class destruction(UWSElement): pass
	class endTime(UWSElement, NillableMixin): pass
	class executionDuration(UWSElement): pass
	class jobId(UWSElement): pass
	class jobInfo(UWSElement): pass
	class message(UWSElement): pass
	class ownerId(UWSElement, NillableMixin): pass
	class phase(UWSElement): pass
	class quote(UWSElement, NillableMixin): pass
	class runId(UWSElement): pass
	class startTime(UWSElement, NillableMixin): pass
	
	class detail(UWSElement):
		_a_href = None
		_a_type = None
		_name_a_href = "xlink:href"
		_name_a_type = "xlink:type"
	
	class errorSummary(UWSElement):
		_a_type = None  # transient | fatal

	class jobref(UWSElement):
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
		_mayBeEmpty = True
		_a_id = None
		_a_href = None
		_a_type = None
		_href_name = "xlink:href"
		_type_name = "xlink:type"

	class results(UWSElement):
		_mayBeEmpty = True


def getJobList():
	jobstable = uws.getJobsTable()
	fields = jobstable.tableDef.columns
	result = UWS.jobs()
	for row in jobstable.iterQuery([
			fields.getColumnByName("jobId"),
			fields.getColumnByName("phase"),], ""):
		result[
			UWS.jobref(id=row["jobId"])[
				UWS.phase[row["phase"]]]]
	jobstable.close()
	return stanxml.xmlrender(result, "<?xml-stylesheet "
		"href='/static/xsl/uws-joblist-to-html.xsl' type='text/xsl'?>")


def getErrorSummary(job):
# all our errors are fatal, and for now .../error yields the same thing
# as we include here, so we hardcode the attributes.
	if job.phase!=uws.ERROR:
		return None
	return UWS.errorSummary(type="fatal")[
		str(job.getError())]


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

	It is defines methods do<METHOD> that are dispatched through JobActions.

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


class ErrorAction(JobAction):
	name = "error"

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		try:
			request.write(unicode(job.getError()).encode("utf-8", "ignore"))
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
		for key, value in request.scalars.iteritems():
			job.addParameter(key, value)
		raise svcs.WebRedirect("async/"+job.jobId)

_JobActions.addAction(ParameterAction)

class PhaseAction(JobAction):
	name = "phase"

	def doPOST(self, job, request):
		newPhase = request.scalars.get("PHASE", None)
		if newPhase=="RUN":
			job.changeToPhase(uws.QUEUED)
		elif newPhase=="ABORT":
			job.changeToPhase(uws.ABORTED)
		else:
			raise base.ValidationError("Bad phase: %s"%newPhase, "phase")
		raise svcs.WebRedirect("async/"+job.jobId)
	
	def doGET(self, job, request):
		return UWS.makeRoot(UWS.phase[job.phase])
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
				self.name.upper(), repr(raw))))
		setattr(job, self.attName, val)
		raise svcs.WebRedirect("async/"+job.jobId)

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		return self.serializeValue(getattr(job, self.attName))


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
		request.setHeader("content-type", "text/xml")
		if job.quote is None:
			quote = ""
		else:
			quote = str(job.quote)
		return UWS.makeRoot(UWS.quote[quote])
	
_JobActions.addAction(QuoteAction)


class OwnerAction(JobAction):
	# we do not support auth yet, so this is a no-op.
	name = "owner"
	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		request.write("None")
		return ""

_JobActions.addAction(OwnerAction)
		

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

		# if that doesn't work, try to return some other file fromt the
		# job directory.  This is so we can deliver uploads.
		filePath = os.path.join(job.getWD(), *segments)
		if not os.path.exists(filePath):
			raise svcs.UnknownURI("File not found")
		return static.File(filePath)

	def doGET(self, job, request):
		baseURL = "%s/async/%s/results/"%(
			base.caches.getRD(tap.RD_ID).getById("run").getURL("tap"),
			job.jobId)
		return UWS.results[[
				UWS.result(id=res["resultName"], href=baseURL+res["resultName"])
			for res in job.getResults()]]

_JobActions.addAction(ResultsAction)


def _serializeTime(element, dt):
	if dt is None:
		return element(nil="true")
	return element[utils.formatISODT(dt)]


class RootAction(JobAction):
	"""Actions for async/jobId.
	"""
	name = ""
	def doDELETE(self, job, request):
		job.delete()
		raise svcs.WebRedirect("async")

	def doPOST(self, job, request):
		# (Extension to let web browser delete jobs)
		if utils.getfirst(request.args, "ACTION")=="DELETE":
			self.doDELETE(job, request)
		else:
			raise svcs.BadMethod("POST")


	def doGET(self, job, request):
		tree = UWS.makeRoot(UWS.job[
			UWS.jobId[job.jobId],
			UWS.runId[job.runId],
			UWS.ownerId(nil="true"),
			UWS.phase[job.phase],
			_serializeTime(UWS.startTime, job.startTime),
			_serializeTime(UWS.endTime, job.endTime),
			UWS.executionDuration[str(job.executionDuration)],
			UWS.destruction[utils.formatISODT(job.destructionTime)],
			getParametersElement(job),
			UWS.results(),
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
# XXX TODO: This hardcodes TAP jobs.  Can we parametrize that instead?
	with tap.TAPJob.makeFromId(jobId) as job:
		return _JobActions.dispatch(action, job, request, segments)
