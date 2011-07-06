"""
Dropping resources.  For now, you can only drop entire RDs.
"""

import os
import sys

from gavo import api
from gavo import base
from gavo.protocols import tap


def drop(opts, rdId, ddIds=None):
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
	querier = base.SimpleQuerier(connection=connection)
	for tableName in ["dc.tablemeta", "tap_schema.tables", 
			"tap_schema.columns", "tap_schema.keys", "tap_schema.key_columns"]:
		if querier.tableExists(tableName):
			querier.query("delete from %s where sourceRd=%%(sourceRD)s"%tableName,
				{"sourceRD": rd.sourceId})

	connection.commit()


def main():
	"""parses the command line and drops data and services for the
	selected RD.
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
	drop(opts, rdId, ddIds)
