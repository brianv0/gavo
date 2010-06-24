"""
Execution of UWS (right now, TAP only) requests.

This mainly intended to be exec'd (through some wrapper) by the queue
runner in the main server thread.  The jobs executed have to be in
the database and have to have a job directory.

Primarily for testing an alternative interface rabRun exists that takes that
takes jobid, and parameters.

The tap runner takes the job to EXECUTING shortly before sending the
query to the DB server.  When done, the job's state is one of COMPLETED, 
ABORTED or ERROR.
"""

from __future__ import with_statement

import os
import sys
import time
import traceback

from twisted.python import log

from gavo import base
from gavo import formats
from gavo import utils
from gavo.grammars import votablegrammar
from gavo.formats import votableread
from gavo.protocols import adqlglue
from gavo.protocols import tap
from gavo.protocols import uws



# The following would point to executors for other languages at some point.
SUPPORTED_LANGS = {
	'ADQL': None,
	'ADQL-2.0': None,
}


# The pid of the worker db backend.  This is used in the signal handler
# try and kill the running query.
_WORKER_PID = None


def normalizeTAPFormat(rawFmt):
	format = rawFmt.lower()
	try:
		return tap.FORMAT_CODES[format]
	except KeyError:
		raise base.ui.logOldExc(base.ValidationError(
			"Unsupported format '%s'."%format, colName="FORMAT",
			hint="Legal format codes include %s"%(", ".join(tap.FORMAT_CODES))))


def _parseTAPParameters(jobId, parameters):
	rd = base.caches.getRD("__system__/tap")
	version = rd.getProperty("TAP_VERSION")
	try:
		if parameters.get("VERSION", version)!=version:
			raise uws.UWSError("Version mismatch.  This service only supports"
				" TAP version %s"%version, jobId)
		if parameters["REQUEST"]!="doQuery":
			raise uws.UWSError("This service only supports REQUEST=doQuery", jobId)
		if parameters["LANG"] not in SUPPORTED_LANGS:
			raise uws.UWSError("This service only supports LANG=ADQL", jobId)
		query = parameters["QUERY"]
	except KeyError, key:
		raise base.ui.logOldExc(base.ValidationError(
			"Required parameter %s missing."%key, key))

	format = normalizeTAPFormat(parameters.get("FORMAT", "votable"))

	try:
		maxrec = int(parameters["MAXREC"])
	except ValueError:
		raise base.ui.logOldError(
			uws.UWSError("Invalid MAXREC literal '%s'."%parameters["MAXREC"]))
	except KeyError:
		maxrec = base.getConfig("async", "defaultMAXREC")
	return query, format, maxrec


def writeResultTo(format, res, outF):
	formats.formatData(format, res, outF)


def runTAPQuery(query, timeout, connection, tdsForUploads):
	"""executes a TAP query and returns the result in a data instance.
	"""
	try:
		querier = base.SimpleQuerier(connection=connection)
		return adqlglue.query(querier, query, timeout=timeout,
			tdsForUploads=tdsForUploads)
	except:
		adqlglue.mapADQLErrors(*sys.exc_info())


def _ingestUploads(uploads, connection):
	tds = []
	for destName, src in uploads:
		if isinstance(src, tap.LocalFile):
			srcF = open(src.fullPath)
		else:
			try:
				srcF = utils.urlopenRemote(src)
			except IOError, ex:
				raise base.ui.logOldExc(
					base.ValidationError("Upload '%s' cannot be retrieved"%(
					src), "UPLOAD", hint="The I/O operation failed with the message: "+
					str(ex)))
		if votablegrammar.needsQuoting(destName):
			raise base.ValidationError("'%s' is not a valid table name on"
				" this site"%destName, "UPLOAD", hint="It either contains"
				" non-alphanumeric characters or conflicts with an ADQL"
				" reserved word.  Quoted table names are not supported"
				" at this site.")
		uploadedTable = votableread.uploadVOTable(destName, srcF, connection,
				nameMaker=votableread.AutoQuotedNameMaker())
		if uploadedTable is not None:
			tds.append(uploadedTable.tableDef)
		srcF.close()
	return tds


def _noteWorkerPID(conn):
	"""stores conn's worker PID in _WORKER_PID.
	"""
	global _WORKER_PID
	curs = conn.cursor()
	curs.execute("SELECT pg_backend_pid()")
	_WORKER_PID = curs.fetchall()[0][0]
	curs.close()


def _hangIfMagic(jobId, parameters, timeout):
# Test intrumentation. There are more effective ways to DoS me.
	if parameters.get("QUERY")=="JUST HANG around":
		time.sleep(timeout)
		with tap.TAPJob.makeFromId(jobId) as job:
			job.phase = uws.COMPLETED
		sys.exit()


def _runTAPJob(parameters, jobId, queryProfile, timeout):
	"""executes a TAP job defined by parameters.  
	
	This does not do state management.  Use runTAPJob if you need it.
	"""
	_hangIfMagic(jobId, parameters, timeout)
	query, format, maxrec = _parseTAPParameters(jobId, parameters)
	connectionForQuery = base.getDBConnection(queryProfile)
	try:
		_noteWorkerPID(connectionForQuery)
	except: # Don't fail just because we can't kill workers
		base.ui.notifyErrorOccurred(
			"Could not obtain PID for the worker, job %s"%jobId)
	tdsForUploads = _ingestUploads(parameters.get("UPLOAD", ""), 
		connectionForQuery)

	res = runTAPQuery(query, timeout, connectionForQuery,
		tdsForUploads)
	with tap.TAPJob.makeFromId(jobId) as job:
		destF = job.openResult(formats.getMIMEFor(format), "result")
	writeResultTo(format, res, destF)
	destF.close()


def runTAPJob(parameters, jobId, queryProfile="untrustedquery"):
	"""executes a TAP job defined by parameters and job id.
	"""
	with tap.TAPJob.makeFromId(jobId) as job:
		job.phase = uws.EXECUTING
		timeout = job.executionDuration
	try:
		_runTAPJob(parameters, jobId, queryProfile, timeout)
	except Exception, ex:
		with tap.TAPJob.makeFromId(jobId) as job:
			# This creates an error document in our WD and writes a log.
			job.changeToPhase(uws.ERROR, ex)
	else:
		with tap.TAPJob.makeFromId(jobId) as job:
			job.changeToPhase(uws.COMPLETED, None)


############### CLI


def setINTHandler(jobId):
	"""installs a signal handler that pushes our job to aborted on SIGINT.
	"""
	import signal

	def handler(signo, frame):
		# Let's be reckless for now and kill from the signal handler.
		log.msg("Runner for job %s received SIGINT, wpid %s"%(jobId, _WORKER_PID))
		with tap.TAPJob.makeFromId(jobId) as job:
			job.phase = uws.ABORTED
			if _WORKER_PID:
				killConn = base.getDBConnection("admin")
				curs = killConn.cursor()
				curs.execute("SELECT pg_cancel_backend(%d)"%_WORKER_PID)
				curs.close()
				killConn.close()
			sys.exit(2)

	signal.signal(signal.SIGINT, handler)


def joinInterruptibly(t):
	while True: 
		t.join(timeout=0.5)
		if not t.isAlive():
			return


def _runInThread(target):
	# The standalone tap runner must run the query in a thread since
	# it must be able to react to a SIGINT.
	import threading
	t = threading.Thread(target=target)
	t.setDaemon(True)
	t.start()
	joinInterruptibly(t)


def parseCommandLine():
	from optparse import OptionParser
	parser = OptionParser(usage="%prog <jobid>",
		description="runs the TAP job with <jobid> from the UWS table.")
	opts, args = parser.parse_args()
	if len(args)!=1:
		parser.print_help()
		sys.exit(1)
	return opts, args[0]


def main():
	"""causes the execution of the job with jobId sys.argv[0].
	"""
	# there's a problem in CLI behaviour in that if anything goes wrong in 
	# main, a job that may have been created will remain QUEUED forever.
	# There's little we can do about that, though, since we cannot put
	# a job into ERROR when we don't know its id or cannot get it from the DB.
	opts, jobId = parseCommandLine()
	setINTHandler(jobId)
	try:
		theLog = logfile.LogFile("taprunner", base.getConfig("logDir"))
		# this will race since potentially many tap runners log to the
		# same file, but the logs are only for emergencies anyway.
		log.startLogging(theLog)
	except: # don't die just because logging fails
		pass

	try:
		with tap.TAPJob.makeFromId(jobId) as job:
			parameters = job.parameters
		
		_runInThread(lambda: runTAPJob(parameters, jobId))
	except SystemExit:
		pass
	except uws.JobNotFound: # someone destroyed the job before I was done
		pass
	except:
		base.ui.notifyErrorOccurred("Taprunner major failure")
		raise
