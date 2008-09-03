"""
Code dealing with the service list.
"""

import grp
import os
import sys
import traceback
import urlparse

import gavo
from gavo import config
from gavo import resourcecache
from gavo import sqlsupport
from gavo import utils
from gavo.parsing import parseswitch
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import typeconversion
from gavo.web import staticresource

from gavo.web.staticresource import rdId


class MissingMeta(gavo.Error):
	def __init__(self, msg, fields):
		gavo.Error.__init__(self, msg)
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
		except gavo.MetaError:
			missingKeys.append(key)
	if missingKeys:
		raise MissingMeta("Missing meta keys", missingKeys)


def makeBaseRecord(service):
	"""returns a dictionary giving the metadata common to all publications
	of a service.
	"""
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["internalId"] = service.get_id()
	rec["title"] = unicode(service.getMeta("title")) or rec["shortName"]
	rec["description"] = unicode(service.getMeta("description"
		) or unicode(service.getMeta("_description")))
	rec["owner"] = service.get_requiredGroup()
	return rec

def iterSvcRecs(service):
	"""iterates over a records suitable for importing into the service list 
	for service.

	It will yield record(s) for each "publication" (i.e., renderer) and
	for each set therein.  It will then, together with the last publication,
	records for all given subjects are yielded.

	With the forceUnique hacks on the records defined in 
	services.vord#servicetables, this fills every table as desired.  However,
	the whole thing clearly shows we want something more fancy when data
	models get a bit more complex.

	WARNING: you'll get back the same dict every time.  You need to copy
	it if you can't process is between to visits in the iterator.
	"""
	if not service.get_publications():
		return  # don't worry about missing meta if there are not publications
	ensureSufficientMeta(service)
	rec = makeBaseRecord(service)
	subjects = [str(item) for item in service.getMeta("subject")]
	rec["subject"] = subjects.pop()
	for pub in service.get_publications():
		rec["renderer"] = pub["render"]
		rec["accessURL"] = service.getURL(pub["render"])
		sets = set([s.strip() for s in pub.get("sets", "").split(",")])
		for setName in sets:
			rec["setName"] = setName
			yield rec
	for subject in subjects:
		rec["subject"] = subject
		yield rec


def getServiceRecsFromRd(rd):
	"""returns all service records defined in the resource descriptor rd.
	"""
	for svcId in rd.itemsof_service():
		svc = rd.get_service(svcId)
		for sr in iterSvcRecs(svc):
			yield sr.copy()


def updateServiceList(rd):
	"""updates the services defined in rd in the services table in the database.
	"""
	# Don't use resourcecache here since we're going to mess with the rd
	from gavo.parsing import importparser
	serviceRd = importparser.getRd(rdId, forImport=True)
	dd = serviceRd.getDataById("servicelist")
	serviceRd.register_property("srcRdId", rd.sourceId)
	inputData = sqlsupport.makeRowsetFromDicts(
		list(getServiceRecsFromRd(rd)), dd.get_Grammar().get_dbFields())
	gavo.ui.silence = True
	dataSet = resource.InternalDataSet(dd, tableMaker=parseswitch.createTable,
		dataSource=inputData)
	dataSet.exportToSQL(serviceRd.get_schema())
	gavo.ui.silence = False


def getShortNamesForSets(queriedSets):
	"""returns the list of service shortNames that are assigned to any of
	the set names mentioned in the list queriedSets.
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryTableDef()
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(
		"SELECT * FROM %s WHERE setName in %%(sets)s"%(tableDef.get_table()),
		{"sets": queriedSets})
	return [str(r["shortName"]) for r in
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getSetsForService(shortName):
	"""returns the list of set names the service shortName belongs to.
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryTableDef()
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(
		"SELECT * FROM %s WHERE shortName = %%(name)s"%(tableDef.get_table()),
		{"name": shortName})
	return [str(r["setName"]) for r in 
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getSets():
	"""returns a sequence of records for the known sets.  
	
	Right now, the records have the keys setName and services (containing
	the short names of the services that are in the set).
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryTableDef()
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(
		"SELECT * FROM %s"%(tableDef.get_table()))
	setMembers = {}
	for rec in resource.InternalDataSet(dd, dataSource=data
			).getPrimaryTable().rows:
		setMembers.setdefault(rec["setName"], []).append(rec["shortName"])
	return [{"setName": key, "services": value} 
		for key, value in setMembers.iteritems()]


def queryServicesList(whereClause="", pars={}, source="services"):
	"""returns a list of services based on selection criteria in
	whereClause

	Source is either resources, resSet, or services (actually,
	any data in services.vord will do).  If you query for resSet,
	no record will show up that has no set assigned.  If you query
	for services, resources without interfaces will not be shown.
	"""
	rd = resourcecache.getRd(rdId)
	dd = rd.getDataById(source).copy()
	grammar = dd.get_Grammar()
	sources = [f.get_source() for f in grammar.get_items()]
	tables = set([s.split(".")[0] for s in sources])
	if whereClause:
		whereClause = "WHERE "+whereClause
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(
		"SELECT %s FROM %s %s"%(
			",".join(sources),
			" NATURAL JOIN ".join(tables),
			whereClause), pars)
	res = resource.InternalDataSet(dd, dataSource=data).getPrimaryTable()
	return res.rows

resourcecache.makeCache("getWebServiceList", 
	lambda ignored: queryServicesList("srv_sets.setName='local'"))


# XXX Replace using ADQL
def querySubjectsList():
	"""returns a list of local services chunked by subjects.
	"""
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(
		"select subject, title, owner, accessURL from"
		" srv_subjs_join")
	reg = {}
	for subject, title, owner, accessURL in data:
		reg.setdefault(subject, []).append(({"title": title, 
			"owner": owner, "accessURL": accessURL}))
	for svcs in reg.values():
		svcs.sort(lambda a,b: cmp(a["title"], b["title"]))
	res = [{"subject": subject, "chunk": svcs}
		for subject, svcs in reg.iteritems()]
	res.sort(lambda a,b: cmp(a["subject"], b["subject"]))
	return res

resourcecache.makeCache("getSubjectsList", 
	lambda ignored: querySubjectsList())



def getResourceForRec(rec):
	"""returns a "resource" for the record rec.

	rec at least has to contain the sourceRd and internalId fields.

	The item that is being returned is either a service or a StaticResource
	object.  All of these have a getMeta method and should be able to
	return the standard DC metadata.  Everything else depends on the type
	of StaticResource.
	"""
	sourceRd, internalId = rec["sourceRd"], rec["internalId"]
	if sourceRd==rdId:
		return staticresource.loadStaticResource(internalId)
	else:
		return resourcecache.getRd(sourceRd).get_service(internalId)


def parseCommandLine():
	import optparse
	parser = optparse.OptionParser(usage="%prog [options] {<rd-name>}")
	parser.add_option("-a", "--all", help="search everything below inputsDir"
		" for publications (implies -f).", dest="all", action="store_true")
	parser.add_option("-f", "--fixed", help="also import fixed records"
		" (this is equivalent to gavoimp services).", dest="doFixed",
		action="store_true")
	return parser.parse_args()


def findAllRDs():
	rds = []
	for dir, dirs, files in os.walk(config.get("inputsDir")):
		for file in files:
			if file.endswith(".vord"):
				rds.append(os.path.join(dir, file))
	return rds


def getStateFileName():
	return os.path.join(config.get("stateDir"), "lastGavopub.stamp")


def getLastRegistryUpdate():
	"""returns the timestamp of the last update of the registry.
	"""
	try:
		return os.path.getmtime(getStateFileName())
	except os.error:
		gavo.logger.error("No registry timestamp found.  Returning conservative"
			" modification date")
		return 946681200.0  # 2000-01-01T00:00:00Z


def touchStateFile():
	fn = getStateFileName()
	try: os.unlink(fn)
	except os.error: pass
	f = open(fn, "w")
	f.write("\n")
	f.close()
	os.chmod(fn, 0664)
	try:
		os.chown(fn, -1, grp.getgrnam(config.get("GavoGroup")[2]))
	except (KeyError, os.error):
		pass


def importFixed():
	"""imports the fixed records.

	This is more or less equivalent to gavoimp __system__/services/services.
	"""
	from gavo.parsing import importparser
	gavo.ui.silence = True
	rd = importparser.getRd(rdId)
	res = resource.Resource(rd)
	res.importData(None)
	res.exportToSQL()
	gavo.ui.silence = False


def main():
	"""handles the user interaction for gavopublish.
	"""
	from gavo import textui
	config.setDbProfile("admin")
	from gavo.parsing import importparser
	opts, args = parseCommandLine()
	if opts.all:
		args = findAllRDs()
	for rdPath in args:
		sys.stdout.write("Processing %s..."%(rdPath))
		sys.stdout.flush()
		try:
			updateServiceList(
				importparser.getRd(os.path.join(os.getcwd(), rdPath), 
					forImport=True, noQueries=True))
		except Exception, msg:
			print "Ignoring.  See the log for a traceback."
			gavo.logger.error("Ignoring for service export: %s (%s)"%(
				rdPath, repr(str(msg))), exc_info=True)
		print
	if opts.all or opts.doFixed:  # also import fixed registry records
		importFixed()
	try:
		touchStateFile()
	except (IOError, os.error):
		traceback.print_exc()
		sys.stderr.write("Couldn't touch state file %s.  Please fix by hand.\n"%
			getStateFileName())


if __name__=="__main__":
	from gavo import textui
	import pprint
	config.setDbProfile("trustedquery")
	from gavo.parsing import importparser
	pprint.pprint(getSets())
