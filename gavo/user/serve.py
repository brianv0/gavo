"""
A wrapper script suitable for starting the server.
"""

from __future__ import with_statement

import datetime
import grp
import os
import pkg_resources
import pwd
import signal
import sys
import time
import warnings

from nevow import appserver
from nevow import inevow
from nevow import rend
from twisted.internet import reactor
from twisted.python import log
from twisted.python import logfile

from gavo import base
from gavo import utils
from gavo.base import config
from gavo.base import cron
from gavo.user.common import exposedFunction, makeParser
from gavo.web import root


def setupServer(rootPage):
	config.setMeta("upSince", utils.formatISODT(datetime.datetime.utcnow()))
	base.ui.notifyWebServerUp()
	cron.registerScheduleFunction(reactor.callLater)


class _PIDManager(object):
	"""A manager for the PID of the server.

	There's a single instance of this below.
	"""
	def __init__(self):
		self.path = os.path.join(base.getConfig("stateDir"), "web.pid")
	
	def getPID(self):
		"""returns the PID of the currently running server, or None.
		"""
		try:
			with open(self.path) as f:
				pidString = f.readline()
		except IOError: # PID file does not exist (or we're beyond repair)
			return None
		try:
			return int(pidString)
		except ValueError: # junk in PID file -- no sense in keeping it
			base.ui.notifyWarning("%s contained garbage, attempting to unlink"%
				self.path)
			self.clearPID()

	def setPID(self):
		"""writes the current process' PID to the PID file.

		Any existing content will be clobbered; thus, you could have
		races here (and since both daemons would bind to the same socket,
		only one would survive, possibly the wrong one).  Let's just stipulate
		people won't start two competing daemons.
		"""
		try:
			with open(self.path, "w") as f:
				f.write(str(os.getpid()))
		except IOError: # Cannot write PID.  This would suggest that much else
		                # is broken as well, so we bail out
			base.ui.notifyError("Cannot write PID file %s. Assuming all is"
				" broken, bailing out."%self.file)
			sys.exit(1)

	def clearPID(self):
		"""removes the PID file.
		"""
		try:
			os.unlink(self.path)
		except os.error, ex:
			if ex.errno==2: # ENOENT, we don't have to do anything
				pass
			else:
				base.ui.notifyError("Cannot remove PID file %s (%s).  This"
					" probably means some other server owns it now."%(
						self.file, str(ex)))


PIDManager = _PIDManager()


def _reloadConfig():
	"""should clear as many caches as we can get hold of.
	"""
	base.caches.clearCaches()
	base.ui.notifyInfo("Cleared all caches on SIGHUP")


def _dropPrivileges():
	uid = None
	user = base.getConfig("web", "user")
	if user:
		try:
			uid = pwd.getpwnam(user)[2]
		except KeyError:
			base.ui.notifyError("Cannot change to user %s (not found)\n"%user)
			sys.exit(1)
		try:
			try:
				os.setgid(grp.getgrnam(base.getConfig("group"))[2])
			except Exception, ex: 
				# don't fail because of setgid failure (should I rather?)
				warnings.warn("Could not sgid to gavo group (%s)."%(str(ex)))
			os.setuid(uid)
		except os.error, ex:
			base.ui.notifyError("Cannot change to user %s (%s)\n"%(
				user, str(ex)))


def daemonize(logFile, callable):
	# We translate TERMs to INTs to ensure finally: code is executed
	signal.signal(signal.SIGTERM, 
		lambda a,b: os.kill(os.getpid(), signal.SIGINT))
	pid = os.fork()
	if pid == 0:
		os.setsid() 
		pid = os.fork() 
		if pid==0:
			os.close(0)
			os.close(1)
			os.close(2)
			os.dup(logFile.fileno())
			os.dup(logFile.fileno())
			os.dup(logFile.fileno())
			callable()
		else:
			os._exit(0)
	else:
		os._exit(0)


def _configureTwistedLog():
	theLog = logfile.LogFile("web.log", base.getConfig("logDir"))
	log.startLogging(theLog, setStdout=False)
	def rotator():
		theLog.shouldRotate()
		reactor.callLater(86400, rotator)
	rotator()


def _startServer():
	"""runs a detached server, dropping privileges and all.
	"""
	try:
		reactor.listenTCP(
			int(base.getConfig("web", "serverPort")), 
			root.site,
			interface=base.getConfig("web", "bindAddress"))
	except CannotListenError:
		raise base.ReportableError("Someone already listens on the"
			" configured port %s."%base.getConfig("web", "serverPort"),
			hint="This could mean that a DaCHS server is already running."
			" You would have to manually kill it then since its PID file"
			" got lost somehow.  It's more likely that some"
			" other server is already taking up this port; you may want to change"
			" the [web] serverPort setting in that case.")
	_dropPrivileges()
	_configureTwistedLog()
	
	PIDManager.setPID()
	try:
		setupServer(root)
		signal.signal(signal.SIGHUP, lambda sig, stack: 
			reactor.callLater(0, _reloadConfig))
		reactor.run()
	finally:
		PIDManager.clearPID()


@exposedFunction(help="start the server and put it in the background.")
def start(args):
	oldPID = PIDManager.getPID()
	if oldPID is not None:  # Presumably, there already is a server running
		sys.exit("It seems there's already a server (pid %s) running."
			" Try 'gavo serve stop'."%(PIDManager.getPID()))
	daemonize(
		open(os.path.join(base.getConfig("logDir"), "server.stderr"), "a"), 
		_startServer)


def _waitForServerExit(timeout=5):
	"""waits for server process to terminate.
	
	It does so by polling the server pid file.
	"""
	for i in range(int(timeout*10)):
		if PIDManager.getPID() is None:
			break
		time.sleep(0.1)
	else:
		sys.exit("The server with pid %d refuses to die.  Please try manually"%
			pid)


def _stopServer():
	pid = PIDManager.getPID()
	if pid is None:  # No server running, nothing to do
		return
	try:
		os.kill(pid, signal.SIGTERM)
	except os.error, ex:
		if ex.errno==3: # no such process
			PIDManager.clearPID()
			base.ui.notifyWarning("Removed stale PID file.")
			return
		else:
			raise
	_waitForServerExit()


@exposedFunction(help="stop a running server.")
def stop(args):
	_stopServer()


@exposedFunction(help="restart the server")
def restart(args):
	_stopServer()
	start(args)


@exposedFunction(help="reload server configuration (incomplete)")
def reload(args):
	pid = PIDManager.getPID()
	if pid is None:
		raise base.ReportableError("No DaCHS server appears to be running."
			"  Thus, not reloading.")
	os.kill(pid, signal.SIGHUP)


class ExitPage(rend.Page):
	def renderHTTP(self, ctx):
		req = inevow.IRequest(ctx)
		req.setHeader("content-type", "text/plain")
		reactor.stop()
		return "exiting."


@exposedFunction(help="run a server and remain in the foreground, dumping"
	" all kinds of stuff to the terminal")
def debug(args):
	log.startLogging(sys.stderr)
	base.DEBUG = True
	root.root.child_exit = ExitPage()
	reactor.listenTCP(int(base.getConfig("web", "serverPort")), root.site)
	setupServer(root)
	reactor.run()


def main():
	args = makeParser(globals()).parse_args()
	args.subAction(args)


if __name__=="__main__":
	main()
