"""
Code dealing with the service list.
"""

import grp
import os
import sys
import traceback

import gavo
from gavo import config
from gavo import resourcecache
from gavo import sqlsupport
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
# built XXX TODO: Check for their presence when ivoa_managed is in sets.
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
		except config.MetaError:
			missingKeys.append(key)
	if missingKeys:
		raise MissingMeta("Missing meta keys", missingKeys)


def makeRecord(publication, service):
	"""returns a record suitable for importing into the service list for the
	publication type of service.
	"""
	ensureSufficientMeta(service)
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["internalId"] = service.get_id()
	rec["title"] = (str(service.getMeta("title") or service.getMeta("_title"))
		or rec["shortName"])
	rec["description"] = str(service.getMeta("description") or service.getMeta(
		"_description"))
	rec["renderer"] = publication["render"]
	rec["accessURL"] = service.getURL(publication["render"])
	rec["owner"] = service.get_requiredGroup()
	rec["type"] = publication["type"]
	rec["sets"] = service.getMeta("sets")
	if rec["sets"]:
		rec["sets"] = str(rec["sets"])
	return rec


def getServiceRecsFromRd(rd):
	"""returns all service records defined in the resource descriptor rd.
	"""
	res = []
	for svcId in rd.itemsof_service():
		svc = rd.get_service(svcId)
		for pub in svc.get_publications():
			try:
				res.append(makeRecord(pub, svc))
			except MissingMeta, err:
				sys.stderr.write("%s in %s is missing the required meta field(s) %s."
					"  Skipping.\n"%(svc.get_id(), svc.rd.sourceId, 
					", ".join(err.fields)))
	return res


def updateServiceList(rd):
	"""updates the services defined in rd in the services table in the database.
	"""
	# Don't use resourcecache here since we're going to mess with the rd
	from gavo.parsing import importparser
	serviceRd = importparser.getRd(rdId, forImport=True)
	dd = serviceRd.getDataById("servicelist")
	serviceRd.register_property("srcRdId", rd.sourceId)
	inputData = sqlsupport.makeRowsetFromDicts(
		getServiceRecsFromRd(rd), dd.get_Grammar().get_dbFields())
	gavo.ui.silence = True
	dataSet = resource.InternalDataSet(dd, tableMaker=parseswitch.createTable,
		dataSource=inputData)
	dataSet.exportToSql(serviceRd.get_schema())
	gavo.ui.silence = False


def getShortNamesForSets(queriedSets):
	"""returns the list of service shortNames that are assigned to any of
	the set names mentioned in the list queriedSets.
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryRecordDef()
	data = sqlsupport.SimpleQuerier().query(
		"SELECT * FROM %s WHERE setName in %%(sets)s"%(tableDef.get_table()),
		{"sets": queriedSets}).fetchall()
	return [str(r["shortName"]) for r in
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getSetsForService(shortName):
	"""returns the list of set names the service shortName belongs to.
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryRecordDef()
	data = sqlsupport.SimpleQuerier().query(
		"SELECT * FROM %s WHERE shortName = %%(name)s"%(tableDef.get_table()),
		{"name": shortName}).fetchall()
	return [str(r["setName"]) for r in 
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getSets():
	"""returns a sequence of records for the known sets.  
	
	Right now, the records have the keys setName and services (containing
	the short names of the services that are in the set).
	"""
	dd = resourcecache.getRd(rdId).getDataById("sets")
	tableDef = dd.getPrimaryRecordDef()
	data = sqlsupport.SimpleQuerier().query(
		"SELECT * FROM %s"%(tableDef.get_table())).fetchall()
	setMembers = {}
	for rec in resource.InternalDataSet(dd, dataSource=data
			).getPrimaryTable().rows:
		setMembers.setdefault(rec["setName"], []).append(rec["shortName"])
	return [{"setName": key, "services": value} 
		for key, value in setMembers.iteritems()]


def getMatchingServices(whereClause="", pars={}):
	"""queries the services table.
	"""
	dd = resourcecache.getRd(rdId).getDataById("servicelist")
	return resource.getMatchingData(dd, "services", 
		whereClause, pars).getPrimaryTable()


def queryServicesList(whereClause="", pars={}):
	"""returns the current list of form based services.

	This is mainly for the benefit of the portal page.
	"""
	rd = resourcecache.getRd(rdId)
	dd = rd.getDataById("services").copy()
	grammar = dd.get_Grammar()
	sources = [f.get_source() for f in grammar.get_items()]
	tables = set([s.split(".")[0] for s in sources])
	if whereClause:
		whereClause = "WHERE "+whereClause
	data = sqlsupport.SimpleQuerier().query(
		"SELECT %s FROM %s %s"%(
			",".join(sources),
			" NATURAL JOIN ".join(tables),
			whereClause), pars).fetchall()
	return resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows

resourcecache.makeCache("getWebServiceList", 
	lambda ignored: queryServicesList("srv_interfaces.type='web'"))


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
	parser = optparse.OptionParser(usage="%prog [options] [<rd-name>]+")
	parser.add_option("-a", "--all", help="search everything below inputsDir"
		" for publications.", dest="all", action="store_true")
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


def main():
	"""handles the user interaction for gavopublish.
	"""
	from gavo import textui
	from gavo.parsing import commandline
	config.setDbProfile("feed")
	from gavo.parsing import importparser
	opts, args = parseCommandLine()
	if opts.all:
		args = findAllRDs()
	for rdPath in args:
		try:
			updateServiceList(
				importparser.getRd(os.path.join(os.getcwd(), rdPath), 
					forImport=True))
		except Exception, msg:
			commandline.displayError(msg)
	try:
		touchStateFile()
	except (IOError, os.error):
		traceback.print_exc()
		sys.stderr.write("Couldn't touch state file %s.  Please fix by hand.\n"%
			getStateFileName())


if __name__=="__main__":
	from gavo import textui
	import pprint
	config.setDbProfile("querulator")
	from gavo.parsing import importparser
	pprint.pprint(getSets())
