"""
Support classes for the universal worker service.

This module contains the actual logic.  The UWS REST interface is dealt with
in web.uwsrest.
"""

import cPickle as pickle
import datetime
import os
import shutil
import tempfile

from gavo import base
from gavo import rsc
from gavo import utils

# So, this is the first instance where an ORM might actually be nice.
# But, aw, I'm not pulling in SQLAlchemy just yet.


RD_ID = "__system__/uws"

# Ward against typos
PENDING = "PENDING"
QUEUED = "QUEUED"
EXECUTING = "EXECUTING"
COMPLETED = "COMPLETED"
ERROR = "ERROR"
ABORTED = "ABORTED"
DESTROYED = "DESTROYED"  # local extension

@utils.memoized
def getJobsTable():
	conn = base.getDBConnection("admin")
	jobsTable = rsc.TableForDef(base.caches.getRD(RD_ID).getById("jobs"), 
		connection=conn)
	# jobsTable really has an owned connection.  So, let's override its
	# commit method
	jobsTable.commit = conn.commit
	return jobsTable


def getfirst(request, key):
	"""returns the first value for key if it's present in request.args, None
	otherwise.

	request must implement newow.IRequest.
	"""
	vals = request.args.get(key)
	if vals:
		return vals[0]


def serializeData(data):
	"""returns a base64-encoded version of a pickle of data
	"""
	return pickle.dumps(data, 1).encode("base64")

def deserializeData(serData):
	"""does the inverse of serializedData.
	"""
	return pickle.loads(serData.decode("base64"))


class UWSJob(object):
	"""A job description within UWS.

	These usually get serialized and deserialized from the uws.jobs table
	defined in __system__/uws.  The construction usually works by using a 
	row dict as keyword arguments.  See the RD of the meaning of the
	constructor arguments.
	
	To create a new UWSJob, use the create class method.  It is called
	with a nevow request object and the name of an Actions object
	(see below).

	Note that the parameters attribute isn't terribly useful.  Use
	getParDict/setParDict to work with it (this is probably a silly
	optimization).

	Some of the items given in the UWS data model are actually kept in dataDir.

	The UWSJob itself is just a managing class.  The actual actions
	occurring on the phase chages are defined in the Actions object.
	"""
# XXX TODO: We *probably* want to lock the jobsTable while we have
# an instance of UWSJob around (or at least the pertaining record)
# This requires an explicit cleanup.  Make this a ContextManager?
	_dbAttrs = ["jobid", "phase", "runId", "quote", "executionDuration",
		"destructionTime", "owner", "parameters", "actions"]

	def __init__(self, **kwargs):
		for att in self._dbAttrs:
			try:
				setattr(self, att, kwargs.pop(att))
			except KeyError:
				raise TypeError("UWSJob needs keyword argument %s"%(
					repr(att)))
		if kwargs:
			att, val = kwargs.popitem()
			raise TypeError("UWSJob got an unexpected keyword argument %s"%(
				repr(att)))

	@classmethod
	def _allocateDataDir(cls):
		jobDir = tempfile.mkdtemp("", "", base.getConfig("uwsWD"))
		return os.path.basename(jobDir)

	@classmethod
	def create(cls, request, actions):
		"""creates a new job.

		request is something implementing nevow.IRequest, actions is the
		name (i.e., a string) of a registred Actions class.
		"""
		newOb = cls(jobid=cls._allocateDataDir(),
			quote=None,
			executionDuration=base.getConfig("async", "defaultExecTime"),
			destructionTime=datetime.datetime.utcnow()+datetime.timedelta(
				seconds=base.getConfig("async", "defaultLifetime")),
			phase=PENDING,
			parameters = serializeData(request.args),
			runId=getfirst(request, "RUNID"),
			owner=None,
			actions=actions)
		newOb._persist()
		return newOb
	
	@classmethod
	def makeFromId(cls, jobid):
		jobsTable = getJobsTable()
		res = list(jobsTable.iterQuery(jobsTable.tableDef, "jobid=%(jobid)s",
			pars={"jobid": jobid}))
		if not res:
			raise base.NotFoundError(jobid, "UWS job", "jobs table")
		kws = dict((str(k), v) for k, v in res[0].iteritems())
		return cls(**kws)

	def getWD(self):
		return os.path.join(base.getConfig("uwsWD"), self.jobid)

	def getParDict(self):
		"""returns the current job parameter dictionary.
		"""
		return deserializeData(self.parameters)
	
	def setParDict(self, parDict):
		"""replaces the parameter dictionary with the argument.
		"""
		self.parameters = serializeData(parDict)

	def getAsDBRec(self):
		"""returns self's representation in the jobs table.
		"""
		return dict((att, getattr(self, att)) for att in self._dbAttrs)

	def _persist(self):
		"""updates or creates the job in the database table.
		"""
		dbRec = self.getAsDBRec()
		jobsTable = getJobsTable()
		jobsTable.deleteMatching("jobid=%(jobid)s", dbRec)
		if self.phase!=DESTROYED:
			jobsTable.addRow(dbRec)
		jobsTable.commit()
		jobsTable.query("BEGIN")

	def delete(self):
		"""removes all traces of the job from the system.
		"""
		try:
			self.changeToPhase("DESTROYED")
		except base.ValidationError: # actions don't want to do anything
			pass                       # no problem
		# Should we check whether destruction actions worked?
		self.phase = "DESTROYED"
		self._persist()
		shutil.rmtree(self.getWD(), ignore_errors=True)
	
	def changeDestructionTime(self, newDT):
		"""changes the destruction time.  newDT must be a datetime.datetime 
		instance.
		"""
		self.destructionTime = newDT
		self._persist()
	
	def changeExecutionDuration(self, newTime):
		"""changes the execution duration.  newTime must be an integer.
		"""
		self.executionDuration = newTime
		self._persist()
	
	def changeToPhase(self, newPhase):
		"""pushes to job to a new phase, if allowed by actions
		object.
		"""
		getActions(self.actions).getTransition(
			self.phase, newPhase)(newPhase, self)
		self._persist()


class UWSActions(object):
	"""An abstract base for classes defining the behaviour of an UWS.

	These need to be defined for every service you want exposed.
	They must be named.  An instance of each class is stored in this
	module and can be accessed using the getActions method.

	The main interface to UWSActions is getTransition(p1, p2) -> callable
	It returns a callable that should push the automaton from phase p1
	to phase p2 or raise an ValidationError for a phase field.  The
	default implementation should do.

	The callable has the signature f(desiredState, uwsJob) -> None.
	It must alter the uwsJob object as appropriate.

	To the transitions are implemented as simple methods having the signature
	of the callables returned by getTransition.  
	
	To link transistions and methods, pass a vertices list to the constructor.
	This list consists of 3-tuples of strings (from, to, method-name).  From and
	to are phase names (use the symbols from this module to ward against typos).

	When transitioning to DESTROYED, you do not need to remove the job's
	working directory or the jobs table entry.  Typically, a transition
	from COMPLETED to DESTROYED is a no-op.
	"""
	def __init__(self, name, vertices):
		self.name = name
		self._buildTransitions(vertices)
	
	def _buildTransitions(self, vertices):
		self.transitions = {}
		for fromPhase, toPhase, methodName in vertices:
			self.transitions.setdefault(fromPhase, {})[toPhase] = methodName
	
	def getTransition(self, fromPhase, toPhase):
		try:
			methodName = self.transitions[fromPhase][toPhase]
		except KeyError:
			raise base.ValidationError("No transition from %s to %s defined"
				" for %s Actions"%(fromPhase, toPhase, self.name),
				"phase", hint="This almost always points to an implementation error")
		try:
			return getattr(self, methodName)
		except AttributeError:
			raise base.ValidationError("%s Actions have no %s methods"%(self.name,
				methodName),
				"phase", hint="This is an error in an internal protocol definition."
				"  There probably is nothing you can do but complain.")


_actionsRegistry = {}

def getActions(name):
	try:
		return _actionsRegistry[name]
	except KeyError:
		raise NotFoundError(name, "Actions", "registred Actions",
			hint="Either you just made up the UWS actions name, or the"
			" module defining these actions has not been imported yet.")

def registerActions(cls, *args, **kwargs):
	"""registers an Actions class.

	args and kwargs are arguments passed to cls's constructor.
	"""
	newActions = cls(*args, **kwargs)
	_actionsRegistry[newActions.name] = newActions


create = UWSJob.create
makeFromId = UWSJob.makeFromId
