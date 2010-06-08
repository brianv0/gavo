"""
Execution of UWS (right now, TAP only) requests.

This mainly intended to be exec'd (through some wrapper) by the queue
runner in the main server thread.  The jobs executed have to be in
the database and have to have a job directory.

Primarily for testing an alternative interface rabRun exists that takes that
takes jobid, and parameters.

The tap runner takes the job to either COMPLETED, ABORTED or ERROR states.
It will not, however, change to EXECUTING.  That is the parent's job.
"""

from __future__ import with_statement

import os
import sys
import urllib
import traceback

from gavo import base
from gavo import formats
from gavo.formats import votableread
from gavo.protocols import adqlglue
from gavo.protocols import tap
from gavo.protocols import uws


FORMAT_CODES = {
# A mapping of values of TAP's FORMAT parameter to our formats.format codes.
	"application/x-votable+xml": "votable",
	"text/xml": "votable",
	"votable": "votable",
	"votable/td": "votabletd",
	"text/csv": "csv",
	"csv": "csv",
	"text/tab-separated-values": "tsv",
	"tsv": "tsv",
	"application/fits": "fits",
	"fits": "fits",
	"text/html": "html",
	"html": "html",
}


# The following would point to executors for other languages at some point.
SUPPORTED_LANGS = {
	'ADQL': None,
	'ADQL-2.0': None,
}


def normalizeTAPFormat(rawFmt):
	format = rawFmt.lower()
	try:
		return FORMAT_CODES[format]
	except KeyError:
		raise base.ValidationError("Unsupported format '%s'."%format,
			colName="FORMAT",
			hint="Legal format codes include %s"%(", ".join(FORMAT_CODES)))


def _parseTAPParameters(jobId, parameters):
	try:
		if parameters.get("VERSION", tap.TAP_VERSION)!=tap.TAP_VERSION:
			raise uws.UWSError("Version mismatch.  This service only supports"
				" TAP version %s"%tap.TAP_VERSION, jobId)
		if parameters["REQUEST"]!="doQuery":
			raise uws.UWSError("This service only supports REQUEST=doQuery", jobId)
		if parameters["LANG"] not in SUPPORTED_LANGS:
			raise uws.UWSError("This service only supports LANG=ADQL", jobId)
		query = parameters["QUERY"]
	except KeyError, key:
		raise uws.UWSError("Required parameter %s missing."%key, jobId)

	format = normalizeTAPFormat(parameters.get("FORMAT", "votable"))

	try:
		maxrec = int(parameters["MAXREC"])
	except ValueError:
		raise uws.UWSError("Invalid MAXREC literal '%s'."%parameters["MAXREC"])
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
			srcF = urllib.urlopen(src)
		tds.append(votableread.uploadVOTable(destName, srcF, connection,
				forceQuotedNames=True).tableDef)
		srcF.close()
	return tds


def _runTAPJob(parameters, jobId, timeout, queryProfile):
	"""executes a TAP job defined by parameters.  
	
	This does not do state management.  Use runTAPJob if you need it.
	"""
	query, format, maxrec = _parseTAPParameters(jobId, parameters)
	connectionForQuery = base.getDBConnection(queryProfile)
	tdsForUploads = _ingestUploads(parameters.get("UPLOAD", ""), 
		connectionForQuery)
	with tap.TAPJob.makeFromId(jobId) as job:
		job.phase = uws.EXECUTING
	res = runTAPQuery(query, timeout, connectionForQuery,
		tdsForUploads)
	with tap.TAPJob.makeFromId(jobId) as job:
		destF = job.openResult(formats.getMIMEFor(format), "result")
	writeResultTo(format, res, destF)
	destF.close()


def runTAPJob(parameters, jobId, timeout, queryProfile="untrustedquery"):
	"""executes a TAP job defined by parameters and job id.
	"""
	try:
		_runTAPJob(parameters, jobId, timeout, queryProfile)
	except Exception, ex:
		traceback.print_exc()
		with tap.TAPJob.makeFromId(jobId) as job:
			# This creates an error document in our WD.
			job.changeToPhase(uws.ERROR, ex)
	else:
		with tap.TAPJob.makeFromId(jobId) as job:
			job.changeToPhase(uws.COMPLETED, None)


############### CLI interface

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
	try:
		with tap.TAPJob.makeFromId(jobId) as job:
			parameters = job.parameters
			jobId, timeout = job.jobId, job.executionDuration
	except base.NotFoundError:  # Job was deleted before we came up.
		sys.exit(1)
	runTAPJob(parameters, jobId, timeout)
