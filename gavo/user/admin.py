"""
DC administration interface.
"""

import os
import sys

from gavo import base
from gavo import rscdesc  # (register getRD)
from gavo.user.common import Arg, exposedFunction, makeParser
from gavo.protocols import uws


class ArgError(base.Error):
	pass


@exposedFunction([
	Arg("user", help="the user name"),
	Arg("password", help="a password for the user"),
	Arg("remarks", help="optional remarks", 
		default="", nargs='?')],
	help="add a user/password pair and a matching group to the DC server")
def adduser(querier, args):
	try:
		querier.query("INSERT INTO dc.users (username, password, remarks)"
			" VALUES (%(user)s, %(password)s, %(remarks)s)", args.__dict__)
	except base.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s already exists."
			"  Use 'changeuser' command to edit."%args.user))
	querier.query("INSERT INTO dc.groups (username, groupname)"
		" VALUES (%(user)s, %(user)s)", args.__dict__)


@exposedFunction([
	Arg("user", help="the user name to remove")],
	help="remove a user from the DC server")
def deluser(querier, args):
	c = querier.query("DELETE FROM dc.users WHERE username=%(user)s",
		args.__dict__)
	rowsAffected = c.rowcount
	c = querier.query("DELETE FROM dc.groups WHERE username=%(user)s",
		args.__dict__)
	rowsAffected += c.rowcount
	if not rowsAffected:
		sys.stderr.write("Warning: No rows deleted while deleting user %s\n"%
			args.user)


@exposedFunction([
	Arg("user", help="the user name"),
	Arg("password", help="a password for the user"),
	Arg("remarks", help="optional remarks", 
		default="", nargs='?')],
	help="change remarks and/or password for a DC user")
def changeuser(querier, args):
		if args.remarks is None:
			c = querier.query("UPDATE dc.users SET password=%(password)s"
			" WHERE username=%(user)s", args.__dict__)
		else:
			c = querier.query("UPDATE dc.users SET password=%(password)s,"
			" remarks=%(remarks)s WHERE username=%(user)s", args.__dict__)
		if not c.rowcount:
			sys.stderr.write("Warning: No rows changed for user %s\n"%args.user)


@exposedFunction([
	Arg("user", help="a user name"),
	Arg("group", help="the group to add the user to")],
	help="add a user to a group")
def addtogroup(querier, args):
	try:
		querier.query("INSERT INTO dc.groups (username, groupname)"
			" VALUES (%(user)s, %(group)s)", args.__dict__)
	except sqlsupport.IntegrityError:
		raise base.ui.logOldExc(ArgError("User %s doesn't exist."%args.user))


@exposedFunction([
	Arg("user", help="a user name"),
	Arg("group", help="the group to remove the user from")],
	help="remove a user from a group")
def delfromgroup(querier, args):
	c = querier.query("DELETE FROM dc.groups WHERE groupname=%(group)s"
		" and username=%(user)s", args.__dict__)
	if not c.rowcount:
		sys.stderr.write("Warning: No rows deleted while deleting user"
			" %s from group %s\n"%(args.user, args.group))


@exposedFunction(help="list users known to the DC")
def listusers(querier, args):
	data = querier.query("SELECT username, groupname, remarks"
		" FROM dc.users NATURAL JOIN dc.groups ORDER BY username").fetchall()
	curUser = None
	for user, group, remark in data:
		if user!=curUser:
			print "\n%s (%s) --"%(user, remark),
			curUser = user
		print group,
	print


@exposedFunction([
	Arg("-f", help="also remove all jobs in ERROR and ABORTED states (only use"
		" if you are sure what you are doing).", action="store_true",
		dest="includeFailed"),
	Arg("-p", help="also remove all jobs in PENDING states (only use"
		" if you are sure what you are doing).", action="store_true",
		dest="includeForgotten"),
	Arg("--all", help="remove all jobs (this is extremely unfriendly."
		"  Don't use this on public UWSes)", action="store_true",
		dest="includeAll"),
	Arg("--nuke-completed", help="also remove COMPLETEd jobs (this is"
		" unfriendly.  Don't do this on public UWSes).", action="store_true",
		dest="includeCompleted"),],
	help="remove expired UWS jobs")
def cleanuws(querier, args):
	uws.cleanupJobsTable(includeFailed=args.includeFailed,
		includeCompleted=args.includeCompleted,
		includeAll=args.includeAll,
		includeForgotten=args.includeForgotten)


@exposedFunction(help="Re-import column information from all RDs"
	" (incl. TAP_SCHEMA; like gavo imp -m <all rds>)")
def allcols(querier, args):
	from gavo import registry
	from gavo import rsc
	from gavo import rscdesc
	from gavo.protocols import tap

	for rdId in registry.findAllRDs():
		rd = base.caches.getRD(rdId)
		tap.unpublishFromTAP(rd, querier.connection)
		for dd in rd:
			rsc.Data.create(dd, connection=querier.connection).updateMeta()
		tap.publishToTAP(rd, querier.connection)


@exposedFunction([Arg(help="identifier of the deleted service",
		dest="svcId")],
	help="Declare an identifier as deleted (for when"
	" you've removed the RD but the identifier still floats on"
	" some registries)")
def declaredel(querier, args):
	import datetime

	from gavo import registry
	from gavo import rsc

	authority, path = registry.parseIdentifier(args.svcId)
	if authority!=base.getConfig("ivoa", "authority"):
		raise base.ReportableError("You can only declare ivo ids from your"
			" own authority as deleted.")
	idParts = path.split("/")
	svcsRD = base.caches.getRD("//services")

	# mark in resources table
	resTable = rsc.TableForDef(svcsRD.getById("resources"),
		connection=querier.connection)
	newRow = resTable.tableDef.getDefaults()
	newRow["sourceRD"] = "/".join(idParts[:-1])
	newRow["resId"] = idParts[-1]
	newRow["deleted"] = True
	newRow["title"] = "Ex "+args.svcId
	newRow["dateUpdated"] = newRow["recTimestamp"] = datetime.datetime.utcnow()
	resTable.addRow(newRow)

	# mark in sets table
	resTable = rsc.TableForDef(svcsRD.getById("sets"),
		connection=querier.connection)
	newRow = resTable.tableDef.getDefaults()
	newRow["sourceRD"] = "/".join(idParts[:-1])
	newRow["renderer"] = "null"
	newRow["resId"] = idParts[-1]
	newRow["setName"] = "ivo_managed"
	newRow["deleted"] = True
	resTable.addRow(newRow)


@exposedFunction([Arg(help="rd#table-id for the table containing the"
	" products that should get cached previews", dest="tableId"),
	Arg("-w", 
		help="width to compute the preview for", dest="width", default="200"),],
	help="Precompute previews for the product interface columns in a table.")
def cacheprev(querier, args):
	from gavo import api
	from gavo.protocols import products
	from gavo.web.productrender import PreviewCacheManager
	from twisted.internet import reactor

	basePath = base.getConfig("inputsDir")
	td = base.resolveId(None, args.tableId)
	table = api.TableForDef(td, connection=querier.connection)
	select = [td.getColumnByName("accref"), td.getColumnByName("mime")]
	rows = table.iterQuery(select , "")

	def runNext(ignored):
		try:
			row = rows.next()
			return PreviewCacheManager.getPreviewFor(row["mime"],
				[os.path.join(basePath, row["accref"]), args.width]
			).addCallback(runNext
			).addErrback(runNext)
		except StopIteration:
			pass
		except:
			import traceback
			traceback.print_exc()
		reactor.stop()

	reactor.callLater(0, runNext, "startup")
	reactor.run()


@exposedFunction([Arg(help="rd#table-id of the table of interest", 
	dest="tableId")],
	help="Show the statements to create the indices on a table.")
def indexStatements(querier, args):
	import re
	from gavo import api
	td = base.resolveId(None, args.tableId)
	for ind in td.indices:
		print "\n".join(re.sub(r"\s+", " ", s) for s in ind.iterCode())



def main():
	base.setDBProfile("admin")
	with base.AdhocQuerier(base.getAdminConn) as querier:
		args = makeParser(globals()).parse_args()
		args.subAction(querier, args)
