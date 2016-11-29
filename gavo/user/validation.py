"""
A cli-facing module providing functionality to "validate" one or more
resource descriptors.

Validation means giving some prognosis as to whether RD will properly work 
within both the DC and the VO.

While validation is active there's base.VALIDATING=True.  If RDs
to anything expensive, they're advised to have something like::

	if getattr(base, "VALIDATING", False):
		(don't do the expensive thing)
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re
import sys
import traceback

from gavo import api
from gavo import adql
from gavo import base
from gavo import stc
from gavo import utils
from gavo.helpers import testtricks
from gavo.imp import argparse
from gavo.registry import builders
from gavo.registry import publication
from gavo.protocols import datalink
from gavo.user import errhandle
from gavo.web import htmltable

from gavo.web import examplesrender #noflake: for RST registration

builders.VALIDATING = True

class TestsCollector(object):
	"""a singleton that collects use cases to run.

	Don't instantiate, this is a global singleton.

	The testsToRun attribute contains the test suites to run.
	"""
	testsToRun = []

	@classmethod
	def addRD(cls, rd):
		"""adds tests from rd.
		"""
		for suite in rd.tests:
			cls.testsToRun.append(suite)


def outputDependentMessage(aString):
	"""an output function for errhandle.raiseAndCatch.

	It is used here to indent dependent error messages.
	"""
	print re.sub("(?m)^", "  ", aString)


def outputError(rdId, message, verbose=False):
	print "[ERROR] %s: %s"%(rdId, message)
	if verbose:
		errhandle.raiseAndCatch(output=outputDependentMessage)


def outputWarning(rdId, message, verbose=False):
	print "[WARNING] %s: %s"%(rdId, message)
	if verbose:
		errhandle.raiseAndCatch(output=outputDependentMessage)


def loadRD(rdId):
	"""returns the RD identified by rdId.

	If that fails, diagnostics are printed and None is returned.
	"""
	try:
		rd = api.getReferencedElement(rdId, doQueries=False)

		# This is so we can validate userconfig.rd
		if hasattr(rd, "getRealRD"):
			rd = rd.getRealRD()

	except api.RDNotFound:
		outputError(rdId, "Could not be located")
	except api.LiteralParseError:
		outputError(rdId, "Bad literal in RD, message follows", True)
	except api.StructureError:
		outputError(rdId, "Malformed RD input, message follows", True)
	except api.Error:
		outputError(rdId, "Syntax or internal error, message follows", True)
	else:
		return rd
	# Fallthrough: RD could not be loaded
	return None


_XSD_VALIDATOR = testtricks.XSDTestMixin()


def isIVOPublished(svc):
	"""returns true if svc has a publication facing the VO.
	"""
	for pub in svc.publications:
		if "ivo_managed" in pub.sets:
			return True
	else:
		return False


def validateServices(rd, args):
	"""outputs to stdout various diagnostics about the services on rd.
	"""
	validSoFar = True
	for svc in rd.services:
		# If it's not published, metadata are nobody's business.
		if not (args.prePublication or svc.publications):
			continue
		try:
			base.validateStructure(svc)
		except api.MetaValidationError, ex:
			validSoFar = False
			outputError(rd.sourceId, "Missing metadata for publication of"
				" service %s:\n%s"%(svc.id, str(ex)))
			continue # further checks will just add verbosity

		if not (args.prePublication or isIVOPublished(svc)):
			# require sane metadata only if the VO will see the service
			continue

		# error out if the identifier cannot be generated
		api.getMetaText(svc, "identifier")
		registryRecord = None
		try:
			registryRecord = builders.getVORMetadataElement(svc)
		except stc.STCSParseError, msg:
			validSoFar = False
			outputError(rd.sourceId, "Invalid STC-S (probably in coverage meta)"
				": %s"%str(msg))
		except:
			validSoFar = False
			outputError(rd.sourceId, "Error when producing registry record"
				" of service %s:"%svc.id, True)
		
		if registryRecord is not None:
			try:
				_XSD_VALIDATOR.assertValidates(
					registryRecord.render(), leaveOffending=True)
			except AssertionError, msg:
				validSoFar = False
				outputError(rd.sourceId, "Invalid registry record for service"
					" %s:\n%s"%(svc.id, str(msg)))

	return validSoFar


def validateRST(rd, args):
	"""outputs diagnostics on RST formatting problems.
	"""
	def validateRSTOne(el):
		validSoFar = True

		for key, val in getattr(el, "getAllMetaPairs", lambda: [])():
			if  val.format=='rst':
				content = val.getExpandedContent(macroPackage=el)
				_, msg = utils.rstxToHTMLWithWarning(content)
				if msg:
					outputWarning(rd.sourceId, 
						"%s metadata on %s (%s) has an RST problem: %s"%(
							key, el, utils.makeEllipsis(content, 80), msg))
		
		for child in el.iterChildren():
			if child:
				validSoFar = validSoFar and validateRSTOne(child)

		return validSoFar

	return validateRSTOne(rd)


def validateRowmakers(rd, args):
	"""tries to build all rowmakers mentioned in the RD and bails out
	if one is bad.
	"""
	for dd in rd:
		for m in dd.makes:
			m.table.onDisk = False
			try:
				api.TableForDef(m.table)
				m.rowmaker.compileForTableDef(m.table)
			finally:
				m.table.onDisk = True
	return True


def validateOtherCode(rd, args):
	"""tries to compile other pieces of code in an RD and bails out
	if one is bad.
	"""
	retval = True

	for suite in rd.tests:
		for test in suite.tests:
			try:
				test.compile()
			except Exception, msg:
				outputError(rd.sourceId, "Bad test '%s': %s"%(test.title,
					msg))
				retval = False
	
	for svc in rd.services:
		for outputField in svc.getCurOutputFields():
			if outputField.formatter:
				try:
					htmltable._compileRenderer(outputField.formatter, None)
				except Exception, msg:
					outputError(rd.sourceId, "Bad formatter on output field '%s': %s"%(
						outputField.name, msg))
					retval = False

		if isinstance(svc.core, datalink.DatalinkCore):
			try:
				if "dlmeta" in svc.allowed:
					svc.core.descriptorGenerator.compile(svc.core)
				if "dlget" in svc.allowed:
					for df in svc.core.dataFunctions:
						df.compile(svc.core)
					svc.core.dataFormatter.compile(svc.core)
			except Exception, msg:
				outputError(rd.sourceId, "Bad datalink function in service '%s': %s"%(
					svc.id, msg))
				if isinstance(msg, base.BadCode):
					outputError(rd.sourceId, "Bad code:\n%s"%msg.code)
				retval = False

	for job in rd.jobs:
		try:
			job.job.compile(parent=rd)
		except Exception, msg:
			outputError(rd.sourceId, "Bad code in job  '%s': %s"%(
				job.title, msg))
			retval = False

	# TODO: iterate over service/cores and standalone cores and
	# fiddle out condDescs
	# TODO: Iterate over scripts and data/make/scripts, see which
	# are python and try to compile them
	# TODO: Iterate over grammars and validate rowfilters

	return retval


def validateTables(rd, args):
	"""does some sanity checks on the (top-level) tables within rd.
	"""
	valid = True

	identifierSymbol = adql.getSymbols()["identifier"]

	for td in rd.tables:
		for col in td:
			try:
				if col.unit:
					parsedUnit = api.parseUnit(col.unit)
					if parsedUnit.isUnknown and not args.acceptFreeUnits:
						outputWarning(rd.sourceId,
							"Column %s.%s: Unit %s is not interoperable"%(
							td.getQName(), col.name, col.unit))
					
			except api.BadUnit:
				valid = False
				outputError(rd.sourceId, "Bad unit in table %s, column %s: %s"%(
					td.getQName(), col.name, repr(col.unit)))

			try:
				identifierSymbol.parseString(str(col.name), parseAll=True)
			except base.ParseException, msg:
				outputWarning(rd.sourceId, "Column %s.%s: Name is not a regular"
					" ADQL identifier."%(td.id, col.name))

		if td.onDisk and args.compareDB:
			with base.getTableConn() as conn:
				q = base.UnmanagedQuerier(conn)
				if q.tableExists(td.getQName()):
					t = api.TableForDef(td, connection=conn)
					try:
						t.ensureOnDiskMatches()
					except api.DataError, msg:
						outputError(rd.sourceId, 
							utils.makeEllipsis(utils.safe_str(msg), 160))
	return valid


def validateOne(rdId, args):
	"""outputs to stdout various information on the RD identified by rdId.
	"""
	rd = loadRD(rdId)
	if rd is None:
		return

	if args.runTests:
		TestsCollector.addRD(rd)

	validSoFar = validateServices(rd, args)
	validSoFar = validSoFar and validateRowmakers(rd, args)
	validSoFar = validSoFar and validateTables(rd, args)
	validSoFar = validSoFar and validateOtherCode(rd, args)
	validSoFar = validSoFar and validateRST(rd, args)
	return validSoFar


def validateAll(args):
	"""validates all accessible RDs.
	"""
	for rdId in publication.findAllRDs():
		if args.verbose:
			sys.stdout.write(rdId+" ")
			sys.stdout.flush()
		try:
			validateOne(rdId, args)
		except Exception:
			sys.stderr.write("Severe error while validating %s:\n"%rdId)
			traceback.print_exc()
	if args.verbose:
		sys.stdout.write("\n")


def parseCommandLine():
	parser = argparse.ArgumentParser(description="Check RDs for well-formedness"
		" and some aspects of VO-friendlyness")
	parser.add_argument("rd", nargs="+", type=str,
		help="RD identifier or file system path.  Use magic value ALL to"
		" check all reachable RDs.")
	parser.add_argument("-p", "--pre-publication", help="Validate"
		" as if all services were IVOA published even if they are not"
		" (this may produce spurious errors if unpublished services are in"
		" the RD).",
		action="store_true", dest="prePublication")
	parser.add_argument("-v", "--verbose", help="Talk while working",
		action="store_true", dest="verbose")
	parser.add_argument("-t", "--run-tests", help="Run regression tests"
		" embedded in the checked RDs", action="store_true", dest="runTests")
	parser.add_argument("-T", "--timeout", help="When running tests, abort"
		" and fail requests after inactivity of SECONDS",
		action="store", dest="timeout", type=int, default=15, metavar="SECONDS")
	parser.add_argument("-c", "--compare-db", help="Also make sure that"
		" tables that are on disk (somewhat) match the definition in the RD.",
		action="store_true", dest="compareDB")
	parser.add_argument("-u", "--accept-free-units", help="Do not warn"
		" against units not listed in VOUnits.",
		action="store_true", dest="acceptFreeUnits")


	return parser.parse_args()


def main():
	base.VALIDATING = True
	args = parseCommandLine()
	if len(args.rd)==1 and args.rd[0]=="ALL":
		validateAll(args)
	else:
		for rd in args.rd:
			print rd, "--",
			sys.stdout.flush()
			if validateOne(rd, args):
				print "OK"
			else:
				print "Fail"
	
	if args.runTests:
		print "\nRunning regression tests\n"
		from gavo.rscdef import regtest
		runner = regtest.TestRunner(TestsCollector.testsToRun,
			verbose=False, timeout=args.timeout)
		runner.runTests(showDots=True)
		print runner.stats.getReport()
		if runner.stats.fails:
			print "\nThe following tests failed:\n"
			print runner.stats.getFailures()
