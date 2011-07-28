"""
The user interface to importing resources into the VO.
"""

import sys
import os
import traceback
from optparse import OptionParser

from gavo import base
from gavo import rscdesc
from gavo import rsc
from gavo.protocols import tap
from gavo import user


def process(opts, args):
	"""imports the data set described by args governed by opts.

	The first item of args is an RD id, any remaining ones are interpreted
	as DD ids within the selected RD.  If no DD ids are given, all DDs within
	the RD are processed except those for which auto has been set to False.

	opts is either a ParseOption instance or the object returned by
	main's parseOption function below.
	"""
	src, ddIds = args[0], set(args[1:])
	rd = rscdesc.openRD(src)
	connection = base.getDBConnection("admin")
	tap.unpublishFromTAP(rd, connection)
	tap.publishToTAP(rd, connection)
	for dd in rd.dds:
		if ddIds and not dd.id in ddIds:
			continue
		if not dd.auto and not dd.id in ddIds:
			continue
		if opts.metaOnly:
			base.ui.notifyInfo("Updating meta for %s"%dd.id)
			res = rsc.Data.create(dd, parseOptions=opts, connection=connection
				).updateMeta(opts.metaPlusIndex)
		else:
			base.ui.notifyInfo("Making data %s"%dd.id)
			res = rsc.makeData(dd, parseOptions=opts, connection=connection)
		if hasattr(res, "nAffected"):
			base.ui.notifyInfo("Columns affected: %s"%res.nAffected)
	connection.commit()
	rd.touchTimestamp()


def main():
	"""parses the command line and imports a set of data accordingly.
	"""
	def parseCmdline():
		parser = OptionParser(usage="%prog [options] <rd-name> {<data-id>}",
			description="imports all (or just the selected) data from an RD"
				" into the database.")
		parser.add_option("-n", "--updateRows", help="Use UPDATE on primary"
			" key rather than INSERT with rows inserted to DBTables.",
			action="store_true", dest="doTableUpdates", default=False)
		parser.add_option("-d", "--dumpRows", help="Dump raw rows as they are"
			" emitted by the grammar.", dest="dumpRows", action="store_true",
			default=False)
		parser.add_option("-R", "--redoIndex", help="Drop indices before"
			" updating a table and recreate them when done", dest="dropIndices",
			action="store_true", default=False)
		parser.add_option("-m", "--meta-only", help="just update table meta"
			" (privileges, column descriptions,...).", dest="metaOnly", 
			action="store_true")
		parser.add_option("-I", "--meta-and-index", help="do not import, but"
			" update table meta (privileges, column descriptions,...) and recreate"
			" the indices", dest="metaPlusIndex", action="store_true")
		parser.add_option("-u", "--update", help="update mode -- don't drop"
			" tables before writing.", dest="updateMode", 
			action="store_true", default=False)
		parser.add_option("-p", "--profile", help="use PROFILE to access db",
			dest="dbProfile", action="store", type="str", 
			default="admin", metavar="PROFILE")
		parser.add_option("-s", "--system", help="create shared tables",
			dest="systemImport", action="store_true")
		parser.add_option("-v", "--verbose", help="talk a lot while working",
			dest="verbose", action="store_true")
		parser.add_option("-U", "--ui", help="use UI to show what is going on;"
			" known UI names include: %s"%", ".join(user.interfaces),
			dest="uiName", action="store", type="str", default="plain",
			metavar="UI")
		parser.add_option("-r", "--reckless", help="Do not validate rows"
			" before ingestion", dest="validateRows", action="store_false",
			default=True)
		parser.add_option("-M", "--stop-after", help="Stop after having parsed"
			" MAX rows", metavar="MAX", action="store", dest="maxRows", type="int",
			default=None)
		parser.add_option("-b", "--batch-size", help="deliver N rows at a time"
			" to the database.", dest="batchSize", action="store", type="int",
			default=5000, metavar="N")
		parser.add_option("-c", "--continue-bad", help="go on if processing a"
			" row failed.", dest="keepGoing", action="store_true", default=False)

		(opts, args) = parser.parse_args()

		base.setDBProfile(opts.dbProfile)
		if opts.uiName not in user.interfaces:
			raise base.ReportableError("UI %s does not exist.  Choose one of"
				" %s"%(opts.uiName, ", ".join(user.interfaces)))
		if opts.metaPlusIndex:
			opts.metaOnly = True
		user.interfaces[opts.uiName](base.ui)
		if not args:
			parser.print_help()
			sys.exit(1)
		return opts, args


	problemlog = user.interfaces["problemlog"](base.ui)
	opts, args = parseCmdline()
	process(opts, args)
	problemlog.dump("last.badrows")


if __name__=="__main__":
	main()
