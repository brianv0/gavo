"""
Code dealing with the service list.
"""

import datetime
import os
import sys
import time
import traceback
import urlparse
import warnings

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.registry import staticresource
from gavo.registry.common import *


# XXX TODO: Refactor -- there's grammar-type, servicelist querying, and
# command line stuff in here that should each go in a separate module.

class Error(base.Error):
	pass

class MissingMeta(Error):
	def __init__(self, msg, fields):
		Error.__init__(self, msg)
		self.fields = fields


# These keys must be present to ensure a valid VOResource record can be
# built.
_voRequiredMeta = [
	"title",
	"creationDate", 
	"description", 
	"subject", 
#	"referenceURL", (would be necessary, but we default to service URL
	"shortName", # actually, that's in just because we need it.
]


def ensureSufficientMeta(service):
	"""raises an MissingMeta if metadata absolutely necessary for registration
	is missing from the service.
	"""
	missingKeys = []
	for key in _voRequiredMeta:
		try:
			service.getMeta(key, raiseOnFail=True)
		except base.MetaError:
			missingKeys.append(key)
	if missingKeys:
		raise MissingMeta("Missing meta keys in %s#%s: %s"%(service.rd.sourceId, 
			service.id, missingKeys), missingKeys)


def makeBaseRecord(service):
	"""returns a dictionary giving the metadata common to all publications
	of a service.
	"""
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["internalId"] = service.id
	rec["title"] = unicode(service.getMeta("title")) or rec["shortName"]
	rec["description"] = unicode(service.getMeta("description"
		) or unicode(service.getMeta("_description")))
	rec["owner"] = service.limitTo
	dateUpdated = service.getMeta("datetimeUpdated")
	if dateUpdated is not None:
		rec["dateUpdated"] = datetime.datetime(
			*time.strptime(str(dateUpdated), utils.isoTimestampFmt)[:3])
	else:
		rec["dateUpdated"] = datetime.datetime.utcnow()
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
		return  # don't worry about missing meta if there are not publications
	ensureSufficientMeta(service)
	rec = makeBaseRecord(service)
	subjects = [str(item) for item in service.getMeta("subject")]
	rec["subject"] = subjects.pop()
	for pub in service.publications:
		rec["renderer"] = pub.render
		rec["accessURL"] = service.getURL(pub.render, absolute=False)
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


def cleanServiceTablesFor(targetRDId, connection):
	"""deletes all entries coming from targetRDId in the service tables.
	"""
# XXX TODO: think about script type="newSource" for this kind of situation
# -- or do we want a special mechanism similar to owningCondition of old?
	for td in getServicesRD().getById("tables"):
		rsc.TableForDef(td, connection=connection).deleteMatching(
			"sourceRD=%(sourceRD)s", {"sourceRD": targetRDId})


def updateServiceList(rds, metaToo=False, connection=None):
	"""updates the services defined in rds in the services table in the database.
	"""
	parseOptions = rsc.getParseOptions(validateRows=True, batchSize=20)
	if connection is None:
		connection = base.getDBConnection("admin")
	dd = getServicesRD().getById("tables")
	dd.grammar = _svcRscGrammar
	for rd in rds:
		if rd.sourceId.startswith("/"):
			raise Error("Resource descriptor ID may not be absolute, but"
				" '%s' seems to be."%rd.sourceId)
		cleanServiceTablesFor(rd.sourceId, connection)
		rsc.makeData(dd, forceSource=rd, parseOptions=parseOptions,
			connection=connection)
		if metaToo:
			for dependentDD in rd:
				rsc.Data.create(dependentDD, connection=connection).updateMeta()
	connection.commit()


def importFixed():
	connection = base.getDBConnection("admin")
	cleanServiceTablesFor(STATICRSC_ID, connection)

	dd = base.caches.getRD(STATICRSC_ID).getById("tables")
	dd.grammar = _staticRscGrammar
	rsc.makeData(dd, forceSource=object, parseOptions=rsc.parseValidating,
		connection=connection)
	connection.commit()


############# query functions

def getShortNamesForSets(queriedSets):
	"""returns the list of service shortNames that are assigned to any of
	the set names mentioned in the list queriedSets.
	"""
	tableDef = getServicesRD().getById("srv_sets")
	table = rsc.TableForDef(tableDef)
	destTableDef = rscdef.TableDef(None, columns=[tableDef.getColumnByName(
		"shortName")])
	return [str(r["shortName"])
		for r in table.iterQuery(destTableDef, "setName IN %(sets)s",
		{"sets": queriedSets})]


def getSetsForService(shortName):
	"""returns the list of set names the service shortName belongs to.
	"""
	tableDef = getServicesRD().getById("srv_sets")
	table = rsc.TableForDef(tableDef)
	destTableDef = base.makeStruct(rscdef.TableDef,
		columns=[tableDef.getColumnByName("setName")])
	return set(str(r["setName"])
		for r in table.iterQuery(destTableDef, "shortName=%(name)s",
		{"name": shortName}))


def getSets():
	"""returns a sequence of dicts giving setName and and a list of
	services belonging to that set.
	"""
	tableDef = getServicesRD().getById("srv_sets")
	table = rsc.TableForDef(tableDef)
	setMembers = {}
	for rec in table:
		setMembers.setdefault(rec["setName"], []).append(rec["shortName"])
	return [{"setName": key, "services": value} 
		for key, value in setMembers.iteritems()]


def queryServicesList(whereClause="", pars={}, tableName="srv_join"):
	"""returns a list of services based on selection criteria in
	whereClause.

	The table queried is the srv_join view, and you'll get back all
	fields defined there.
	"""
	td = getServicesRD().getById(tableName)
	otd = svcs.OutputTableDef.fromTableDef(td)
	table = rsc.TableForDef(td)
	return [r for r in table.iterQuery(otd, whereClause, pars)]

base.caches.makeCache("getWebServiceList", 
	lambda ignored: queryServicesList("setName='local'"))


def querySubjectsList():
	"""returns a list of local services chunked by subjects.
	"""
	svcsForSubjs = {}
	td = base.caches.getRD(SERVICELIST_ID).getById("srv_subjs_join")
	otd = svcs.OutputTableDef.fromTableDef(td)
	for row in rsc.TableForDef(td).iterQuery(otd, ""):
		svcsForSubjs.setdefault(row["subject"], []).append(row)
	for s in svcsForSubjs.values():
		s.sort(lambda a,b: cmp(a["title"], b["title"]))
	res = [{"subject": subject, "chunk": s}
		for subject, s in svcsForSubjs.iteritems()]
	res.sort(lambda a,b: cmp(a["subject"], b["subject"]))
	return res

base.caches.makeCache("getSubjectsList", 
	lambda ignored: querySubjectsList())


def basename(tableName):
	if "." in tableName:
		return tableName.split(".")[-1]
	else:
		return tableName


def getTableDef(tableName):
	"""returns a tableDef instance for the schema-qualified tableName.

	If no such table is known to the system, a NotFoundError is raised.
	"""
	q = base.SimpleQuerier()
	res = q.query("SELECT sourceRd FROM dc.tablemeta WHERE"
			" tableName=%(tableName)s", {"tableName": tableName}).fetchall()
	q.close()
	if len(res)!=1:
		raise base.NotFoundError(
			"%s is no accessible table in the data center"%tableName,
			tableName, "table")
	rdId = res[0][0]
	return base.caches.getRD(rdId).getById(basename(tableName))


################ UI stuff

def findAllRDs():
	"""returns all RDs in inputsDir.

	System RDs are not returned.
	"""
	rds = []
	for dir, dirs, files in os.walk(base.getConfig("inputsDir")):
		for file in files:
			if file.endswith(".rd"):
				rds.append(os.path.join(dir, file))
	return rds


def getRDs(args):
	"""returns a list of RDs from a list of more-or-less RD ids.
	"""
	return [base.caches.getRD(rdPath, doQueries=False)
		for rdPath in args]


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
		"now": datetime.datetime.now(),
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


if __name__=="__main__":
	from gavo import rscdesc
	from gavo.protocols import basic
	import pprint
	print findAllRDs()
