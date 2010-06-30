"""
Support classes for the universal worker service.
"""

from __future__ import with_statement

import cPickle as pickle
import datetime
import itertools
import os
import shutil
import tempfile

from twisted.python import log

from gavo import base
from gavo import rsc
from gavo import utils
from gavo.base import cron

RD_ID = "__system__/uws"

# Ward against typos
from gavo.votable.tapquery import (PENDING, QUEUED, EXECUTING, COMPLETED,
	ERROR, ABORTED)
DESTROYED = "DESTROYED"  # local extension

class UWSError(base.Error):
	def __init__(self, msg, jobId, hint=None):
		base.Error.__init__(self, msg, hint)
		self.args = [msg, jobId, hint]
		self.msg = msg
		self.jobId = jobId

	def __str__(self):
		return "Error in processing job %s: %s"%(self.jobId, self.msg)


class JobNotFound(base.NotFoundError, UWSError):
	def __init__(self, jobId):
		base.NotFoundError.__init__(self, str(jobId), "UWS job", "jobs table")
	
	def __str__(self):
		return base.NotFoundError.__str__(self)


# So, this is the first instance where an ORM might actually be nice.
# But, aw, I'm not pulling in SQLAlchemy just yet.


def getJobsTable(timeout=None):
	"""returns an instanciated job table.

	This will open a new connection every time.  Since this is an exclusive
	table, "automatic" selects will block each other.  In this way, there
	can always be only one UWSJob instance in memory for each job.

	timeout, if given, specifies after how many seconds the machine should
	give up when waiting for another instance to give up a lock on
	a job.
	"""
	conn = base.getDBConnection("admin")
	q = base.SimpleQuerier(connection=conn)
	if timeout is not None:
		q.configureConnection([("statement_timeout", timeout*1000)])
	jobsTable = rsc.TableForDef(base.caches.getRD(RD_ID).getById("jobs"), 
		connection=conn, exclusive=True)
	# jobsTable really has an owned connection.  Make it realize this.
	jobsTable.ownedConnection = True
	return jobsTable


def serializeParameters(data):
	"""returns a base64-encoded version of a pickle of data
	"""
	# data should only contain strings, and I'm forcing them all to
	# be shorter than 1k; this should ward off broken clients that 
	# might push in files as "harmless" parameters.
	for key in data.keys():
		if isinstance(data[key], basestring) and len(data[key])>1000:
			del data[key]
	return pickle.dumps(data, 1).encode("base64")


def deserializeParameters(serData):
	"""does the inverse of serializedData.
	"""
	return pickle.loads(serData.decode("base64"))


class ParameterRef(object):
	"""A reference to a UWS parameter.

	This always contains a URL.  In case of uploads, the tap renderer makes
	sure the upload is placed into the upload directory and generates a
	URL; in that case, local is True.
	"""
	def __init__(self, url, local=False):
		self.local = local
		self.url = url


class ProtocolParameter(object):
	"""A UWS protocol parameter.

	All methods of these are class methods since ProtocolParameters are 
	never instanciated.

	Methods:

	* addParam(value, job) -> None -- parse value and perform some action
	  (typically, set an attribute) on job.
	* getParam(job) -> string -- infer a string representation of the
	  protocol parameter on job.

	The default implementation just dumps/gets name from the job's
	parameters dict.
	"""
	name = None
	_deserialize, _serialize = str, str

	@classmethod
	def addParam(cls, value, job):
		assert cls.name is not None
		job.parameters[cls.name] = cls._deserialize(value)

	@classmethod
	def getParam(cls, job):
		return cls._serialize(job.parameters[cls.name])


class SerializingProtocolParameter(ProtocolParameter):
	"""is a ProtocolParameter for writing to parsed job attributes.

	It looks at the _serialize, _deserialize, and _destAttr attributes
	to figure out what to do.
	"""
	name = None

	@classmethod
	def addParam(cls, value, job):
		return getattr(job, cls._deserialize(cls._destAttr))
	
	@classmethod
	def getParam(cls, job):
		return setattr(job, cls._destAttr, cls._serialize(value))


class DestructionParameter(SerializingProtocolParameter):
	name = "DESTRUCTION"
	_serialize, _deserialize, _destAttr = \
		utils.formatISODT, utils.parseISODT, "destructionTime"


class ExecDParameter(SerializingProtocolParameter):
	name = "EXECUTIONDURATION"
	_serialize, _deserialize, _destAttr = \
		str, int, "executionDuration"


class RunIdParameter(SerializingProtocolParameter):
	name = "RUNID"

	_serialize, _deserialize, _destAttr = \
		str, str, "runId"


class UWSParameters(object):
	"""A container for the protocol parameters of an UWS job.

	UWSJobs have a protocolParameters class attribute containing this.
	"""
	def __init__(self, base, *parameters):
		self.paramClasses = {}
		for par in itertools.chain(base, parameters):
			self._addParamClass(par)

	def __iter__(self):
		for p in self.paramClasses.values():
			yield p

	def _addParamClass(self, par):
		self.paramClasses[par.name.upper()] = par
	
	def addParam(self, job, name, value):
		"""adds a name/value pair to the job's parameters.

		This is really supposed to be called by UWSJob.xParam, so don't bother.
		"""
		if name.upper() in self.paramClasses:
			self.paramClasses[name.upper()].addParam(value, job)
		else:
			job.parameters[name] = value

	def getParam(self, job, name):
		if name.upper() in self.paramClasses:
			return self.paramClasses[name.upper()].getParam(job)
		else:
			return job.parameters[name]


class UWSJob(object):
	"""A job description within UWS.

	This keeps most of the data on a Worker.  Constructing these
	is relatively expensive (in incurs constructing a DBTable, opening
	a database connection, and doing a query).  On the other hand,
	these things only need to be touched a couple of times during the
	lifetime of a job, or to answer polls, and for those, other operations
	are at least as expensive.

	The DB takes care of avoiding races in status changes.  getJobsTable
	above opens the jobs table in exclusive mode, whereas construction here
	always opens a transaction.  This means that other processes accessing
	the row will block.

	UWSJobs should only be used as context managers to make sure the
	transactions are closed in time.

	To create a new UWSJob, use the create class method.  It is called
	with a nevow request object and the name of an Actions object
	(see below).

	In general, you should not access the parameters dictionary directly, since
	the protocol parameters may do some processing.  Use addParameter,
	getParameter, delParameter, and iterParameters instead.

	Some of the items given in the UWS data model are actually kept in dataDir.

	The UWSJob itself is just a managing class.  The actual actions
	occurring on the phase chages are defined in the Actions object.
	"""
# Hm -- I believe things would be much smoother if locking happened
# in __enter__, and the rest would just keep instanciated.  Well,
# we can always clean this up later while keeping code assuming
# the current semantics working.
	_dbAttrs = ["jobId", "phase", "runId", "quote", "executionDuration",
		"destructionTime", "owner", "actions", "pid", "startTime", "endTime"]
	_closed = True

	protocolParameters = UWSParameters((), DestructionParameter,
		ExecDParameter)

	def __init__(self, jobId, jobsTable=None, timeout=None):
		self.jobId = jobId
		self.jobsTable = jobsTable
		if self.jobsTable is None:
			self.jobsTable = getJobsTable(timeout)

		res = list(self.jobsTable.iterQuery(
			self.jobsTable.tableDef, "jobId=%(jobId)s",
			pars={"jobId": jobId}))
		if not res:
			self._closed = True
			raise JobNotFound(jobId)
		self._closed = False
		kws = res[0]

		for att in self._dbAttrs:
			setattr(self, att, kws[att])
		self.parameters = deserializeParameters(kws["parameters"])

	@classmethod
	def _allocateDataDir(cls):
		jobDir = tempfile.mkdtemp("", "", base.getConfig("uwsWD"))
		return os.path.basename(jobDir)

	@classmethod
	def create(cls, args={}, **kws):
		"""creates a new job from a (partial) jobs table row.

		See jobs table for what you can give in kws, except for parameters.
		These are passed in as a dictionary args.  jobId and phase are 
		always overridden, many other colums will fill in defaults if necessary.
		"""
		kws["jobId"] = cls._allocateDataDir()
		kws["phase"] = PENDING
		kws["parameters"] = serializeParameters({})
		jobsTable = getJobsTable()
		utils.addDefaults(kws, {
			"quote": None,
			"executionDuration": base.getConfig("async", "defaultExecTime"),
			"destructionTime": datetime.datetime.utcnow()+datetime.timedelta(
					seconds=base.getConfig("async", "defaultLifetime")),
			"runId": None,
			"owner": None,
			"pid": None,
			"startTime": None,
			"endTime": None,
			"actions": "TAP",
		})
		jobsTable.addRow(kws)

		# The following commit is really important so we can keep track
		# of job directories in the DB even if user code crashes before
		# commiting.
		jobsTable.commit()

		# Can't race for jobId here since _allocateDataDir uses mkdtemp
		res = cls(kws["jobId"], jobsTable)
		for key, value in args.iteritems():
			res.addParameter(key, value)
		return res

	@classmethod
	def createFromRequest(cls, request, actions="TAP"):
		"""creates a new job from something like a nevow request.

		request is something implementing nevow.IRequest, actions is the
		name (i.e., a string) of a registred Actions class.
		"""
		# XXX TODO: Allow UPLOAD spec in initial POST?
		return cls.create(args=request.scalars, actions=actions)
	
	@classmethod
	def makeFromId(cls, jobId, timeout=None):
		return cls(jobId, timeout=timeout)

	def __del__(self):
		# if a job has not been closed, commit it (this may be hiding programming
		# errors, though -- should we rather roll back?)
		if self.jobsTable is not None and not self._closed:
			self.close()

	def __enter__(self):
		return self # transaction has been opened by makeFromId
	
	def __exit__(self, type, value, tb):
		# we want to persist no matter what, but we don't claim to handle
		# any exception.
		self.close()
		if tb is not None: # exception came in, signal we did not handle it.
			return False

	def close(self):
		if self._closed:  # allow multiple closing
			return
		self._persist()
		self.jobsTable.commit()
		self.jobsTable.close()
		self._closed = True

	def getWD(self):
		return os.path.join(base.getConfig("uwsWD"), self.jobId)

	def addParameter(self, name, value):
		self.protocolParameters.addParam(self, name, value)

	def getParameter(self, name):
		return self.protocolParameters.getParam(self, name)

	def iterParameters(self):
		for name in self.parameters:
			yield name, self.getParameter(name)

	def getAsDBRec(self):
		"""returns self's representation in the jobs table.
		"""
		res = dict((att, getattr(self, att)) for att in self._dbAttrs)
		res["parameters"] = serializeParameters(self.parameters)
		return res

	def addResult(self, source, mimeType, name=None):
		"""adds a result, with data taken from source.

		source may be a file-like object or a byte string.

		If no name is passed, a name is auto-generated.
		"""
		if name is None:
			name = utils.intToFunnyName(id(source))
		with open(os.path.join(self.getWD(), name), "w") as destF:
			if isinstance(source, baseString):
				destF.write(source)
			else:
				utils.cat(source, destF)
		self._addResultToTable(mimeType, name)

	def openResult(self, mimeType, name):
		"""returns a writable file that adds a result.
		"""
		self._addResultToTable(mimeType, name)
		return open(os.path.join(self.getWD(), name), "w")

	def _addResultToTable(self, mimeType, name):
		resTable = rsc.TableForDef(base.caches.getRD(RD_ID).getById("results"),
			connection=self.jobsTable.connection)
		resTable.addRow(
			{'jobId': self.jobId, 'resultName': name, 'resultType': mimeType})
		resTable.commit()
		resTable.close()

	def getResult(self, resName):
		"""returns a pair of file name and mime type for a named job result.

		If the result does not exist, a NotFoundError is raised.
		"""
		res = self.getResults("resultName=%(resultName)s", {"resultName": resName})
		if not res:
			raise base.NotFoundError(resName, "job result",
				"uws job %s"%self.jobId)
		res = res[0]
		return os.path.join(self.getWD(), res["resultName"]), res["resultType"]

	def getResults(self, addFragment=None, addPars={}):
		"""returns a list of this service's results.

		The list contains (dict) records from uws.results.
		"""
		resTable = rsc.TableForDef(base.caches.getRD(RD_ID).getById("results"),
			connection=self.jobsTable.connection)
		fragment = "jobId=%(jobId)s"
		pars={"jobId": self.jobId}
		if addFragment:
			fragment = fragment+" AND "+addFragment
			pars.update(addPars)
		results = list(resTable.iterQuery(resTable.tableDef, 
			fragment, pars=pars))
		resTable.close()
		return results

	def _persist(self):
		"""updates or creates the job in the database table.
		"""
		if self._closed:
			raise ValueError("Cannot persist closed UWSJob")
		dbRec = self.getAsDBRec()
		if self.phase==DESTROYED:
			self.jobsTable.deleteMatching("jobId=%(jobId)s", dbRec)
		else:
			self.jobsTable.addRow(dbRec)

	def delete(self):
		"""removes all traces of the job from the system.
		"""
		try:
			self.changeToPhase(DESTROYED, None)
		except (base.ValidationError, base.NotFoundError):
			# silently ignore failures in transitioning here
			pass                       
		# Should we check whether destruction actions worked?
		self.phase = DESTROYED
		shutil.rmtree(self.getWD(), ignore_errors=True)
	
	def changeToPhase(self, newPhase, input=None):
		"""pushes to job to a new phase, if allowed by actions
		object.
		"""
		try:
			return getActions(self.actions).getTransition(
				self.phase, newPhase)(newPhase, self, input)
		except Exception, exception:
			# transition to error if possible.  If that fails at well,
			# blindly set error and give up.
			try:
				return self.changeToPhase(ERROR, exception)
			except:
				self.setError(exception)
				self.phase = ERROR
			raise exception

	def setError(self, exception):
		"""sets exception as the job's error.

		Exception will be pickled and can be retrieved by getError.
		Setting the error will not transition the job to ERROR;
		it is generally assumed that this method is called in actions
		transitioning there.
		"""
# Currently, this should be called exclusively by changeToPhase.
# When and if we make error behaviour overrideable, this actually
# makes sense as a user-exposed method.
		with open(os.path.join(self.getWD(), "__EXCEPTION__"), "w") as f:
			pickle.dump(exception, f)
	
	def getError(self):
		"""returns an exception object previously set by setError.

		If no error has been posted, a ValueError is raised.
		"""
		try:
			with open(os.path.join(self.getWD(), "__EXCEPTION__")) as f:
				return pickle.load(f)
		except IOError:
			raise base.ui.logOldExc(ValueError(
				"No error has been posted on UWS job %s"%self.jobId))

	def openFile(self, name, mode="r"):
		"""returns an open file object for a file within the job's work directory.

		No path parts are allowed on name.
		"""
		if "/" in name:
			raise ValueError("No path components allowed on job files.")
		return open(os.path.join(self.getWD(), name), mode)


def cleanupJobsTable():
	toDestroy = []
	now = datetime.datetime.utcnow()
	jt = getJobsTable(timeout=10)
	for row in jt.iterQuery(jt.tableDef, ""):
		if row["destructionTime"]<now:
			toDestroy.append(row["jobId"])
	jt.close()
	for jobId in toDestroy:
		try:
			with UWSJob.makeFromId(jobId, timeout=5) as job:
				job.delete()
		except base.QueryCanceledError: # job locked by something, don't hang
			base.ui.notifyWarning("Postponing destruction of %s: Locked"%
				jobId)
			pass


cron.every(3600*12, cleanupJobsTable)


class UWSActions(object):
	"""An abstract base for classes defining the behaviour of an UWS.

	This basically is the definition of a finite state machine with
	arbitrary input (which is to say: the input "alphabet" is up to
	the transitions).
	
	UWSActions need to be defined for every service you want exposed.
	They must be named.  An instance of each class is stored in this
	module and can be accessed using the getActions method.

	The main interface to UWSActions is getTransition(p1, p2) -> callable
	It returns a callable that should push the automaton from phase p1
	to phase p2 or raise an ValidationError for a field phase.  The
	default implementation should work.

	The callable has the signature f(desiredPhase, uwsJob, input) -> None.
	It must alter the uwsJob object as appropriate.  input is some object
	defined by the the transition.

	The transitions are implemented as simple methods having the signature
	of the callables returned by getTransition.  
	
	To link transistions and methods, pass a vertices list to the constructor.
	This list consists of 3-tuples of strings (from, to, method-name).  From and
	to are phase names (use the symbols from this module to ward against typos).

	When transitioning to DESTROYED, you do not need to remove the job's
	working directory or the jobs table entry.  Therefore typically, the
	COMPLETED to DESTROYED is a no-op for UWSActions.

	"""
	def __init__(self, name, vertices):
		self.name = name
		self._buildTransitions(vertices)
	
	def _buildTransitions(self, vertices):
		self.transitions = {}
		# set some defaults
		for phase in [PENDING, QUEUED, EXECUTING, ERROR, ABORTED]:
			self.transitions.setdefault(phase, {})[ERROR] = "flagError"
			self.transitions.setdefault(phase, {})[DESTROYED] = "noOp"
		for fromPhase, toPhase, methodName in vertices:
			self.transitions.setdefault(fromPhase, {})[toPhase] = methodName
	
	def getTransition(self, fromPhase, toPhase):
		try:
			methodName = self.transitions[fromPhase][toPhase]
		except KeyError:
			raise base.ui.logOldExc(
				base.ValidationError("No transition from %s to %s defined"
				" for %s Actions"%(fromPhase, toPhase, self.name),
				"phase", hint="This almost always points to an implementation error"))
		try:
			return getattr(self, methodName)
		except AttributeError:
			raise base.ui.logOldExc(
				base.ValidationError("%s Actions have no %s methods"%(self.name,
				methodName),
				"phase", hint="This is an error in an internal protocol definition."
				"  There probably is nothing you can do but complain."))

	def noOp(self, newPhase, job, ignored):
		"""a sample action just setting the new phase.

		This is a no-op baseline sometimes useful in user code.
		"""
		job.phase = newPhase

	def flagError(self, newPhase, job, exception):
		"""the default action when transitioning to an error: dump exception and
		mark phase as ACTION.
		"""
		job.phase = ERROR
		# Validation errors don't get logged -- for one, they probably
		# are the user's fault, and for a second, logging them upsets
		# trial during testing, since trial examines the log.
		if not isinstance(exception, base.ValidationError):
			log.err(_why="Error duing UWS execution of job %s"%job.jobId)
		job.setError(exception)

_actionsRegistry = {}


def getActions(name):
	try:
		return _actionsRegistry[name]
	except KeyError:
		raise base.ui.logOldExc(
			base.NotFoundError(name, "Actions", "registred Actions",
			hint="Either you just made up the UWS actions name, or the"
			" module defining these actions has not been imported yet."))


def registerActions(cls, *args, **kwargs):
	"""registers an Actions class.

	args and kwargs are arguments passed to cls's constructor.
	"""
	newActions = cls(*args, **kwargs)
	_actionsRegistry[newActions.name] = newActions
