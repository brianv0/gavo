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
import traceback

from gavo import base
from gavo import formats
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
		# VERSION is checked at submission
		if parameters["REQUEST"]!="doQuery":
			raise uws.UWSError("This service only supports REQUEST=doQuery", jobId)
		if parameters["LANG"]!="ADQL":
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


def runTAPQuery(query, timeout, queryProfile):
	"""executes a TAP query and returns the result in a data instance.
	"""
	try:
		return adqlglue.query(query, timeout=timeout, queryProfile=queryProfile)
	except:
		adqlglue.mapADQLErrors(*sys.exc_info())


def runTAPJob(parameters, jobId, resultName, timeout, 
		queryProfile="untrustedquery"):
	"""executes a TAP job defined by parameters.  
	
	As a side effect, it will create a file result.data in jobWD.

	Right now, we only execute ADQL queries and bail out on anything else.
	"""
	query, format, maxrec = _parseTAPParameters(jobId, parameters)
	res = runTAPQuery(query, timeout, queryProfile)
	with open(resultName, "w") as outF:
		writeResultTo(format, res, outF)


############### CLI interface

def parseCommandLine():
	from optparse import OptionParser
	parser = OptionParser(usage="%prog <jobid> -- run an enqueued UWS job.")
	opts, args = parser.parse_args()
	if len(args)!=1:
		parser.print_help()
		sys.exit(1)
	return opts, args[0]


def main():
	"""causes the execution of the job with jobId sys.argv[0].
	"""
	opts, jobId = parseCommandLine()
	with uws.makeFromId(jobId) as job:
		parameters = job.getParDict()
		jobId, timeout = job.jobId, job.executionDuration
		resultName = job.getResultName()
	try:
		runTAPJob(parameters, jobId, resultName, timeout)
	except Exception, ex:
		traceback.print_exc()
		with uws.makeFromId(jobId) as job:
			# This creates an error document in our WD.
			job.changeToPhase(uws.ERROR, ex)
	else:
		with uws.makeFromId(jobId) as job:
			job.changeToPhase(uws.COMPLETED, None)
