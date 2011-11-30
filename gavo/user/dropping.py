"""
Dropping resources.  For now, you can only drop entire RDs.
"""

import os
import sys

from gavo import api
from gavo import base
from gavo.protocols import tap


def _do_dropTable(tableName):
	"""deletes rows generated from tableName from the DC's metadata
	(and tableName itself).
	"""
	with base.AdhocQuerier(base.getAdminConn) as q:
		for metaTableName, columnName in [
				("dc.columnmeta", "tableName"),
				("dc.tablemeta", "tableName"),
				("ivoa._obscoresources", "tableName"),]:
			if q.tableExists(metaTableName):
				q.query("delete from %s where %s=%%(tableName)s"%(
					metaTableName, columnName),
					{"tableName": tableName})
		if q.tableExists(tableName):
			#	POSSIBLE SQL INJECTION when tableName is a suitably wicked
			# quoted name; right now, this is mitigated by the fact that
			# people that can call this don't need SQL injection since
			# they can execute anything gavoadmin can anyway.
			q.query("drop table "+tableName)


def dropTable():
	"""tries to "manually" purge a table from the DC's memory.

	This is a "toplevel" function inteded to be called by cli directly.
	"""
	def parseCmdline():
		from gavo.imp.argparse import ArgumentParser
		parser = ArgumentParser(
			description="Removes all traces of the named table within the DC.")
		parser.add_argument("tablename", help="The name of the table to drop,"
		 	" including the schema name.")
		return parser.parse_args()
	
	opts = parseCmdline()
	_do_dropTable(opts.tablename)


def _do_dropRD(opts, rdId, ddIds=None):
	"""drops the data and services defined in the RD selected by rdId.
	"""
	try:
		rd = api.getRD(os.path.join(os.getcwd(), rdId))
	except api.RDNotFound:
		rd = api.getRD(rdId, forImport=True)
	connection = api.getDBConnection("admin")
	for dd in rd.dds:
		if ddIds is not None and dd.id not in ddIds:
			continue
		res = api.Data.drop(dd, connection=connection)
	if ddIds is None:
		from gavo.registry import servicelist
		servicelist.cleanServiceTablesFor(rd, connection)
		tap.unpublishFromTAP(rd, connection)
	
	# purge from system tables that have sourceRD
	# all traces that may have been left from this RD
	with base.SimpleQuerier(connection=connection) as querier:
		for tableName in ["dc.tablemeta", "tap_schema.tables", 
				"tap_schema.columns", "tap_schema.keys", "tap_schema.key_columns"]:
			if querier.tableExists(tableName):
				querier.query("delete from %s where sourceRd=%%(sourceRD)s"%tableName,
					{"sourceRD": rd.sourceId})


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
		return parser.parse_args()

	opts = parseCmdline()
	rdId = opts.rdid
	ddIds = None
	if opts.ddids:
		ddIds = set(opts.ddids)
	_do_dropRD(opts, rdId, ddIds)
