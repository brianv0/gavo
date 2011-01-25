"""
The (DC-internal) service list: querying, adding records, etc.
"""

from gavo import base
from gavo import utils
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo.registry.common import *


def getSetsForResource(restup):
	"""returns the list of set names the resource described by restup belongs to.
	"""
	tableDef = getServicesRD().getById("sets")
	table = rsc.TableForDef(tableDef)
	destTableDef = base.makeStruct(rscdef.TableDef,
		columns=[tableDef.getColumnByName("setName")])
	return set(str(r["setName"])
		for r in table.iterQuery(destTableDef, 
			"sourceRD=%(sourceRD)s AND resId=%(resId)s", restup))


def getSets():
	"""returns a sequence of dicts giving setName and and a list of
	services belonging to that set.
	"""
	tableDef = getServicesRD().getById("sets")
	table = rsc.TableForDef(tableDef)
	setMembers = {}
	for rec in table:
		setMembers.setdefault(rec["setName"], []).append(
			(rec["sourceRD"], rec["resId"]))
	return [{"setName": key, "services": value} 
		for key, value in setMembers.iteritems()]


def queryServicesList(whereClause="", pars={}, tableName="resources_join"):
	"""returns a list of services based on selection criteria in
	whereClause.

	The table queried is the resources_join view, and you'll get back all
	fields defined there.
	"""
	td = getServicesRD().getById(tableName)
	otd = svcs.OutputTableDef.fromTableDef(td, None)
	table = rsc.TableForDef(td)
	return [r for r in table.iterQuery(otd, whereClause, pars)]


def querySubjectsList(setName=None):
	"""returns a list of local services chunked by subjects.

	This is mainly for the root page (see web.root).  Query the
	cache using the __system__/services key to clear the cache on services
	"""
	setName = setName or 'local'
	svcsForSubjs = {}
	td = base.caches.getRD(SERVICELIST_ID).getById("subjects_join")
	otd = svcs.OutputTableDef.fromTableDef(td, None)
	for row in rsc.TableForDef(td).iterQuery(otd, 
			"setName=%(setName)s AND subject IS NOT NULL", {"setName": setName}):
		svcsForSubjs.setdefault(row["subject"], []).append(row)
	for s in svcsForSubjs.values():
		s.sort(key=lambda a: a["title"])
	res = [{"subject": subject, "chunk": s}
		for subject, s in svcsForSubjs.iteritems()]
	res.sort(lambda a,b: cmp(a["subject"], b["subject"]))
	return res

base.caches.makeCache("getSubjectsList", 
	lambda ignored: querySubjectsList())


def getChunkedServiceList(setName=None):
	"""returns a list of local services chunked by title char.

	This is mainly for the root page (see web.root).  Query the
	cache using the __system__/services key to clear the cache on services
	reload.
	"""
	setName = setName or 'local'
	return utils.chunk(
		sorted(queryServicesList("setName=%(setName)s and not deleted", 
			{"setName": setName}), 
			key=lambda s: s.get("title").lower()),
		lambda srec: srec.get("title", ".")[0].upper())

base.caches.makeCache("getChunkedServiceList", 
	lambda ignored: getChunkedServiceList())


def cleanServiceTablesFor(rd, connection):
	"""removes/invalidates all entries originating from rd from the service
	tables.
	"""
# this is a bit of a hack: We're running services#tables' newSource
#	skript without then importing anything new.
	tables = rsc.Data.create(
		getServicesRD().getById("tables"),
		connection=connection)
	tables.runScripts("newSource", sourceToken=rd)

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
	res = q.query("SELECT sourceRD FROM dc.tablemeta WHERE"
			" tableName=%(tableName)s", {"tableName": tableName}).fetchall()
	q.close()
	if len(res)!=1:
		raise base.NotFoundError(tableName, what="Table",
			within="data center table listing.", hint="The table is missing from"
			" the dc.tablemeta table.  This gets filled at gavoimp time.")
	rdId = res[0][0]
	return base.caches.getRD(rdId).getById(basename(tableName))
