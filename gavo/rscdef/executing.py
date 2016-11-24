"""
The execute element and related stuff.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
import re
import subprocess
import sys
import threading
import traceback

from gavo import base
from gavo.base import cron
from gavo.rscdef import common
from gavo.rscdef import procdef


class GuardedFunctionFactory(object):
	"""a class for making functions safe for cron-like executions.

	The main method is makeGuarded.  It introduces a lock protecting against
	double execution (if that were to happen, the execution is suppressed with a
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

	def makeGuardedThreaded(self, callable, execDef):
		"""returns callable ready for safe cron-like execution.

		execDef is an Execute instance.
		"""
		serializingLock = threading.Lock()
		
		def innerFunction():
			try:
				try:
					execDef.outputAccum = []
					callable(execDef.rd, execDef)
				except Exception:
					base.ui.notifyError("Uncaught exception in timed job %s."
						" Trying to send traceback to the maintainer."%execDef.jobName)
					cron.sendMailToAdmin("DaCHS Job %s failed"%execDef.jobName,
						"".join(traceback.format_exception(*sys.exc_info())))
			finally:
				serializingLock.release()
			if execDef.debug and execDef.outputAccum:
				cron.sendMailToAdmin("Debug output of DaCHS Job %s"%execDef.jobName,
					"\n".join(execDef.outputAccum))
				del execDef.outputAccum

		def cronFunction():
			self._reapOldThreads()
			if not serializingLock.acquire(False):
				base.ui.notifyWarning("Timed job %s has not finished"
					" before next instance came around"%execDef.jobName)
				return
			t = threading.Thread(name=execDef.title, target=innerFunction)
			base.ui.notifyInfo("Spawning thread for cron job %s"%execDef.title)
			t.daemon = True
			t.start()

			with self.activeListLock:
				self.threadsCurrentlyActive.append(t)

			return t

		return cronFunction

_guardedFunctionFactory = GuardedFunctionFactory()


class CronJob(procdef.ProcApp):
	"""Python code for use within execute.

	The resource descriptor this runs at is available as rd, the execute
	definition (having such attributes as title, job, plus any
	properties given in the RD) as execDef.

	Note that no I/O capturing takes place (that's impossible since in
	general the jobs run within the server).  To have actual cron jobs,
	use ``execDef.spawn(["cmd", "arg1"...])``.  This will send a mail on failed
	execution and also raise a ReportableError in that case.

	In the frequent use case of a resdir-relative python program, you
	can use the ``execDef.spawnPython(modulePath)`` function.

	If you must stay within the server process, you can do something like::

		mod = utils.loadPythonModule(rd.getAbsPath("bin/coverageplot.py"))
		mod.makePlot()
	
	-- in that way, your code can sit safely within the resource directory
	and you still don't have to manipulate the module path.
	"""
	name_ = "job"
	formalArgs = "rd, execDef"


class Execute(base.Structure, base.ExpansionDelegator):
	"""a container for calling code.

	This is a cron-like functionality.  The jobs are run in separate
	threads, so they need to be thread-safe with respect to the
	rest of DaCHS.	DaCHS serializes calls, though, so that your
	code should never run twice at the same time.

	At least on CPython, you must make sure your code does not
	block with the GIL held; this is still in the server process.
	If you do daring things, fork off (note that you must not use
	any database connections you may have after forking, which means
	you can't safely use the RD passed in).  See the docs on `Element job`_.

	Then testing/debugging such code, use ``gavo admin execute rd#id``
	to immediately run the jobs.
	"""
	name_ = "execute"

	_title = base.UnicodeAttribute("title",
		default = base.Undefined,
		description="Some descriptive title for the job; this is used"
			" in diagnostics.",
		copyable=False,)

	_at = base.StringListAttribute("at",
		description="One or more hour:minute pairs at which to run"
			" the code each day.  This conflicts with every.  Optionally,"
			" you can prefix each time by one of m<dom> or w<dow> for"
			" jobs only to be exectued at some day of the month or week, both"
			" counted from 1.  So, 'm22 7:30, w3 15:02' would execute on"
			" the 22nd of each month at 7:30 UTC and on every wednesday at 15:02.",
		default=base.NotGiven,
		copyable=True,)

	_every = base.IntAttribute("every",
		default=base.NotGiven,
		description="Run the job roughly every this many seconds."
		"  This conflicts with at.  Note that the first execution of"
		" such a job is after every/10 seconds, and that the timers"
		" start anew at every server restart.  So, if you restart"
		" often, these jobs may run much more frequently or not at all"
		" if the interval is large.  If every is smaller than zero, the"
		" job will be executed immediately when the RD is being loaded and is"
		" then run every abs(every) seconds",
		copyable=True,)

	_job = base.StructAttribute("job",
		childFactory=CronJob,
		default=base.Undefined,
		description="The code to run.",
		copyable=True,)

	_debug = base.BooleanAttribute("debug",
		description="If true, on execution of external processes (span or"
			" spawnPython), the output will be accumulated and mailed to"
			" the administrator.  Note that output of the actual cron job"
			" itself is not caught (it might turn up in serverStderr)."
			" You could use execDef.outputAccum.append(<stuff>) to have"
			" information from within the code included.", default=False)

	_properties = base.PropertyAttribute()

	_rd = common.RDAttribute()

	def spawn(self, cliList):
		"""spawns an external command, capturing the output and mailing it
		to the admin if it failed.

		Output is buffered and mailed, so it shouldn't be  too large.

		This does not raise an exception if it failed (in normal usage,
		this would cause two mails to be sent).  Instead, it returns the 
		returncode of the spawned process; if that's 0, you're ok.  But
		in general, you wouldn't want to check it.
		"""
		p = subprocess.Popen(cliList,
			stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
			stderr=subprocess.STDOUT, close_fds=True)
		childOutput, _ = p.communicate()
		if p.returncode:
			cron.sendMailToAdmin("A process spawned by %s failed with %s"%(
				self.title, p.returncode),
				"Output of %s:\n\n%s"%(cliList, childOutput))

		elif self.debug:
			if childOutput:
				self.outputAccum.append("\n\n%s -> %s\n"%(cliList, p.returncode))
				self.outputAccum.append(childOutput)

		return p.returncode
	
	def spawnPython(self, pythonFile):
		"""spawns a new python interpreter executing pythonFile.

		pythonFile may be resdir-relative.
		"""
		self.spawn(["python", os.path.join(self.rd.resdir, pythonFile)])

	def _parseAt(self, atSpec, ctx):
		"""returns a tuple ready for cron.repeatAt from atSpec.

		see the at StringListAttribute for how it would look like; this
		parses one element of that string list.
		"""
		mat = re.match(r"(?P<dow>w\d\s+)?"	
			r"(?P<dom>m\d\d?\s+)?"
			r"(?P<hr>\d+):(?P<min>\d+)", atSpec)
		if not mat:
			raise base.LiteralParseError("at", atSpec, pos=ctx.pos, hint=
				"This is hour:minute optionally prefixed by either w<weekday> or"\
				" m<day of month>, each counted from 1.")
		
		hour, minute = int(mat.group("hr")), int(mat.group("min"))
		if not (0<=hour<=23 and 0<=minute<=59):
			raise base.LiteralParseError("at", atSpec, pos=ctx.pos, hint=
				"This must be hour:minute with 0<=hour<=23 or 0<=minute<=59")

		dom = None
		if mat.group("dom"):
			dom = int(mat.group("dom")[1:])
			if not 1<=dom<=28:
				raise base.LiteralParseError("at", atSpec, pos=ctx.pos, hint=
					"day-of-month in at must be between 1 and 28.")

		dow = None
		if mat.group("dow"):
			dow = int(mat.group("dow")[1:])
			if not 1<=dow<=7:
				raise base.LiteralParseError("at", atSpec, pos=ctx.pos, hint=
					"day-of-week in at must be between 1 and 7.")

		return (dom, dow, hour, minute)

	def completeElement(self, ctx):
		self._completeElementNext(Execute, ctx)
		if len([s for s in [self.at, self.every] if s is base.NotGiven])!=1:
			raise base.StructureError("Exactly one of at and every required"
				" for Execute", pos=ctx.pos)

		if self.at is not base.NotGiven:
			self.parsedAt = []
			for literal in self.at:
				self.parsedAt.append(self._parseAt(literal, ctx))

	def onElementComplete(self):
		self._onElementCompleteNext(Execute)

		self.jobName = "%s#%s"%(self.rd.sourceId, self.title)

		self.callable = _guardedFunctionFactory.makeGuardedThreaded(
			self.job.compile(), self)

		if self.at is not base.NotGiven:
			cron.repeatAt(self.parsedAt, self.jobName, self.callable)
		else:
			cron.runEvery(self.every, self.jobName, self.callable)
