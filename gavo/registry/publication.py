"""
"Publishing" (i.e. entering into the services table) service records -- 
grammar-type stuff and UI.
"""

import datetime
import os
import sys
import time
import traceback
import warnings

import pkg_resources

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import utils

from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry import staticresource
from gavo.registry.common import *


def makeBaseRecord(service):
	"""returns a dictionary giving the metadata common to all publications
	of a service.
	"""
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["internalId"] = service.id
	rec["title"] = unicode(service.getMeta("title")) or rec["shortName"]
	rec["deleted"] = False
	rec["recTimestamp"] = datetime.datetime.utcnow()
	rec["description"] = unicode(service.getMeta("description"
		) or unicode(service.getMeta("_description")))
	rec["owner"] = service.limitTo
	dateUpdated = service.getMeta("datetimeUpdated")
	if dateUpdated is None:
		rec["dateUpdated"] = datetime.datetime.utcnow()
	else:
		rec["dateUpdated"] = str(dateUpdated)
	return rec


def iterSvcRecs(service):
	"""iterates over records suitable for importing into the service list 
	for service.

	It will yield record(s) for each "publication" (i.e., renderer) and
	for each set therein.  It will then, together with the last publication,
	records for all given subjects are yielded.

	With the forceUnique hacks on the records defined in 
	services.rd#servicetables, this fills every table as desired.  However,
	the whole thing clearly shows we want something more fancy when data
	models get a bit more complex.

	WARNING: you'll get back the same dict every time.  You need to copy
	it if you can't process is between to visits in the iterator.
	"""
	if not service.publications:
		return  # don't worry about missing meta if there are no publications
	# bomb out if service metadata is missing
	base.validateStructure(service)
	rec = makeBaseRecord(service)
	# bomb out if, for some reason, we can't come up with a resource record
	# for this guy
	ignored = builders.getVOResourceElement(service)
	subjects = [str(item) for item in service.getMeta("subject")]
	rec["subject"] = subjects.pop()
	for pub in service.publications:
		rec["renderer"] = pub.render
		rec["accessURL"] = service.getURL(pub.render, absolute=False)
		rec["referenceURL"] = base.getMetaText(service, "referenceURL")
		try:
			rec["browseable"] = service.isBrowseableWith(pub.render)
		except AttributeError:  # service is not a ResourceBasedRenderer
			rec["browseable"] = False
		for setName in pub.sets:
			rec["setName"] = setName
			yield rec
	for subject in subjects:
		rec["subject"] = subject
		yield rec


class ServiceRscIterator(grammars.RowIterator):
	"""is a RowIterator yielding resource records for inclusion into the
	service list for the services defined in the source token RD.
	"""
	def _iterRows(self):
		for svc in self.sourceToken.services:
			self.curSource = svc.id
			for sr in iterSvcRecs(svc):
				yield sr.copy()
	
	def getLocation(self):
		return "%s#%s"%(self.sourceToken.sourceId, self.curSource)


class SvcRscGrammar(grammars.Grammar):
	rowIterator = ServiceRscIterator
_svcRscGrammar = base.makeStruct(SvcRscGrammar)


class StaticRscIterator(grammars.RowIterator):
	"""is a RowIterator yielding resource records for inclusion in the
	service list from static resource definitions.

	The notes on iterSvcRecs apply here as well.
	"""
	def _iterRows(self):
		for rsc in staticresource.iterStaticResources():
			self.curSource = rsc.srcName
			for rec in iterSvcRecs(rsc):
				yield rec

	def getLocation(self):
		return self.curSource


class StaticRscGrammar(grammars.Grammar):
	rowIterator = StaticRscIterator
_staticRscGrammar = base.makeStruct(StaticRscGrammar)


def updateServiceList(rds, metaToo=False, connection=None, onlyWarn=True):
	"""updates the services defined in rds in the services table in the database.
	"""
	recordsWritten = 0
	parseOptions = rsc.getParseOptions(validateRows=True, batchSize=20)
	if connection is None:
		connection = base.getDBConnection("admin")
	dd = getServicesRD().getById("tables")
	dd.grammar = _svcRscGrammar
	msg = None
	for rd in rds:
		if rd.sourceId.startswith("/"):
			raise Error("Resource descriptor ID may not be absolute, but"
				" '%s' seems to be."%rd.sourceId)
		try:
			data = rsc.makeData(dd, forceSource=rd, parseOptions=parseOptions,
				connection=connection)
			recordsWritten += data.nAffected
		except base.MetaValidationError, ex:
			msg = "Aborting publication of '%s' at service '%s':\n * %s"%(
				rd.sourceId, ex.carrier.id, "\n * ".join(ex.failures))
		except base.NoMetaKey, ex:
			msg = ("Aborting publication of '%s' at service '%s': Resource"
				" record generation failed: %s"%(
				rd.sourceId, 'whatever', str(ex)))

		if msg is not None:
			if onlyWarn:
				warnings.warn(msg)
			else:
				raise base.ReportableError(msg)
		msg = None

		if metaToo:
			for dependentDD in rd:
				rsc.Data.create(dependentDD, connection=connection).updateMeta()
	connection.commit()
	return recordsWritten


def importFixed():
	connection = base.getDBConnection("admin")
	rd = base.caches.getRD(STATICRSC_ID)
	dd = rd.getById("tables")
	dd.grammar = _staticRscGrammar
	rsc.makeData(dd, forceSource=rd, parseOptions=rsc.parseValidating,
		connection=connection)
	connection.commit()


################ UI stuff

def findAllRDs():
	"""returns ids of all RDs (inputs and built-in) known to the system.
	"""
	rds = []
	inputsDir = base.getConfig("inputsDir")
	for dir, dirs, files in os.walk(inputsDir):
		for file in files:
			if file.endswith(".rd"):
				rds.append(os.path.splitext(
					utils.getRelativePath(os.path.join(dir, file), inputsDir))[0])
	for name in pkg_resources.resource_listdir('gavo', 
			"resources/inputs/__system__"):
		if name.startswith("."):  # ignore VCS files (and possibly others:-)
			continue
		rds.append(os.path.splitext("__system__/%s"%name)[0])
	return rds


def getRDs(args):
	"""returns a list of RDs from a list of more-or-less RD ids.
	"""
	try:
		return [base.caches.getRD(rdPath, doQueries=False)
			for rdPath in args]
	except:
		sys.stderr.write("Error occurred in %s\n"%rdPath)
		raise


def parseCommandLine():
	import optparse
	parser = optparse.OptionParser(usage="%prog [options] {<rd-name>}")
	parser.add_option("-a", "--all", help="search everything below inputsDir"
		" for publications (implies -f).", dest="all", action="store_true")
	parser.add_option("-m", "--meta-too", help="update meta information, too",
		dest="meta", action="store_true")
	parser.add_option("-f", "--fixed", help="also import fixed records",
		dest="doFixed", action="store_true")
	return parser.parse_args()


def updateRegistryTimestamp():
	"""edits the dateupdated field for the registry service in servicelist.
	"""
	q = base.SimpleQuerier()
	regSrv = getRegistryService()
	q.runIsolatedQuery("UPDATE services SET dateupdated=%(now)s"
		" WHERE sourcerd=%(rdId)s AND internalid=%(sId)s", {
		"rdId": regSrv.rd.sourceId,
		"sId": regSrv.id,
		"now": datetime.datetime.utcnow(),
	})
	q.close()
	getServicesRD().touchTimestamp()


def main():
	"""handles the user interaction for gavopublish.
	"""
	from gavo import rscdesc
	from gavo.protocols import basic
	from gavo import web
	base.setDBProfile("admin")
	opts, args = parseCommandLine()
	getServicesRD().touchTimestamp()
	if opts.all:
		args = findAllRDs()
	updateServiceList(getRDs(args), metaToo=opts.meta)
	if opts.all or opts.doFixed:  # also import fixed registry records
		importFixed()
