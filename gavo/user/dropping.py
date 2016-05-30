"""
Dropping resources.  For now, you can only drop entire RDs.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import api
from gavo import base
from gavo import utils
from gavo.protocols import tap
from gavo.user import common


def restoreObscore(conn):
	"""sees if this system should have an obscore table and re-creates
	it if it's missing.
	"""
	q = base.UnmanagedQuerier(conn)
	if q.tableExists("ivoa._obscoresources"):
		n = list(q.query("SELECT count(*) from ivoa._obscoresources"))[0][0]
		if n>1: # ivoa.emptyobscore doesn't count
			api.makeData(api.resolveCrossId("//obscore#create"),
				connection=conn)


def _do_dropTable(tableName, conn):
	"""deletes rows generated from tableName from the DC's metadata
	(and tableName itself).
	"""
	q = base.UnmanagedQuerier(conn)
	for metaTableName, columnName in [
			("dc.tablemeta", "tableName"),
			("ivoa._obscoresources", "tableName"),
			("tap_schema.tables", "table_name"),
			("tap_schema.keys", "from_table"),
			("tap_schema.keys", "target_table"),
			("tap_schema.columns", "table_name")]:
		if q.tableExists(metaTableName):
			q.query("delete from %s where %s=%%(tableName)s"%(
				metaTableName, columnName),
				{"tableName": tableName})

	#	POSSIBLE SQL INJECTION when tableName is a suitably wicked
	# quoted name; right now, this is mitigated by the fact that
	# people that can call this don't need SQL injection since
	# they can execute anything gavoadmin can anyway.
	if q.viewExists(tableName):
		q.query("drop view "+tableName)
	elif q.tableExists(tableName):
		# warning: this will drop ivoa.obscore if defined (the "cascade").
		# We manually re-create obscore after this is run if necessary.
		q.query("drop table "+tableName+" cascade")


def dropTable():
	"""tries to "manually" purge a table from the DC's memories.

	This is a "toplevel" function inteded to be called by cli directly.
	"""
	def parseCmdline():
		from gavo.imp.argparse import ArgumentParser
		parser = ArgumentParser(
			description="Removes all traces of the named table within the DC.")
		parser.add_argument("tablename", help="The name of the table to drop,"
		 	" including the schema name.", nargs="+")
		return parser.parse_args()
	
	opts = parseCmdline()
	
	with base.getWritableAdminConn() as conn:
		for tableName in opts.tablename:
			_do_dropTable(tableName, conn)
		conn.execute("DELETE FROM dc.products WHERE sourcetable=%(t)s",
			{'t': tableName})
		restoreObscore(conn)


def _do_dropRD(opts, rdId, selectedIds=()):
	"""drops the data and services defined in the RD selected by rdId.
	"""
	try:
		rd = api.getReferencedElement(rdId, forceType=api.RD)
	except api.NotFoundError:
		if opts.force:
			rd = None
		else:
			raise

	with base.AdhocQuerier(base.getWritableAdminConn) as querier:
		if rd is not None:
			if opts.dropAll:
				dds = rd.dds
			else:
				dds = common.getPertainingDDs(rd, selectedIds)

			parseOptions = api.getParseOptions(systemImport=opts.systemImport)

			for dd in dds:
				api.Data.drop(dd, connection=querier.connection, 
					parseOptions=parseOptions)

			if not selectedIds or opts.dropAll:
				from gavo.registry import servicelist
				servicelist.cleanServiceTablesFor(rd, querier.connection)
				tap.unpublishFromTAP(rd, querier.connection)

			try:
				with querier.connection.savepoint():
					querier.query("drop schema %s"%rd.schema)
			except Exception, msg:
				api.ui.notifyWarning("Cannot drop RD %s's schema %s because:"
					" %s."%(rd.sourceId, rd.schema, utils.safe_str(msg)))

		else:
			# If the RD doesn't exist any more, just manually purge it
			# from wherever it could have been mentioned.
			for tableName in ["dc.tablemeta", "tap_schema.tables", 
					"tap_schema.columns", "tap_schema.keys", "tap_schema.key_columns",
					"dc.resources", "dc.interfaces", "dc.sets", "dc.subjects",
					"dc.authors", "dc.res_dependencies"]:
				if querier.tableExists(tableName):
					querier.query(
						"delete from %s where sourceRd=%%(sourceRD)s"%tableName,
						{"sourceRD": rdId})

		restoreObscore(querier.connection)


def dropRD():
	"""parses the command line and drops data and services for the
	selected RD.

	This is a "toplevel" function inteded to be called by cli directly.
	"""
	def parseCmdline():
		from gavo.imp.argparse import ArgumentParser
		parser = ArgumentParser(
			description="Drops all tables made in an RD's data element.")
		parser.add_argument("rdid", help="RD path or id to drop")
		parser.add_argument("ddids", help="Optional dd id(s) if you"
			" do not want to drop the entire RD.  Note that no service"
			" publications will be undone if you give DD ids.", nargs="*")
		parser.add_argument("-s", "--system", help="drop tables even if they"
			" are system tables",
			dest="systemImport", action="store_true")
		parser.add_argument("-f", "--force", help="Even if the RD isn't"
			" found, try to purge entries referencing it. This only"
			" makes sense with the full RD id.",
			dest="force", action="store_true")
		parser.add_argument("--all", help="drop all DDs in the RD,"
			" not only the auto ones (overrides manual selection)",
			dest="dropAll", action="store_true")
		return parser.parse_args()

	opts = parseCmdline()
	rdId = opts.rdid
	ddIds = None
	if opts.ddids:
		ddIds = set(opts.ddids)
	_do_dropRD(opts, rdId, ddIds)
