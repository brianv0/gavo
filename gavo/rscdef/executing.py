"""
The execute element and related stuff.
"""

import threading
import traceback

from gavo import base
from gavo.base import cron
from gavo.rscdef import common
from gavo.rscdef import procdef


class GuardedFunctionFactory(object):
	"""a class for making functions safe for cron-like executions.

	The main method is makeGuarded.  It introduces a lock protecting against
	double execution (if that would happen, the execution is suppressed with a
	warning; of course, if you fork something into the background, that mechanism
	no longer works). The stuff is run in a thread, and exceptions caught.  If
	anything goes wrong during execution, a mail is sent to the administrator.

	Note that, in contrast to cron, I/O is not captured (that would
	be difficult for threads; we don't want processes because of
	the potential trouble with database connections).

	There's a module-private instance of this that's used by Execute.
	"""
	def __init__(self):
		self.threadsCurrentlyActive = []
		self.activeListLock = threading.Lock()

	def _reapOldThreads(self):
		if len(self.threadsCurrentlyActive)>10:
			base.ui.notifyWarning("There's a suspicious number of cron"
				" threads active (%d).  You should check what's going on."%
				len(self.threadsCurrentlyActive))

		newThreads = []
		with self.activeListLock:
			for t in self.threadsCurrentlyActive:
				if t.isAlive():
					newThreads.append(t)
				else:
					t.join(timeout=0.001)
			self.threadsCurrentlyActive = newThreads

	def makeGuardedThreaded(self, callable, rd, title):
		"""returns callable ready for safe cron-like execution.
		"""
		serializingLock = threading.Lock()
		
		def innerFunction():
			try:
				try:
					callable(rd)
				except Exception, msg:
					base.ui.notifyError("Uncaught exception in timed job %s."
						" Trying to send traceback to the maintainer."%title)
					cron.sendMailToAdmin("DaCHS Job %s failed"%title,
						"".join(traceback.format_exception(*sys.exc_info())))
			finally:
				serializingLock.release()

		def cronFunction():
			self._reapOldThreads()
			if not serializingLock.acquire(False):
				base.ui.notifyWarning("Timed job %s has not finished"
					" before next instance came around"%title)
				return
			t = threading.Thread(name=title, target=innerFunction)
			t.daemon = True
			t.start()

			with self.activeListLock:
				self.threadsCurrentlyActive.append(t)

		return cronFunction

_guardedFunctionFactory = GuardedFunctionFactory()


class CronJob(procdef.ProcApp):
	"""Python code for a timed job.

	The resource descriptor this runs at is available as rd.
	"""
	name_ = "job"
	requiredType = "job"
	formalArgs = "rd"


class Execute(base.Structure):
	"""a container for calling code.

	This is a cron-like functionality.  The jobs are run in separate
	threads, so they need to be thread-safe with respect to the
	rest of DaCHS.	DaCHS serializes calls, though, so that your
	code should never run twice at the same time.

	At least on CPython, you must make sure your code does not
	block with the GIL held; this is still in the server process.
	If you do daring things, fork off (note that you must not use
	any database connections you may have after forking, which means
	you can't safely use the RD passed in).
	"""
	name_ = "execute"

	_title = base.UnicodeAttribute("title",
		default = base.Undefined,
		description="Some descriptive title for the job; this is used"
			" in diagnostics.",
		copyable=False,)

	_at = base.UnicodeAttribute("at",
		default=base.NotGiven,
		description='A hour:minute pair at which to run the code each day.'
		'  This conflicts with every.',
		copyable=True,)

	_every = base.IntAttribute("every",
		default=base.NotGiven,
		description="Run the job roughly every this many seconds."
		"  This conflicts with at.",
		copyable=True,)

	_job = base.StructAttribute("job",
		childFactory=CronJob,
		default=base.Undefined,
		description="The code to run.",
		copyable=True,)

	_rd = common.RDAttribute()

	def completeElement(self, ctx):
		self._completeElementNext(Execute, ctx)
		if len([s for s in [self.at, self.every] if s is base.NotGiven])!=1:
			raise base.StructureError("Exactly one of at and every required"
				" for Execute", pos=ctx.pos)

		if self.at is not base.NotGiven:
			mat = re.match(r"(\d+):(\d+)", self.at)
			if not mat:
				raise base.LiteralParseError("at", self.at, pos=ctx.pos, hint=
					"This must be in hour:minute format")
			self.hour, self.minute = int(mat.group(1)), int(mat.group(2))
			if not 0<=hour<=23 or 0<=minute<=59:
				raise base.LiteralParseError("at", self.at, pos=ctx.pos, hint=
					"This must be hour:minute with 0<=hour<=23 or 0<=minute<=59")

	def onElementComplete(self):
		self._onElementCompleteNext(Execute)
		callable = _guardedFunctionFactory.makeGuardedThreaded(
			self.job.compile(), self.rd, self.title)

		jobName = "%s#%s"%(self.rd.sourceId, self.title)
		if self.at is not base.NotGiven:
			cron.repeatAt(self.hour, self.minute, jobName, callable)
		else:
			cron.runEvery(self.every, jobName, callable)
