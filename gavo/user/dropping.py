"""
Dropping resources.  For now, you can only drop entire RDs.
"""

import os
import sys
from optparse import OptionParser

from gavo import api
from gavo.protocols import tap


def drop(opts, rdId):
	"""drops the data and services defined in the RD selected by rdId.
	"""
	try:
		rd = api.getRD(os.path.join(os.getcwd(), rdId))
	except api.RDNotFound:
		rd = api.getRD(rdId, forImport=True)
	connection = api.getDBConnection("admin")
	for dd in rd.dds:
		res = api.Data.drop(dd, connection=connection)
	from gavo.registry import servicelist
	servicelist.cleanServiceTablesFor(rd, connection)
	tap.unpublishFromTAP(rd, connection)
	connection.commit()


def main():
	"""parses the command line and drops data and services for the
	selected RD.
	"""
	def parseCmdline():
		parser = OptionParser(usage="%prog [options] <rd-id>",
			description="Drops all tables made in an RD's data element.")
		(opts, args) = parser.parse_args()
		if len(args)!=1:
			parser.print_help()
			sys.exit(1)
		return opts, args

	opts, args = parseCmdline()
	drop(opts, args[0])

