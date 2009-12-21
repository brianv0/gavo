"""
Code dealing with the service list.
"""

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo.registry import staticresource
from gavo.registry.common import *


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
		raise base.NotFoundError(tableName, what="Table",
			within="data center table listing.", hint="The table is missing from"
			" the dc.tablemeta table.  This gets filled at gavoimp time.")
	rdId = res[0][0]
	return base.caches.getRD(rdId).getById(basename(tableName))
