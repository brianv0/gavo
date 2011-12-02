"""
Support classes for the universal worker service.
"""

# TODO: make all jobs R/O by default, and use context managers to let
# people obtain manipulators:
# job = UWSJob()
# with job.getManipulator() as man:
#   man.changeToPhase(uws.ABORTED)
# or somesuch.
# Scrap the horrible getWritable() hack when done.


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
from gavo.base import config
from gavo.base import cron

RD_ID = "__system__/uws"

# Ward against typos
from gavo.votable.tapquery import (PENDING, QUEUED, EXECUTING, COMPLETED,
	ERROR, ABORTED, UNKNOWN)
DESTROYED = "DESTROYED"  # local extension

END_STATES = set([DESTROYED, COMPLETED, ERROR, ABORTED])

# used in the computation of quote
EST_TIME_PER_JOB = datetime.timedelta(minutes=10)

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


@utils.memoized
def getROJobsTable():
	"""returns a UWS jobs table instance only intended for reading.

	If you write to what you get back, that's a bug (though we don't
	enforce anything right now).

	Use getJobsTable if you need to write to the jobs table.
	"""
	jobsTableConnection = base.getDBConnection("trustedquery", 
		autocommitted=True)
	return rsc.TableForDef(base.caches.getRD(RD_ID).getById("jobs"), 
		connection=jobsTableConnection)


def getJobsTable(timeout=None):
	"""returns a "writable" job table.

	Use this function to if you need to manipulate the jobs table.  You
	can use getROJobsTable if you only read.

	This will open a new connection every time.  Since this is an exclusive
	table, "automatic" selects will block each other.  In this way, there
	can always be only one UWSJob instance in memory for each job.

	timeout, if given, specifies after how many seconds the machine should
	give up when waiting for another instance to give up a lock on
	a job.  If not given, 60 seconds are used.
	"""
	conn = base.getDBConnection("admin")
	q = base.SimpleQuerier(connection=conn)
	if timeout is not None:
		q.configureConnection([("statement_timeout", int(timeout*1000))])
	jobsTable = rsc.TableForDef(base.caches.getRD(RD_ID).getById("jobs"), 
		connection=conn, exclusive=True, create=False)
	# jobsTable really has an owned connection.  Make it realize this.
	jobsTable.ownedConnection = True

	def jobsQuery(*args, **kwargs):
		try:
			return jobsTable.__class__.query(jobsTable, *args, **kwargs)
		except base.QueryCanceledError:
			raise base.ReportableError("Could not access the jobs table."
				" This probably means there is a stale lock on it.  Please"
				" notify the service operators.")
	jobsTable.query = jobsQuery

	return jobsTable

def countRunningJobs():
	"""returns the number of EXECUTING jobs in the jobsTable.
	"""
	return getROJobsTable().query("SELECT COUNT(*) FROM \curtable"
		" WHERE phase='EXECUTING' or phase='UNKNOWN'").next()[0]

def countQueuedJobs():
	"""returns the number of QUEUED jobs in jobsTable.
	"""
	return getROJobsTable().query("SELECT COUNT(*) FROM \curtable"
		" WHERE phase='QUEUED'").next()[0]


def serializeParameters(data):
	"""returns a base64-encoded version of a pickle of data
	"""
	# data should only contain strings, and I'm forcing them all to
	# be shorter than 50k; this should ward off broken clients that 
	# might push in files as "harmless" parameters while not actually
	# discarding actual queries.  Let's put in a warning nevertheless
	# XXX TODO: parse parameters in a way such that we catch/weed out
	# malformed uploads somewhere else and remove that limit here.
	for key in data.keys():
		if isinstance(data[key], basestring) and len(data[key])>50000:
			base.ui.notifyWarning("UWS Parameter %s discarded as too long; first"
				" bytes: %s"%(key, repr(data[key][:20])))
			del data[key]
	return pickle.dumps(data, 1).encode("base64")


def deserializeParameters(serData):
	"""does the inverse of serializeParameters.
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

	Methods you must override:

		- addParam(value, job) -> None -- parse value and perform some action
			(typically, set an attribute) on job.
		- getParam(job) -> string -- infer a string representation of the
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
	"""A ProtocolParameter for writing to parsed job attributes.

	It looks at the _serialize, _deserialize, and _destAttr attributes
	to figure out what to do.

	All this is nonsense, and I'm pretty sure all these should simply
	become members of the parameters dictionary.
	"""
	name = None

	@classmethod
	def addParam(cls, value, job):
		return setattr(job, cls._destAttr, cls._deserialize(value))
	
	@classmethod
	def getParam(cls, job):
		return cls._serialize(getattr(job, cls._destAttr))


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
	"""A container for the protocol parameters of a UWS job.

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

		This really is supposed to be called by UWSJob.xParam exclusively.
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


class ROUWSJob(object):
	"""A UWS job you cannot manipulate.

	This is a service mainly for GET-type functionality in the web interface.

	These jobs do not lock, and they may be arbitrarily out of date.
	They're much faster to instanciate, though, since no connection
	creation or such is involved.

	If you have one of those, you can get a writable version of it using

	with job.getWritable() as wjob:
		<stuff>
	
	Note that job will not get updated automatically after stuff.

	The RO/rest-mess currently make inheritance a huge pain, since you'll
	need to make an R/O and a writable version for each type of UWS job
	there is.  I'll think about that when I want to support more types
	of UWS jobs.
	"""
	_dbAttrs = ["jobId", "phase", "runId", "executionDuration",
		"destructionTime", "owner", "actions", "pid", "startTime", "endTime"]
	_closed = True

	protocolParameters = UWSParameters((), DestructionParameter,
		ExecDParameter, RunIdParameter)

# XXX TODO: passing in a jobs table in this way probably makes no
# sense.  Remove that soon.
	def __init__(self, jobId, jobsTable=None):
		self.jobId = jobId
		self.jobsTable = jobsTable
		if self.jobsTable is None:
			self.jobsTable = getROJobsTable()
		self._updateFromDB(jobId)
		self._closed = False

	def _updateFromDB(self, jobId):
		res = list(self.jobsTable.iterQuery(
			self.jobsTable.tableDef, "jobId=%(jobId)s",
			pars={"jobId": jobId}))
		if not res:
			self._closed = True
			raise JobNotFound(jobId)
		kws = res[0]

		for att in self._dbAttrs:
			setattr(self, att, kws[att])
		self.parameters = deserializeParameters(kws["parameters"])

	@classmethod
	def makeFromId(cls, jobId):
		return cls(jobId)

# XXX TODO: this shouldn't be a context manager.  Is this used
# anywhere?
	def __enter__(self):
		return self
	
	def __exit__(self, type, value, tb):
		pass

	def getWritable(self, timeout=10):
		return UWSJob.makeFromId(self.jobId, timeout=timeout)

	def getWD(self):
		return os.path.join(base.getConfig("uwsWD"), self.jobId)

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

	def getError(self):
		"""returns a dictionary having type, msg and hint keys for an error.

		If no error has been posted, a ValueError is raised.
		"""
		try:
			with open(os.path.join(self.getWD(), "__EXCEPTION__")) as f:
				return pickle.load(f)
		except IOError:
			raise ValueError(
				"No error has been posted on UWS job %s"%self.jobId)

	# results management: We use a pickled list in the jobs dir to manage 
	# the results.  I once had a table of those in the DB and it just
	# wasn't worth it.  One issue, though: this potentially races
	# if two different processes/threads were to update the results
	# at the same time.  With TAP, implementation semantics prevent
	# that.
	# 
	# The list contains dictionaries having resultName and resultType keys.
	@property
	def _resultsDirName(self):
		return os.path.join(self.getWD(), "__RESULTS__")

	def _loadResults(self):
		try:
			with open(self._resultsDirName) as f:
				return pickle.load(f)
		except IOError:
			return []

	def _saveResults(self, results):
		handle, srcName = tempfile.mkstemp(dir=self.getWD())
		with os.fdopen(handle, "w") as f:
			pickle.dump(results, f)
		# The following operation will bomb on windows when the second
		# result is saved.  Tough luck.
		os.rename(srcName, self._resultsDirName)

	def _addResultInJobDir(self, mimeType, name):
		resTable = self._loadResults()
		resTable.append(
			{'resultName': name, 'resultType': mimeType})
		self._saveResults(resTable)

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
		self._addResultInJobDir(mimeType, name)

	def openResult(self, mimeType, name):
		"""returns a writable file that adds a result.
		"""
		self._addResultInJobDir(mimeType, name)
		return open(os.path.join(self.getWD(), name), "w")

	def getResult(self, resName):
		"""returns a pair of file name and mime type for a named job result.

		If the result does not exist, a NotFoundError is raised.
		"""
		res = [r for r in self._loadResults() if resName==r["resultName"]]
		if not res:
			raise base.NotFoundError(resName, "job result",
				"uws job %s"%self.jobId)
		res = res[0]
		return os.path.join(self.getWD(), res["resultName"]), res["resultType"]

	def getResults(self):
		"""returns a list of this service's results.

		The list contains dictionaries having at least resultName and resultType
		keys.
		"""
		return self._loadResults()

	def openFile(self, name, mode="r"):
		"""returns an open file object for a file within the job's work directory.

		No path parts are allowed on name.
		"""
		if "/" in name:
			raise ValueError("No path components allowed on job files.")
		return open(os.path.join(self.getWD(), name), mode)

	@property
	def quote(self):
		"""returns an estimation of the job completion.

		This currently is very naive: we give each job that's going to run
		before this one 10 minutes.

		This method needs to be changed when the dequeueing algorithm
		is changed.
		"""
		nBefore = self.jobsTable.query("select count(*) from \curtable where"
			" phase='QUEUED' and destructionTime<=%(dt)s",
			{"dt": self.destructionTime}).next()[0]
		return datetime.datetime.utcnow()+nBefore*EST_TIME_PER_JOB


class UWSJob(ROUWSJob):
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

	To create a new UWSJob, use one of the create* class methods, to get
	one from an id, use makeFromId.  The normal constructor is not really
	intended for user consumption.

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
	_dbAttrs = ["jobId", "phase", "runId", "executionDuration",
		"destructionTime", "owner", "actions", "pid", "startTime", "endTime"]
	_closed = True

	def __init__(self, jobId, jobsTable=None, timeout=10):
		if jobsTable is None:
			jobsTable = getJobsTable(timeout)
		# the following is a counter for the number of times __enter__
		# has been called.  This is to accomodate the stupid way we
		# manage our context with nested uses of with
		self.nestingDepth = 0
		ROUWSJob.__init__(self, jobId, jobsTable)

	@classmethod
	def makeFromId(cls, jobId, timeout=10):
		return cls(jobId, timeout=timeout)

	@classmethod
	def _allocateDataDir(cls):
		uwsWD = base.getConfig("uwsWD")
		utils.ensureDir(uwsWD, mode=0775, setGroupTo=config.getGroupId())
		jobDir = tempfile.mkdtemp("", "", dir=uwsWD)
		return os.path.basename(jobDir)

	@classmethod
	def create(cls, args={}, **kws):
		"""creates a new job from a (partial) jobs table row.

		See jobs table for what you can give in kws, except for parameters.
		These are passed in as a dictionary args.  jobId and phase are 
		always overridden, many other colums will fill in defaults if necessary.
		"""
		timeout = kws.pop("timeout", 20)
		kws["jobId"] = cls._allocateDataDir()
		kws["phase"] = PENDING
		kws["parameters"] = serializeParameters({})
		jobsTable = getJobsTable(timeout=timeout)
		utils.addDefaults(kws, {
			"executionDuration": base.getConfig("async", "defaultExecTime"),
			"destructionTime": datetime.datetime.utcnow()+datetime.timedelta(
					seconds=base.getConfig("async", "defaultLifetime")),
			"quote": None,  # see below in _persist
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
		try:
			for key, value in args.iteritems():
				res.addParameter(key, value)
		except:
			# if a bad parameter was used to create the job, kill it right away
			res.delete()
			res.close()
			raise
		return res

	@classmethod
	def createFromRequest(cls, request, actions="TAP"):
		"""creates a new job from something like a nevow request.

		request is something implementing nevow.IRequest, actions is the
		name (i.e., a string) of a registred Actions class.
		"""
		return cls.create(args=request.scalars, actions=actions)

	def __del__(self):
		# if a job has not been closed, commit it (this may be hiding programming
		# errors, though -- should we rather roll back?)
		if self.jobsTable is not None and not self._closed:
			self.close()

	def __enter__(self):
		self.nestingDepth += 1
		return self # transaction has been opened by makeFromId
	
	def __exit__(self, type, value, tb):
		# we want to release the jobs table no matter what, but we don't 
		# claim to handle any exception.
		self.nestingDepth -= 1
		if self.nestingDepth==0:
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

	def getWritable(self, timeout=10):
		return self

	def addParameter(self, name, value):
		self.protocolParameters.addParam(self, name, value)

	def _persist(self):
		"""updates or creates the job in the database table.
		"""
		if self._closed:
			raise ValueError("Cannot persist closed UWSJob")
		dbRec = self.getAsDBRec()
		# artifically add quote; we now compute this on the fly, but
		# I'd like to wait with a schema change until we refurbish the
		# whole UWS mess
		dbRec["quote"] = None
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
				if newPhase!=ERROR:
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
		errInfo = {
			"type": exception.__class__.__name__,
			"msg": unicode(exception),
			"hint": getattr(exception, "hint", None),
		}
		with open(os.path.join(self.getWD(), "__EXCEPTION__"), "w") as f:
			pickle.dump(errInfo, f)


def cleanupJobsTable(includeFailed=False, includeCompleted=False,
		includeAll=False, includeForgotten=False):
	"""removes expired jobs from the UWS jobs table.

	The uws service arranges for this to be called roughly once a day.
	The functionality is also exposed through gavo admin cleanuws; this
	also lets you use the includeFailed and includeCompleted flags.  These
	should not be used on production services since you'd probably nuke
	jobs still interesting to your users.
	"""
	phasesToKill = set()
	if includeFailed or includeAll:
		phasesToKill.add(ERROR)
		phasesToKill.add(ABORTED)
	if includeCompleted or includeAll:
		phasesToKill.add(COMPLETED)
	if includeAll:
		phasesToKill.add(PENDING)
		phasesToKill.add(QUEUED)
	if includeForgotten:
		phasesToKill.add(PENDING)

	toDestroy = []
	now = datetime.datetime.utcnow()
	jt = getJobsTable(timeout=10)

	try:
		for row in jt.iterQuery(jt.tableDef, ""):
			if row["destructionTime"]<now:
				toDestroy.append(row["jobId"])
			elif row["phase"] in phasesToKill:
				toDestroy.append(row["jobId"])
	finally:
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


# XXX TODO: These should be called transistionFunctions or so to tell them
# apart from the uwsactions (which are REST manipulations).
class UWSActions(object):
	"""An abstract base for classes defining the behaviour of a UWS.

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
		for phase in [PENDING, QUEUED, EXECUTING, ERROR, ABORTED, COMPLETED,
				DESTROYED]:
			self.transitions.setdefault(phase, {})[ERROR] = "flagError"
			self.transitions.setdefault(phase, {})[DESTROYED] = "noOp"
		for fromPhase, toPhase, methodName in vertices:
			self.transitions.setdefault(fromPhase, {})[toPhase] = methodName
	
	def getTransition(self, fromPhase, toPhase):
		if (fromPhase==toPhase or
				fromPhase in END_STATES):
			# ignore null or ignorable transitions
			return lambda p, job, input: None
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
			base.ui.notifyError("Error during UWS execution of job %s"%job.jobId)
		job.setError(exception)
	
	def checkProcessQueue(self):
		"""should push processes from the queue to executing.

		The default is a no-op, so it must be overridden unless you don't
		actually use queuing.
		"""
		pass

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
