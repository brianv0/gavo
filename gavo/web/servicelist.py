"""
Code dealing with the service list.
"""

import gavo
from gavo import config
from gavo import resourcecache
from gavo import sqlsupport
from gavo.parsing import importparser
from gavo.parsing import parseswitch
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import typeconversion

def makeRecord(publication, service):
	"""returns a record suitable for importing into the service list for the
	publication type of service.
	"""
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["title"] = (str(service.getMeta("title") or service.getMeta("_title"))
		or rec["shortName"])
	rec["description"] = str(service.getMeta("description") or service.getMeta(
		"_description"))
	rec["renderer"] = publication["render"]
	rec["accessURL"] = "".join([
		config.get("web", "serverURL"),
		config.get("web", "nevowRoot"),
		"/",
		service.rd.sourceId,
		"/",
		service.get_id(),
		"/",
		publication["render"]])
	rec["owner"] = service.get_requiredGroup()
	rec["type"] = publication["type"]
	rec["sets"] = str(service.getMeta("sets"))
	if not rec["sets"]:
		rec["sets"] = "local"
	return rec


def getServiceRecsFromRd(rd):
	"""returns all service records defined in the resource descriptor rd.
	"""
	res = []
	for svcId in rd.itemsof_service():
		svc = rd.get_service(svcId)
		for pub in svc.get_publications():
			res.append(makeRecord(pub, svc))
	return res


def updateServiceList(rd):
	"""updates the services defined in rd in the services table in the database.
	"""
	# Don't use resourcecache here since we're going to mess with the rd
	serviceRd = importparser.getRd("__system__/services/services", 
		forImport=True)
	dd = serviceRd.getDataById("servicelist")
	serviceRd.register_property("srcRdId", rd.sourceId)
	inputData = sqlsupport.makeRowsetFromDicts(
		getServiceRecsFromRd(rd), dd.get_Grammar().get_dbFields())
	dataSet = resource.InternalDataSet(dd, tableMaker=parseswitch.createTable,
		dataSource=inputData)
	dataSet.exportToSql(serviceRd.get_schema())


def queryServicesList(whereClause="", pars={}):
	"""returns the current list or form based service. 
	"""
	rd = resourcecache.getRd("__system__/services/services")
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


def main():
	import os
	import sys
	from gavo import textui
	from gavo.parsing import commandline
	config.setDbProfile("feed")
	try:
		updateServiceList(
			importparser.getRd(os.path.join(os.getcwd(), sys.argv[1]), 
				forImport=True))
	except Exception, msg:
		commandline.displayError(msg)


if __name__=="__main__":
	from gavo import textui
	import pprint
	config.setDbProfile("querulator")
	pprint.pprint(queryServicesList())
