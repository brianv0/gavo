"""
Handling table metadata in db tables.
"""

from gavo import base
from gavo.rsc import dbtable
from gavo import rscdef


class ColumnError(base.Error):
	"""is raised by the MetaTableHandler when some operation on 
	columns doesn't work out.
	"""


class MetaTableHandler(object):
	"""is an interface to the meta table.

	The meta table holds information on all columns of all user tables
	in the database.  Its definition is given in the __system__/dc_tables
	RD.

	The meta table handler holds one connection to query for field infos.
	If writing to the meta table, you have to provide a querier.  This
	is done to avoid changing the meta table in a transaction and have
	the effects bleed out of it.  On the other hand, while in a transaction,
	meta table results may differ from what you just wrote.  That shouldn't
	hurt, though, since you shouldn't need to access the meta table shortly
	after writing to it.

	Though you can construct MetaTableHandlers of your own, the metaHandler
	from rscdesc should usually do.
	"""
	def __init__(self, overrideProfile=None):
		self.profile = overrideProfile or "admin"
		self.rd = base.caches.getRD("__system__/dc_tables")
		self.readQuerier = self._getQuerier()
		if not self.readQuerier.tableExists("dc.columnmeta"):
			# this is for bootstrapping: the first gavo imp dc_tables doesn't have
			# dc tables yet but it doesn't need them either.
			return
		self.metaTable = dbtable.DBTable(
			self.rd.getTableDefById("columnmeta"))
		self.tablesTable = dbtable.DBTable(
			self.rd.getTableDefById("tablemeta"))
		self.metaRowdef = self.rd.getTableDefById("metaRowdef")
		self.tablesRowdef = self.rd.getTableDefById("tablemeta")

	def _getQuerier(self):
		"""returns the write-only querier for the meta table.

		Do not use this querier to write information.
		"""
		return base.SimpleQuerier(useProfile=self.profile)

	def getColumn(self, colName, tableName=""):
		"""returns a dictionary with the information available
		for colName.

		colName can be "fully qualified", i.e. given as <schema>.<table>.<column>
		of <table>.<column> (which implies the public schema).  If they are
		not, tableName will be used for the query instead.

		Table names are opaque to MetaTableHandler but will
		usually include a schema.
		"""
		resDict = {}
		parts = colName.split(".")
		if len(parts)==2:
			tableName, colName = parts
		elif len(parts)==3:
			tableName = ".".join(parts[:2])
			colName = parts[2]
		elif len(parts)!=1:
			raise ColumnError("Invalid column specification: %s"%colName)
		try:
			match = self.metaTable.iterQuery(self.metaRowdef,
					" tableName=%%(tableName)s AND colName=%%(colName)s", { 
				"tableName": tableName,
				"fieldName": colName,}).next()
		except OperationalError:
			raise ColumnError("No info for %s in %s"%(colName, tableName))
		return rscdef.Column.fromMetaTableRow(match)
	
	def getColumnsForTable(self, tableName):
		"""returns a field definition list for tableName.

		WARNING: This will produce columns according to the information in
		the database.  This does, e.g., not include STC information.

		Consider using the base.caches.getTableDefForTable method for 
		RD-correct columns.
		"""
		if not "." in tableName:
			tableName = "public."+tableName
		res = self.metaTable.iterQuery(self.metaRowdef, 
			" tableName=%(tableName)s", {"tableName": tableName},
			limits=("ORDER BY colInd", {}))
		return [rscdef.Column.fromMetaTableRow(row)
			for row in res]
	
	def getTableDefForTable(self, tableName):
		if not "." in tableName:
			tableName = "public."+tableName
		try:
			tableRec = list(self.tablesTable.iterQuery(self.tablesRowdef, 
				" tableName=%(tableName)s", {"tableName": tableName}))[0]
		except IndexError:
			raise base.NotFoundError(tableName, "Table", "dc_tables")
		return base.caches.getRD(tableRec["sourceRd"]
			).getById(tableName.split(".")[1])
