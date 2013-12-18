"""
A cli-facing module providing functionality to "validate" one or more
resource descriptors.

Validation means giving some prognosis as to whether RD will properly work 
within both the DC and the VO.
"""

import re
import sys

from gavo import base
from gavo import rsc
from gavo import rscdesc
from gavo import stc
from gavo.helpers import testtricks
from gavo.imp import argparse
from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry import publication
from gavo.user import errhandle


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
		rd = rscdesc.openRD(rdId)
	except base.RDNotFound:
		outputError(rdId, "Could not be located")
	except base.LiteralParseError, ex:
		outputError(rdId, "Bad literal in RD, message follows", True)
	except base.StructureError, ex:
		outputError(rdId, "Malformed RD input, message follows", True)
	except base.Error, ex:
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
		if not svc.publications:  
			continue
		try:
			base.validateStructure(svc)
		except base.MetaValidationError, ex:
			validSoFar = False
			outputWarning(rd.sourceId, "Missing metadata for publication of"
				" service %s:\n%s"%(svc.id, str(ex)))
			continue # further checks will just add verbosity

		if not isIVOPublished(svc):
			# require sane metadata only if the VO will see the service
			continue
		svcId = base.getMetaText(svc, "identifier")
		registryRecord = None
		try:
			registryRecord = builders.getVORMetadataElement(svc)
		except stc.STCSParseError, msg:
			validSoFar = False
			outputWarning(rd.sourceId, "Invalid STC-S (probably in coverage meta)"
				": %s"%str(msg))
		except:
			validSoFar = False
			outputWarning(rd.sourceId, "Error when producing registry record"
				" of service %s:"%svc.id, True)

		if args.doXSD and registryRecord and base.getConfig("xsdclasspath"):
			try:
				_XSD_VALIDATOR.assertValidates(
					registryRecord.render(), leaveOffending=True)
			except AssertionError, msg:
				validSoFar = False
				outputWarning(rd.sourceId, "Invalid registry record for service"
					" %s:\n%s"%(svc.id, str(msg)))

	return validSoFar


def validateRowmakers(rd, args):
	"""tries to build all rowmakers mentioned in the RD and bails out
	if one is bad.
	"""
	for dd in rd:
		for m in dd.makes:
			m.table.onDisk = False
			try:
				rawTable = rsc.TableForDef(m.table)
				m.rowmaker.compileForTableDef(m.table)
			finally:
				m.table.onDisk = True
	return True


def validateTables(rd, args):
	"""does some sanity checks on the (top-level) tables within rd.
	"""
	valid = True

	for td in rd.tables:
		for col in td:
			try:
				if col.unit:
					base.parseUnit(col.unit)
			except base.BadUnit:
				valid = False
				outputError(rd.sourceId, "Bad unit in table %s, column %s: %s"%(
					td.getQName(), col.name, col.unit))

	return valid


def validateOne(rdId, args):
	"""outputs to stdout various information on the RD identified by rdId.
	"""
	rd = loadRD(rdId)

	if args.runTests:
		TestsCollector.addRD(rd)

	if rd is None:
		return
	validSoFar = validateServices(rd, args)
	validSoFar = validSoFar and validateRowmakers(rd, args)
	validSoFar = validSoFar and validateTables(rd, args)
	return validSoFar


def validateAll(args):
	"""validates all accessible RDs.
	"""
	for rdId in publication.findAllRDs():
		if args.verbose:
			sys.stdout.write(rdId+" ")
			sys.stdout.flush()
		validateOne(rdId, args)
	if args.verbose:
		sys.stdout.write("\n")


def parseCommandLine():
	parser = argparse.ArgumentParser(description="Check RDs for well-formedness"
		" and some aspects of VO-friendlyness")
	parser.add_argument("rd", nargs="+", type=str,
		help="RD identifier or file system path.  Use magic value ALL to"
		" check all reachable RDs.")
	parser.add_argument("-x", "--check-xsd", help="Do schema validation"
		" of registry record (requires extra software, see docs)",
		action="store_true", dest="doXSD")
	parser.add_argument("-v", "--verbose", help="Talk while working",
		action="store_true", dest="verbose")
	parser.add_argument("-t", "--run-tests", help="Run regression tests"
		" embedded in the checked RDs", action="store_true", dest="runTests")
	return parser.parse_args()


def main():
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
			verbose=False)
		runner.runTests(showDots=True)
		print runner.stats.getReport()
		if runner.stats.fails:
			print "\nThe following tests failed:\n"
			print runner.stats.getFailures()
