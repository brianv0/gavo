"""
Tables on disk
"""

import os
import sys

from gavo import base
from gavo import rscdef
from gavo.base import sqlsupport
from gavo.rsc import common
from gavo.rsc import table


class Feeder(table.Feeder):
	"""is a callable used for feeding data into a table.

	This feeder hands through batchSize items at a time to the database.

	After an exit, the instances have an nAffected attribute that says
	how many rows were processed by the database through this feeder.
	"""
	def __init__(self, parent, insertCommand, batchSize=2000, notify=True):
		self.nAffected, self.notify = 0, notify
		table.Feeder.__init__(self, parent)
		self.cursor = parent.connection.cursor()
		self.feedCommand, self.batchSize = insertCommand, batchSize
		self.batchCache = []

	def shipout(self):
		if self.batchCache:
			try:
				self.cursor.executemany(self.feedCommand, self.batchCache)
			except sqlsupport.IntegrityError:
				import pprint
				sys.stderr.write("One or more of the following rows clashed:\n")
				pprint.pprint(self.batchCache, sys.stderr)
				raise
			except sqlsupport.DataError:
				sys.stderr.write("Bad input.  Run with -b1 to pin down offending"
					" record.  First rec:\n")
				sys.stderr.write("%s\n"%self.batchCache[0])
				raise
			except sqlsupport.ProgrammingError:
				raise
			if self.cursor.rowcount>=0:
				self.nAffected += self.cursor.rowcount
			else: # can't guess how much was affected, let's assume all rows
				self.nAffected += len(self.batchCache)        # did something.
			if self.notify:
				base.ui.notifyShipout(len(self.batchCache))
			self.batchCache = []

	def add(self, data):
		if self.table.validateRows:
			try:
				self.table.tableDef.validateRow(data)
			except rscdef.IgnoreThisRow:
				return
		self.batchCache.append(data)
		if len(self.batchCache)>=self.batchSize:
			self.shipout()
	
	def exit(self, *args):
		if not args or args[0] is None: # regular exit, ship out
			try:
				self.shipout()
# The following sucks, but rowcount seems to be always 1 on insert operations.
# However, we at least want a chance to catch update operations matching
# nothing.  So, if rowcount is 0, it's a sign something went wrong, and
# we want to override our initial guess.
				if self.cursor.rowcount==0:
					self.nAffected = 0
				self.cursor.close()
			except:
				return table.Feeder.exit(self, *sys.exc_info())
		return table.Feeder.exit(self, *args)

	def getAffected(self):
		return self.nAffected


class RaisingFeeder(Feeder):
	"""is a feeder that will bomb on any attempt to feed data to it.

	It is useful for tables that can't be written, specifically, views.
	"""
	def add(self, data):
		raise base.DataError("Attempt to feed to a read-only table")


class MetaTableMixin(object):
	"""is a mixin providing methods updating the dc_tables.

	It requires a tableDef attribute on the parent, and the parent must
	mix in QuerierMixin.
	"""
	@property
	def dcTablesRD(self):
		try:
			return self.__dcTablesRD
		except AttributeError:
			self.__dcTablesRD = base.caches.getRD("__system__/dc_tables")
			return self.__dcTablesRD

	def _cleanFromSourceTable(self):
		"""removes information about self.tableDef from the tablemeta table.
		"""
		self.query("DELETE FROM dc.tablemeta WHERE tableName=%(tableName)s",
			{"tableName": self.tableDef.getQName()})
	
	def _addToSourceTable(self):
		"""adds information about self.tableDef to the tablemeta table.
		"""
		t = DBTable(self.dcTablesRD.getTableDefById("tablemeta"),
			connection=self.connection)
		t.addRow({"tableName": self.tableDef.getQName(), 
			"sourceRd": self.tableDef.rd.sourceId,
			"adql": self.tableDef.adql, 
			"tableDesc": base.getMetaText(self.tableDef, "description"),
			"resDesc": base.getMetaText(self.tableDef.rd, "description"),})

	def _cleanColumns(self):
		"""removes information about self.tableDef from columnmeta.
		"""
		self.query(
			"DELETE FROM dc.columnmeta WHERE tableName=%(tableName)s",
			{"tableName": self.tableDef.getQName()})

	def _defineColumns(self):
		"""adds information about self.tableDef to columnmeta.
		"""
		tableName = self.tableDef.getQName()
		t = DBTable(self.dcTablesRD.getTableDefById("columnmeta"),
			connection=self.connection)
		makeRow = self.dcTablesRD.getById("fromColumnList").compileForTable(t)
		feeder = t.getFeeder(notify=False)
		for colInd, column in enumerate(self.tableDef):
			items = {"tableName": tableName, "colInd": colInd, "column": column}
			feeder.add(makeRow(items))
		feeder.exit()

	def addToMeta(self):
		self.cleanFromMeta()  # Don't force people to clean first on meta updates
		self._addToSourceTable()
		self._defineColumns()

	def cleanFromMeta(self):
		self._cleanFromSourceTable()
		self._cleanColumns()


class DBMethodsMixin(sqlsupport.QuerierMixin):
	"""is a mixin for on-disk tables.

	The parent must have tableDef, tableName (from tabledef.getQName()) and
	connection (for the QuerierMixin) attributes.

	Note that many of them return the table so you can say drop().commit()
	in hackish code.
	"""
	def _definePrimaryKey(self):
		if self.tableDef.primary and not self.hasIndex(self.tableName,
				self.getPrimaryIndexName(self.tableDef.id)):
			if not self.tableDef.system:
				base.ui.notifyIndexCreation("Primary key on %s"%self.tableName)
			try:
				self.query("ALTER TABLE %s ADD PRIMARY KEY (%s)"%(
					self.tableName, ", ".join(self.tableDef.primary)))
			except sqlsupport.DBError, msg:
				raise common.DbTableError("Primary key %s could not be added (%s)"%(
					self.tableDef.primary, repr(str(msg))), self.tableName)

	def _dropPrimaryKey(self):
		"""drops a primary key if it exists.

		*** Postgres specific ***
		"""
		constraintName = str(self.getPrimaryIndexName(self.tableDef.id))
		if self.tableDef.primary and self.hasIndex(
				self.tableName, constraintName):
			self.query("ALTER TABLE %s DROP CONSTRAINT %s"%(
				self.tableName, constraintName))

	def _addForeignKeys(self):
		"""adds foreign key constraints if necessary.
		"""
		for fk in self.tableDef.foreignKeys:
			if not self.tableDef.system:
				base.ui.notifyIndexCreation(fk.getDescription())
			fk.create(self)
	
	def _dropForeignKeys(self):
		"""drops foreign key constraints if necessary.
		"""
		for fk in self.tableDef.foreignKeys:
			fk.delete(self)

	def dropIndices(self):
		if not self.exists():
			return
		self._dropForeignKeys()
		self._dropPrimaryKey()
		schema, unqualified = self.tableDef.rd.schema, self.tableDef.id
		for index in self.tableDef.indices:
			iName = self.tableDef.expand(index.name)
			if self.hasIndex(self.tableName, iName):
				self.query("DROP INDEX %s.%s"%(schema, iName))
		return self
	
	def makeIndices(self):
		"""creates all indices on the table, including any definition of
		a primary key.
		"""
		if self.suppressIndex or not self.exists():
			return
		if not self.hasIndex(self.tableName, 
				self.getPrimaryIndexName(self.tableDef.id)):
			self._definePrimaryKey()
		for index in self.tableDef.indices:
			if not self.hasIndex(self.tableName, index.name):
				if not self.tableDef.system:
					base.ui.notifyIndexCreation(index.name)
				self.query(self.tableDef.expand("CREATE INDEX %s ON %s (%s)"%(
					index.name, self.tableName, index.content_)))
			if index.cluster:
				self.query(self.tableDef.expand(
					"CLUSTER %s ON %s"%(index.name, self.tableName)))
		self._addForeignKeys()
		self.query(self.tableDef.expand("ANALYZE %s"%self.tableName))
		return self

	def _deleteMatching(self, matchCondition):
		"""deletes all rows matching matchCondition.

		For now, matchCondition a boolean SQL expression.  All rows matching
		it will be deleted.
		"""
		self.query("DELETE FROM %s WHERE %s"%(self.tableName, matchCondition))
	
	def copyIn(self, inFile):
		cursor = self.connection.cursor()
		cursor.copy_expert("COPY %s FROM STDIN WITH BINARY"%self.tableName, inFile)
		cursor.close()
		return self

	def copyOut(self, outFile):
		cursor = self.connection.cursor()
		cursor.copy_expert("COPY %s TO STDOUT WITH BINARY"%self.tableName, outFile)
		cursor.close()
		return self
	
	def ensureSchema(self):
		"""creates self's schema if necessary.
		"""
		if self.tableDef.temporary:  # these never are in a schema
			return
		schemaName = self.tableDef.rd.schema
		if not self.schemaExists(schemaName):
			self.query("CREATE SCHEMA %(schemaName)s"%locals())
			self.setSchemaPrivileges(self.tableDef.rd)
		return self


class DBTable(table.BaseTable, DBMethodsMixin, MetaTableMixin):
	"""is a table in the database.

	It is created, if necessary, on construction, but indices and primary
	keys will only be created if a feeder finishes, or on a manual makeIndices
	call.

	The constructor will never drop an existing table and does not check if
	the schema of the table on disk matches the tableDef.  If you changed
	tableDef, you will need to call the recreate method.

	You can pass a nometa boolean kw argument to suppress entering the table
	into the dc_tables.
	"""
	def __init__(self, tableDef, **kwargs):
		self.ownedConnection = False
		self.suppressIndex = kwargs.pop("suppressIndex", False)
		self.tableUpdates = kwargs.pop("tableUpdates", False)
		connection = kwargs.pop("connection", None)
		table.BaseTable.__init__(self, tableDef, **kwargs)
		if connection is None:
			self.connection = base.getDefaultDBConnection()
			self.ownedConnection = True
		else:
			self.connection = connection
		if self.tableDef.rd is None and not self.tableDef.temporary:
			raise common.ResourceError("TableDefs without resource descriptor"
				" cannot be used to access database tables")
		self.tableName = self.tableDef.getQName()
		self.nometa = (kwargs.get("nometa", False) 
			or self.tableDef.temporary or tableDef.rd.schema=="dc")
		if kwargs.get("create", True):
			self.createIfNecessary()
		if not self.tableUpdates:
			self.addCommand = ("INSERT INTO %s (%s) VALUES (%s)"%(
				self.tableName, 
				", ".join([c.name for c in self.tableDef.columns]),
				", ".join(["%%(%s)s"%c.name for c in self.tableDef.columns])))
		else:
			self.addCommand = "UPDATE %s SET %s WHERE %s"%(
				self.tableName,
				", ".join("%s=%%(%s)s"%(f.name, f.name) 
					for f in self.tableDef),
			" AND ".join("%s=%%(%s)s"%(n, n) for n in self.tableDef.primary))
		if "rows" in kwargs:
			self.feedRows(kwargs["rows"])

	def __iter__(self):
# XXXX TODO: fix psycopg timeout patch to allow named cursors
		cursor = self.connection.cursor()
		cursor.execute("SELECT * FROM %s"%self.tableName)
		for row in cursor:
			yield self.tableDef.makeRowFromTuple(row)

	def exists(self):
		if self.tableDef.temporary:
			return self.temporaryTableExists(self.tableName)
		else:
			return self.tableExists(self.tableName)

	def close(self):
		"""call this if your table holds an owned connection and you don't need
		it any more.
		"""
		if self.ownedConnection and not self.connection.closed:
			self.connection.close()

	def getFeeder(self, **kwargs):
		if "notify" not in kwargs:
			kwargs["notify"] = not self.tableDef.system
		return Feeder(self, self.addCommand, **kwargs)

	def importFinished(self):
		self.tableDef.runScripts("preIndex", tw=self)
		self.tableDef.runScripts("preIndexSQL", connection=self.connection)
		self.makeIndices()
		if self.ownedConnection:
			self.connection.commit()
		return self
	
	def importFailed(self, *excInfo):
		if self.ownedConnection:
			self.connection.rollback()
		return False
	
	def feedRows(self, rows):
		"""Feeds a sequence of rows to the table.

		The method returns the number of rows affected.  Exceptions are
		handed through upstream, but the connection is rolled back.
		"""
		feeder = self.getFeeder()
		try:
			for r in rows:
				feeder.add(r)
		except:
			feeder.exit(*sys.exc_info())
		else:
			feeder.exit(None, None, None)
		return feeder.nAffected

	def addRow(self, row):
		"""adds a row to the table.

		Use this only to add one or two rows, otherwise go for getFeeder.
		"""
		try:
			self.query(self.addCommand, row)
		except sqlsupport.IntegrityError:
			raise base.ValidationError("Row %s cannot be added since it clashes"
				" with an existing record on the primary key"%row, row=row,
				colName="unknown")

	def getRow(self, *key):
		"""returns the row with the primary key key from the table.

		This will raise a DataError on tables without primaries.
		"""
		if not self.tableDef.primary:
			raise base.DataError("Table %s has no primary key and thus does"
				" not support getRow"%self.tableName)
		res = list(self.iterQuery(self.tableDef, 
			" AND ".join("%s=%%(%s)s"%(n,n) for n in self.tableDef.primary),
			pars=dict(zip(self.tableDef.primary, key))))
		if not res:
			raise KeyError(key)
		return res[0]

	def deleteMatching(self, condition, pars):
		self.query("DELETE FROM %s WHERE %s"%(self.tableName, condition), pars)

	def commit(self):
		"""commits an owned connection.

		For borrowed connections, this is a no-op.
		"""
		if self.ownedConnection:
			self.connection.commit()
		return self
	
	def createUniquenessRules(self):
		if not self.tableDef.forceUnique:
			return

		def getMatchCondition():
			return " AND ".join("%s=new.%s"%(n,n) for n in self.tableDef.primary)

		if self.tableDef.dupePolicy=="drop":
			self.query("CREATE OR REPLACE RULE updatePolicy AS"
				" ON INSERT TO %s WHERE"
				" EXISTS(SELECT * FROM %s WHERE %s)"
				" DO INSTEAD NOTHING"%(self.tableName, self.tableName, 
					getMatchCondition()))
		elif self.tableDef.dupePolicy=="check":
			# This one is tricky: if the inserted column is *different*,
			# the rule does not fire and we get a pkey violation.
			# Furthermore, special NULL handling is required -- we
			# do not check columns that have NULLs in new or old.
			self.query("CREATE OR REPLACE RULE updatePolicy AS"
				" ON INSERT TO %s WHERE"
				" EXISTS(SELECT 1 FROM %s WHERE %s)"
				" DO INSTEAD NOTHING"%(self.tableName, self.tableName, 
					" AND ".join("(new.%s IS NULL OR %s IS NULL OR %s=new.%s)"%(
						c.name, c.name, c.name,c.name) for c in self.tableDef)))
		elif self.tableDef.dupePolicy=="overwrite":
			self.query("CREATE OR REPLACE RULE updatePolicy AS"
				" ON INSERT TO %s WHERE"
				" EXISTS(SELECT %s FROM %s WHERE %s)"
				" DO INSTEAD UPDATE %s SET %s WHERE %s"%(self.tableName, 
					",".join(self.tableDef.primary),
					self.tableName, getMatchCondition(),
					self.tableName,
					", ".join("%s=new.%s"%(c.name,c.name) for c in self.tableDef),
					getMatchCondition()))
		else:
			raise base.DataError("Invalid dupePolicy: %s"%self.tableDef.dupePolicy)

	def configureTable(self):
		if self.tableDef.temporary:
			self.createUniquenessRules()
			return
		self.updateMeta()
		self.createUniquenessRules()
		return self

	def create(self):
		self.ensureSchema()
		preTable = ""
		if self.tableDef.temporary:
			preTable = "TEMP "
		self.query("CREATE %sTABLE %s (%s)"%(
			preTable,
			self.tableName,
			", ".join([column.getDDL()
				for column in self.tableDef.columns])))
		return self.configureTable()

	def updateMeta(self):
		self.setTablePrivileges(self.tableDef)
		self.setSchemaPrivileges(self.tableDef.rd)
		if not self.nometa:
			self.addToMeta()
		return self

	def createIfNecessary(self):
		if not self.exists():
			self.create()
		return self
	
	def drop(self, what="TABLE"):
		if self.exists():
			self.query("DROP %s %s CASCADE"%(what, self.tableName))
			self.tableDef.runScripts("afterDrop", connection=self.connection)
			if not self.nometa:
				self.cleanFromMeta()
		return self

	def recreate(self):
		self.drop()
		self.create()
		return self
	
	def iterQuery(self, resultTableDef, fragment, pars=None, 
			distinct=False, limits=None, groupBy=None):
		"""returns an iterator over rows for a table defined
		by resultTableDef giving the results for a query for
		fragment and pars.

		resultTableDef is a TableDef with svc.OutputField columns
		(rscdef.Column instances will do), fragment is empty or
		an SQL where-clause with dictionary placeholders, pars is
		the dictionary filling fragment, distinct, if True, adds a
		distinct clause, and limits, if given, is a pair of an SQL
		string to be appended to the SELECT clause and parameters
		filling it.  queryMeta.asSQL returns what you need here.

		pars may be mutated in the process.
		"""
		if pars is None:
			pars = {}
		query = ["SELECT "]
		if distinct:
			query.append("DISTINCT ")
		query.append(", ".join([getattr(c, "select", c.name)
			for c in resultTableDef])+" ")
		query.append("FROM %s "%self.tableName)
		if fragment and fragment.strip():
			query.append("WHERE %s "%fragment)
		if groupBy:
			query.append("GROUP BY %s "%groupBy)
		if limits:
			query.append(limits[0]+" ")
			pars.update(limits[1])
		for tupRow in self.query("".join(query), pars):
			yield resultTableDef.makeRowFromTuple(tupRow)


class View(DBTable):
	"""is a view, i.e., a table in the database you can't add to.

	Strictly, I should derive both View and DBTable from a common
	base, but that's currently not worth the effort.

	Technically, Views are DBTables with a viewCreation script
	(this is what TableForDef checks for when deciding whether to
	construct a DBTable or a View).  You can get a feeder for them,
	but trying to actually feed anything will raise a DataError.
	"""
	def __init__(self, *args, **kwargs):
		DBTable.__init__(self, *args, **kwargs)
		del self.addCommand

	def exists(self):
		return self.viewExists(self.tableName)

	def addRow(self, row):
		raise base.DataError("You cannot add data to views")

	feedRows = addRow
	
	def getFeeder(self, **kwargs):
		# all kwargs ignored since the feeder will raise an exception on any
		# attempts to feed anyway.
		return RaisingFeeder(self, None)
	
	def create(self):
		self.ensureSchema()
		self.tableDef.runScripts("viewCreation", querier=self)
		return self.configureTable()

	def makeIndices(self):
		return self  # no indices or primary keys on views.

	def drop(self):
		return DBTable.drop(self, "VIEW")
