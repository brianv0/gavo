"""
The user interface to importing resources into the VO.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import sys
from optparse import OptionParser

from gavo import api
from gavo import base
from gavo.protocols import tap
from gavo.rscdef import scripting
from gavo.user import common


class RetvalWatcher(base.ObserverBase):
	"""an Observer giving approproate program return values.

	Basically, we want to return an error signature even if we managed
	to import things if at least once there was an error notification.

	We define this "error occurred but we manage" code to 101 here.  I'm
	sure we can do better than that.
	"""
	retval = 0

	@base.listensTo("Error")
	def fixRetVal(self, msg):
		self.retval = 101


class TableCollector(base.ObserverBase):
	"""collects the qualified names of tables changed.

	This is used to run vacuum analyze on the respective tables before
	the import exits; the the vacuumAll method of this class can do
	that once all importing connections are closed (even if an Observer
	shouldn't do a thing like that...)
	"""
	def __init__(self, eh):
		base.ObserverBase.__init__(self, eh)
		self.tablesChanged = []

	@base.listensTo("DBTableModified")
	def addChangedTable(self, fqName):
		self.tablesChanged.append(fqName)

	def vacuumAll(self):
		from gavo import adql
		tableNameSym = adql.getSymbols()["qualifier"]
		for tableName in self.tablesChanged:
			tableNameSym.parseString(tableName, parseAll=True)
			with base.getAdminConn() as conn:
				conn.execute("VACUUM ANALYZE %s"%tableName)


def process(opts, args):
	"""imports the data set described by args governed by opts.

	The first item of args is an RD id, any remaining ones are interpreted
	as DD ids within the selected RD.  If no DD ids are given, all DDs within
	the RD are processed except those for which auto has been set to False.

	opts is either a ParseOption instance or the object returned by
	main's parseOption function below.
	"""
	# process manages its dependencies itself
	retvalWatcher = RetvalWatcher(api.ui)
	opts.buildDependencies = False

	# collect tables due for vacuuming
	tableCollector = TableCollector(api.ui)

	rdId, selectedIds = args[0], args[1:]
	rd = api.getReferencedElement(rdId, forceType=api.RD)

	dds = common.getPertainingDDs(rd, selectedIds)
	connection = api.getDBConnection("admin")
	tap.unpublishFromTAP(rd, connection)
	tap.publishToTAP(rd, connection)

	for dd in dds:
		if opts.metaOnly:
			api.ui.notifyInfo("Updating meta for %s"%dd.id)
			res = api.Data.create(dd, parseOptions=opts, connection=connection
				).updateMeta(opts.metaPlusIndex)

			# Hack: if there's an obscore mixin active, redo the obscore
			# Is there a less special-cased way to do this?
			for make in dd.makes:
				for script in make.scripts:
					if script.id=='addTableToObscoreSources':
						scripting.PythonScriptRunner(script).run(
							res.tables[make.table.id])
		else:
			api.ui.notifyInfo("Making data %s"%dd.id)
			res = api.makeData(dd, parseOptions=opts, connection=connection)
		if hasattr(res, "nAffected"):
			api.ui.notifyInfo("Rows affected: %s"%res.nAffected)
	# We're committing here so that we don't lose all importing
	# work just because some dependent messes up.
	connection.commit()

	api.makeDependentsFor(dds, opts, connection)
	connection.commit()
	rd.touchTimestamp()
	base.tryRemoteReload("__system__/dc_tables")

	tableCollector.vacuumAll()

	return retvalWatcher.retval


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
		parser.add_option("-D", "--dumpIngestees", help="Dump processed"
			" rows as emitted by the row makers.", dest="dumpIngestees",
			action="store_true", default=False)
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
		parser.add_option("-s", "--system", help="(re-)create system tables, too",
			dest="systemImport", action="store_true")
		parser.add_option("-v", "--verbose", help="talk a lot while working",
			dest="verbose", action="store_true")
		parser.add_option("-r", "--reckless", help="Do not validate rows"
			" before ingestion", dest="validateRows", action="store_false",
			default=True)
		parser.add_option("-M", "--stop-after", help="Stop after having parsed"
			" MAX rows", metavar="MAX", action="store", dest="maxRows", type="int",
			default=None)
		parser.add_option("-b", "--batch-size", help="deliver N rows at a time"
			" to the database.", dest="batchSize", action="store", type="int",
			default=5000, metavar="N")
		parser.add_option("-c", "--continue-bad", help="do not bail out after"
			" an error, just skip the current source and continue with the"
			" next one.", dest="keepGoing", action="store_true", default=False)
		parser.add_option("-L", "--commit-after-meta", help="commit the importing"
			" transaction after updating the meta tables.  Use this when loading"
			" large (hence -L) data sets to avoid keeping a lock on the meta tables"
			" for the duration of the input, i.e., potentially days.  The price"
			" is that users will see empty tables during the import.",
			dest="commitAfterMeta", action="store_true", default=False)

		(opts, args) = parser.parse_args()

		if opts.metaPlusIndex:
			opts.metaOnly = True
		if not args:
			parser.print_help(file=sys.stderr)
			sys.exit(1)
		return opts, args


	opts, args = parseCmdline()
	sys.exit(process(opts, args))


if __name__=="__main__":
	main()
