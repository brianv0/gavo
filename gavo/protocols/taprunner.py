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

import datetime
import logging
import os
import sys
import time
import traceback

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.base import valuemappers
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
# when it tries to kill the running query.
_WORKER_PID = None


def normalizeTAPFormat(rawFmt):
	format = rawFmt.lower()
	try:
		return tap.FORMAT_CODES[format][0]
	except KeyError:
		raise base.ValidationError(
			"Unsupported format '%s'."%format, colName="FORMAT",
			hint="Legal format codes include %s"%(", ".join(tap.FORMAT_CODES)))


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
		maxrec = min(base.getConfig("async", "hardMAXREC"),
			int(parameters["MAXREC"]))
	except ValueError:
		raise base.ui.logOldError(
			uws.UWSError("Invalid MAXREC literal '%s'."%parameters["MAXREC"]))
	except KeyError:
		maxrec = base.getConfig("async", "defaultMAXREC")
	return query, format, maxrec


def _makeDataFor(resultTable, job):
	"""returns an rsc.Data instance containing resultTable and some
	additional metadata.
	"""
	resData = rsc.wrapTable(resultTable)
	resData.addMeta("info", base.makeMetaValue("Query successful",
		name="info", infoName="QUERY_STATUS", infoValue="OK"))
	overflowedNo = base.getMetaText(resultTable, "_overflow")
	if overflowedNo:
		resData.addMeta("endinfo", base.makeMetaValue("Query (probably)"
			" truncated at element %s"%overflowedNo,
			name="endinfo", infoName="QUERY_STATUS", infoValue="OVERFLOW"))

	return resData


def writeResultTo(format, res, outF):
	formats.formatData(format, res, outF, acquireSamples=False)


def runTAPQuery(query, timeout, connection, tdsForUploads, maxrec):
	"""executes a TAP query and returns the result in a data instance.
	"""
# Some of this replicates functionality from adqlglue.  We should probably
# move the implementation there to what's done here.
	try:
		pgQuery, tableTrunk = adqlglue.morphADQL(query,
			tdsForUploads=tdsForUploads, externalLimit=maxrec)
		querier = base.SimpleQuerier(connection=connection)

		querier.setTimeout(timeout)
		# XXX Hack: this is a lousy fix for postgres' seqscan love with
		# limit.  See if we still want this with newer postgres...
		querier.configureConnection([("enable_seqscan", False)])
		result = rsc.QueryTable(tableTrunk.tableDef, pgQuery,
			connection=querier.connection)
		# copy meta info over from tableTrunk?
	except:
		adqlglue.mapADQLErrors(*sys.exc_info())
	return result


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
		if valuemappers.needsQuoting(destName):
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
			job.endTime = datetime.datetime.utcnow()
		sys.exit()


_preservedMIMEs = set([ # Spec, 2.7.1
	"text/xml", "application/x-votable+xml"])

def _getResultType(formatProduced, formatOrdered):
	"""returns the mime type for a TAP result.

	All this logic is necessary to pull through VOTable MIME types from
	the request format as mandated by the spec.
	"""
	if formatOrdered in _preservedMIMEs:
		return formatOrdered
	return formats.getMIMEFor(formatProduced)


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
		base.ui.notifyError(
			"Could not obtain PID for the worker, job %s"%jobId)
	tdsForUploads = _ingestUploads(parameters.get("UPLOAD", ""), 
		connectionForQuery)

	logging.info("taprunner executing %s"%query)
	res = runTAPQuery(query, timeout, connectionForQuery,
		tdsForUploads, maxrec)
	with tap.TAPJob.makeFromId(jobId) as job:
		destF = job.openResult(
			_getResultType(format, job.parameters.get("FORMAT")), "result")
		res = _makeDataFor(res, job)
	writeResultTo(format, res, destF)
	connectionForQuery.close()
	destF.close()


def runTAPJob(jobId, queryProfile="untrustedquery"):
	"""executes a TAP job defined by parameters and job id.
	"""
	with tap.TAPJob.makeFromId(jobId) as job:
		job.phase = uws.EXECUTING
		job.startTime = datetime.datetime.utcnow()
		timeout = job.executionDuration
		parameters = job.parameters
	try:
		_runTAPJob(parameters, jobId, queryProfile, timeout)
	except Exception, ex:
		with tap.TAPJob.makeFromId(jobId) as job:
			# This creates an error document in our WD and writes a log.
			job.changeToPhase(uws.ERROR, ex)
			job.endTime = datetime.datetime.utcnow()
		base.ui.notifyError("While executing TAP job %s: %s"%(
			jobId, ex))
	else:
		with tap.TAPJob.makeFromId(jobId) as job:
			job.changeToPhase(uws.COMPLETED, None)
			job.endTime = datetime.datetime.utcnow()


############### CLI


def setINTHandler(jobId):
	"""installs a signal handler that pushes our job to aborted on SIGINT.
	"""
	import signal

	def handler(signo, frame):
		# Let's be reckless for now and kill from the signal handler.
		with tap.TAPJob.makeFromId(jobId) as job:
			job.phase = uws.ABORTED
			if _WORKER_PID:
				logging.info("Trying to abort %s, wpid %s"%(
					jobId, _WORKER_PID))
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
		from gavo.protocols.gavolog import RotatingFileHandler
		logHandler = RotatingFileHandler(
			os.path.join(base.getConfig("logDir"), "taprunner"),
			maxBytes=500000, backupCount=1, mode=0664)
		# this will race since potentially many tap runners log to the
		# same file, but the logs are only for emergencies anyway.
		logging.getLogger("").addHandler(logHandler)
		logging.getLogger("").setLevel(logging.INFO)
		logging.debug("taprunner for %s started"%jobId)
	except: # don't die just because logging fails
		traceback.print_exc()

	try:
		_runInThread(lambda: runTAPJob(jobId))
		logging.debug("taprunner for %s finished"%jobId)
	except SystemExit:
		pass
	except uws.JobNotFound: # someone destroyed the job before I was done
		logging.info("giving up non-existing TAP job %s."%jobId)
	except Exception, ex:
		logging.error("taprunner %s major failure"%jobId, exc_info=True)
		# try to push job into the error state -- this may well fail given
		# that we're quite hosed, but it's worth the try
		with tap.TAPJob.makeFromId(jobId) as job:
			job.changeToPhase(uws.ERROR, ex)
		raise
