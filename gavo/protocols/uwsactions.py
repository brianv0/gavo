"""
UWS result documents.

These guys are defined through the schema uws-1.0.xsd.  We also deliver
links to locally hosted stylesheets for convenience.

Instead of returning XML, they can also raise WebRedirect exceptions.  However,
these are caught in JobResource._redirectAsNecessary and appended to
the base URL auf the TAP service, so you must only give URIs relative
to the TAP service's root URL.
"""

from __future__ import with_statement

from gavo import svcs
from gavo import utils
from gavo.protocols import uws
from gavo.utils import stanxml
from gavo.utils import ElementTree


UWSNamespace = 'http://www.ivoa.net/xml/UWS/v1.0rc3'
XlinkNamespace = "http://www.w3.org/1999/xlink"
ElementTree._namespace_map[UWSNamespace] = "uws"
ElementTree._namespace_map[XlinkNamespace] = "xlink"


class UWS(object):
	"""the container for elements from the uws namespace.
	"""
	class UWSElement(stanxml.Element):
		namespace = UWSNamespace

	@staticmethod
	def makeRoot(ob):
		ob.a_xsi_schemaLocation = "%s %s %s %s"%(
			UWSNamespace, stanxml.schemaURL("uws-1.0.xsd"),
			XlinkNamespace, stanxml.schemaURL("xlink.xsd"))
		ob.xsi_schemaLocation_name = "xsi:schemaLocation"
		ob.a_xmlns_xsi = stanxml.XSINamespace
		ob.xmlns_xsi_name = "xmlns:xsi"
		return ob

	class NillableMixin(object):
		mayBeEmpty = True
		a_nil = None
		nil_name = "xsi:nil"


	class job(UWSElement): pass
	class jobs(UWSElement): pass
	class parameters(UWSElement): pass

	class destruction(UWSElement): pass
	class endTime(UWSElement, NillableMixin): pass
	class executionDuration(UWSElement): pass
	class jobId(UWSElement): pass
	class jobInfo(UWSElement): pass
	class message(UWSElement): pass
	class ownerId(UWSElement, NillableMixin): pass
	class phase(UWSElement): pass
	class quote(UWSElement): pass
	class runId(UWSElement): pass
	class startTime(UWSElement, NillableMixin): pass
	
	class detail(UWSElement):
		a_href = None
		a_type = None
		href_name = "xlink:href"
		type_name = "xlink:type"
	
	class errorSummary(UWSElement):
		type = None  # transient | fatal

	class jobref(UWSElement):
		a_id = None
		a_href = None
		a_type = None
		href_name = "xlink:href"
		type_name = "xlink:type"

	class parameter(UWSElement):
		a_byReference = None
		a_id = None
		a_isPost = None

	class result(UWSElement):
		mayBeEmpty = True
		a_id = None
		a_href = None
		a_type = None
		href_name = "xlink:href"
		type_name = "xlink:type"

	class results(UWSElement):
		mayBeEmpty = True

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
	return result.render()


class _JobActions(object):
	"""a collection of "actions" performed on UWS jobs.

	These correspond to the resources specified in the UWS spec.

	It is basically a dispatcher to JobAction instances which are added
	through the addAction method.
	"""
	actions = {}

	@classmethod
	def addAction(cls, actionClass):
		cls.actions[actionClass.name] = actionClass()

	@classmethod
	def dispatch(cls, action, job, request):
		try:
			resFactory = cls.actions[action]
		except KeyError:
			raise svcs.UnknownURI("Invalid UWS action '%s'"%action)
		return resFactory.getResource(job, request)
		

class JobAction(object):
	"""an action done to a job.

	It is defines methods do<METHOD> that are dispatched through JobActions.

	It must have a name corresponding to the child resource names from
	the UWS spec.
	"""
	name = None

	def getResource(self, job, request):
		try:
			handler = getattr(self, "do"+request.method)
		except AttributeError:
			raise svcs.BadMethod(request.method)
		return handler(job, request)


class PhaseAction(JobAction):
	name = "phase"

	def doPOST(self, job, request):
		mustBeRUN = svcs.getfirst(request, "PHASE", "<not given>")
		if mustBeRUN=="RUN":
			job.changeToPhase(uws.EXECUTING)
		else:
			raise uws.UWSError("Invalid PHASE value %s"%mustBeRun,
				job.jobId)
		print ">>>>>>Redirect to parent", dir(request)
	
	def doGET(self, job, request):
		return UWS.makeRoot(UWS.phase[job.phase])
_JobActions.addAction(PhaseAction)


class _DateSettableAction(JobAction):
	"""Abstract base for ExecDAction and DestructionAction.
	"""
	def doPOST(self, job, request):
		try:
			val = parseISODT(svcs.getfirst(request, self.name.upper()))
		except ValueError:
			raise uws.UWSError("Invalid %s value."%self.name.upper())
		setattr(job, self.attName, val)

	def doGET(self, job, request):
		request.setHeader("content-type", "text/plain")
		return getattr(job, self.attName)

class ExecDAction(_DateSettableAction):
	name = "executionduration"
	attName = 'executionDuration '
_JobActions.addAction(ExecDAction)

class DestructionAction(_DateSettableAction):
	name = "destruction"
	attName = "destructionTime"
_JobActions.addAction(DestructionAction)


class QuoteAction(JobAction):
	name = "quote"
	def doGET(self, job, request):
		return UWS.makeRoot(UWS.quoteRoot[job.quote])
_JobActions.addAction(QuoteAction)


class RootAction(JobAction):
	name = ""
	def doDELETE(self, job, request):
		job.delete()
		raise svcs.WebRedirect("async")
	
	def doGET(self, job, request):
		return UWS.makeRoot(UWS.job[
			UWS.jobId[job.jobId],
			UWS.runId[job.runId],
			UWS.ownerId(nil="true"),
			UWS.phase[job.phase],
			UWS.startTime(nil="true"),
			UWS.endTime(nil="true"),
			UWS.executionDuration[str(job.executionDuration)],
			UWS.destruction[job.destructionTime.isoformat()],
			UWS.results()]).render()
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
	if segments:
		raise svcs.UnknownURI("Too many segments")
	with uws.makeFromId(jobId) as job:
		return _JobActions.dispatch(action, job, request)
