"""
Table classes.
"""

import weakref
import warnings
import compiler

import gavo
from gavo import logger
from gavo import sqlsupport
from gavo import meta
from gavo.parsing import parsehelpers

class NoParent(gavo.Error):
	pass


class BaseTable(meta.MetaMixin):
	"""is container for essentially homogenous data with
	metadata.

	Tables consist of rows, where each row maps column names to their
	value for that row.  The rows are accessible at least by iterating
	over a table.

	You can add records using the addData method.

	The main metadata is a list of datadef.DataField instances.

	A table usually has a parent DataSet.  If it has not (i.e., dataSet
	is None), some functionality will not be available, and a NoParent
	exception will be raised.

	Deriving classes can hook into finishBuild that clients must call
	when they are done adding data.

	This class should be considered abstract for the purposes of
	gavo since we keep the fieldDefs hidden in a RecordDef as a rule.
	"""
	def __init__(self, dataSet, fieldDefs, name):
		if dataSet:
			self.dataSet = weakref.proxy(dataSet)
			self.setMetaParent(self.dataSet)
		else:
			self.dataSet = None
		self.fieldDefs = fieldDefs
		self.name = name
		self.rows = []
	
	def __iter__(self):
		return iter(self.rows)

	def __len__(self):
		return len(self.rows)

	def __getitem__(self, index):
		return self.rows[index]

	def finishBuild(self):
		pass

	def setDumpOnly(self, dumpOnly):
		"""ignored, no longer supported.
		"""
		warnings.warn("setDumpOnly no longer supported.")

	def removeData(self, record):
		"""removes record from table.

		This has linear run time for basic tables.  It will raise an IndexError
		if record does not exist in the table.
		"""
		self.rows.remove(record)

	def addData(self, record):
		self.rows.append(record)

	def getFieldDefs(self):
		"""returns the field definitions as a list of DataField instances.

		Do not change the result.  It is *not* a copy.
		"""
		return self.fieldDefs
	
	def getName(self):
		"""returns the name of this table.

		The gavo system uses this name as table name in SQL data base.
		"""
		return self.name
	
	def getDataId(self):
		"""returns the ID of the parent data set.
		"""
		if self.dataSet:
			return self.dataSet.getId()
		raise NoParent()
	
	def getDataSet(self):
		return self.dataSet

	def getRowsAsTuples(self):
		"""returns a sequence of all rows represented as tuples as a data base
		would store them.

		The order of the items is given by the order of the DataFields in
		fieldDefs.
		"""
		makeTuple = compiler.compile(",".join(
			["row[%s]"%repr(f.get_dest()) for f in self.getFieldDefs()]),
			"<tupledef>", "eval")
		return [eval(makeTuple) for row in self.rows]

	def getFieldDefByDest(self, dest):
		"""returns the DataField that writes to dest.

		This method checks the parent dataSet for document fields.
		"""
		for fDef in self.fieldDefs:
			if fDef.get_dest()==dest:
				return fDef
		if self.dataSet:
			for fDef in self.dataSet.getDocFields():
				if fDef.get_dest()==dest:
					return fDef
		raise gavo.Error("Unknown column %s"%dest)


class IndexedTable(BaseTable):
	"""is a table that allows access to items through the primary key of
	the table.

	This currently only works for atomic primary keys.

	It is not used by the gavo system right now.
	"""	
	def getRow(self, key):
		"""returns the row with the primary key key.
		"""
		try:
			return self.rowIndex["key"]
		except AttributeError:
			self._buildRowIndex()
			return self.rowIndex["key"]

	def _buildRowIndex(self):
		primaryIndex = self.recordDef.getPrimary().get_dest()
		self.rowIndex = dict([(row[primaryIndex], row)
			for row in self])


class RecordBasedTable(BaseTable):
	"""is a table that gets its information from a RecordDef.
	"""
	def __init__(self, dataSet, recordDef):
		self.recordDef = recordDef
		BaseTable.__init__(self, dataSet, recordDef.get_items(), 
			recordDef.get_table())
	
	def getRecordDef(self):
		return self.recordDef

	def getInheritingTable(self, dataSet, recordDef):
		"""returns a new table belonging to data set and implementing
		recordDef, where recordDef may refer to self's fields.

		Referencing self's fields works by using the copy and dest attributes
		from fields of the new record.
		"""
		newFields = []
		for fieldDef in recordDef.get_items():
			if fieldDef.get_copy():
				newField = self.getFieldDefByDest(fieldDef.get_dest()).copy()
				newField.set_source(fieldDef.get_dest())
				newFields.append(newField)
			else:
				newFields.append(fieldDef)
		recordDef.set_items(newFields)
		return RecordBasedTable(dataSet, recordDef)


class Table(RecordBasedTable):
	"""is the default table used when exporting data to SQL databases.

	Basically, you fill in data and then call exportToSQL.
	"""
	dbConnection = None

#XXX TODO: nuke metaOnly from constructor and move it to exportToSQL
	def __init__(self, dataSet, recordDef, metaOnly=False):
		self.metaOnly = metaOnly
		RecordBasedTable.__init__(self, dataSet, recordDef)
	
	def _exportToMetaTable(self, schema=None):
		"""writes the column definitions to the sqlsupport-defined meta table.
		"""
		gavo.ui.displayMessage("Writing column info to meta table.")
		if schema:
			tableName = "%s.%s"%(schema, self.recordDef.get_table())
		else:
			tableName = self.recordDef.get_table()
		metaHandler = sqlsupport.MetaTableHandler()
		metaHandler.defineColumns(tableName,
			[field.getMetaRow() for field in self.getFieldDefs()])

	def _feedData(self, feed):
		"""writes the rows through the sqlsupport feeder feed.

		The feed is closed by this operation.  XXX TODO: That's
		wrong.  Closing the feed should be the responsibility of
		the calling function.
		"""
		counter = gavo.ui.getGoodBadCounter("Writing to db", 100)
		try:
			try:
				for row in self.rows:
					counter.hit()
					feed(row)
			except Exception, msg: 
				logger.error("Row %s bad (%s).  Aborting."%(row, msg))
				gavo.ui.displayError("Import of row %s failed (%s). ABORTING"
					" OPERATION."%(row, msg))
				feed.rollback()
				raise
		finally:
			counter.close()
			feed.close()

	def _getOwnedTableWriter(self, schema):
		tableName = "%s.%s"%(schema, self.recordDef.get_table())
		tableExporter = sqlsupport.TableWriter(tableName,
			self.recordDef.get_items(), self.dbConnection, 
			scriptRunner=self.recordDef)
		tableExporter.ensureSchema(schema)
		tableExporter.createTable(create=self.recordDef.get_create(),
			delete=self.recordDef.get_create(),
			privs=self.recordDef.get_create())
		return tableExporter

	def _exportOwnedTable(self, schema):
		"""recreates our data in an SQL database.

		cf. exportToSQL.
		"""
		if self.recordDef.get_create():
			self._exportToMetaTable(schema)
		if not self.metaOnly:
			tableWriter = self._getOwnedTableWriter(schema)
			gavo.ui.displayMessage("Exporting %s to table %s"%(
				self.getDataId(), tableWriter.getTableName()))
			self._feedData(tableWriter.getFeeder())
			tableWriter.finish()

	def _getSharedTableWriter(self):
		"""returns a sqlsupportTableWriter instance for this data set's
		target Table.

		These ignore the schema of the rd since it's in all likelihood
		not theirs.  In other words: Shared tables must always lie in the
		public schema.
		"""
# XXX do we want a "system" or "shared" schema for these?
		tableName = self.recordDef.get_table()
		tableWriter = sqlsupport.TableWriter(tableName,
			self.recordDef.get_items(), self.dbConnection)
		if self.recordDef.get_owningCondition():
			colName, colVal = self.recordDef.get_owningCondition()
			tableWriter.deleteMatching((colName, parsehelpers.atExpand(
				colVal, {}, self.dataSet.getDescriptor().getRd().get_atExpander())))
		return tableWriter

	def _getTableUpdater(self, schema):
		tableName = "%s.%s"%(schema, self.recordDef.get_table())
		return sqlsupport.TableUpdater(tableName,
			self.recordDef.get_items(), self.dbConnection)

	def _exportSharedTable(self):
		"""updates data owned by this data set.

		cf. exportToSql
		"""
		if not self.metaOnly:
			tableWriter = self._getSharedTableWriter()
			gavo.ui.displayMessage("Exporting %s to table %s"%(
				self.getDataId(), tableWriter.getTableName()))
	# XXX TODO: make dropIndices configurable
			self._feedData(tableWriter.getFeeder(dropIndices=False))
			tableWriter.finish()

	def exportToSql(self, schema):
		"""writes the data table to an SQL database.

		This method only knows about table names.  The details
		of the data base connection (db name, dsn, etc.) are
		handled in sqlsupport.
		"""
		if self.recordDef.get_shared():
			self._exportSharedTable()
		else:
			self._exportOwnedTable(schema)


class UniqueForcedTable(Table):
	"""is a table that enforces primary key uniqueness.

	This means that we keep an index of seen primary keys, and if a
	record comes the with a duplicate primary key, we check if it's
	the same record as the one we have.  If it is, it is discarded,
	if it is not, an error is raised.

	For now, this only works for atomic primary keys.
	"""
	def __init__(self, *args, **kwargs):
		Table.__init__(self, *args, **kwargs)
		self.primaryName = self.recordDef.getPrimary().get_dest()
		try:
			self.resolveConflict = {
				"check": self._ensureRecordIdentity,
				"drop": self._dropNew,
				"overwrite": self._overwriteOld,
			}[self.recordDef.get_conflicts()]
		except KeyError, msg:
			raise gavo.Error("Invalid conflict resolution strategy: %s"%str(msg))
		self.primaryIndex = {}

	def _ensureRecordIdentity(self, record, key):
		"""raises an exception if record is not equivalent to the record stored
		for key.

		This is one strategy for resolving primary key conflicts.
		"""
		storedRec = self.primaryIndex[key]
		if record.keys()!=storedRec.keys():
			raise gavo.Error("Differing records for primary key %s: %s vs. %s"%(
				key, self.primaryIndex[key], record))
		for fieldName in record:
			if record[fieldName]!=storedRec[fieldName]:
				raise gavo.ValidationError(
					"Differing records for primary key %s;"
					" %s vs. %s"%(key, record[fieldName],
						storedRec[fieldName]), fieldName=fieldName, record=record)

	def _dropNew(self, record, key):
		"""does nothing.

		This is for resolution of conflicting records (the "drop" strategy).
		"""
		pass
	
	def _overwriteOld(self, record, key):
		"""overwrites the existing record with key in table with record.

		This is for resolution of conflicting records (the "overwrite"
		strategy).

		Warning: This is typically rather slow.
		"""
		storedRec = self.primaryIndex[key]
		self.removeData(storedRec)
		del self.primaryIndex[key]
		return self.addData(record)

	def addData(self, record):
		key = record[self.primaryName]
		if key in self.primaryIndex:
			return self.resolveConflict(record, key)
		else:
			self.primaryIndex[key] = record
		return Table.addData(self, record)


class DirectWritingTable(Table):
	"""is a table that doesn't keep data of its own but dumps everything
	into an sql table right away.

	This is evidently handy when you're talking large data sets.

	Right now, getRow and friends don't work for these (though one
	could, in principle, grab the stuff from the DB if it were really
	necessary at some point).

	Calling the finishBuild method is particularly important here -- if you
	don't the table will remain empty.
	"""
	nUpdated = None
	def __init__(self, dataSet, recordDef, dbConnection=None,
			doUpdates=False, dropIndices=False):
		self.dbConnection = dbConnection
		Table.__init__(self, dataSet, recordDef)
		if doUpdates:
			self.tableWriter = self._getTableUpdater(
				self.dataSet.getRd().get_schema())
		else:
			if self.recordDef.get_shared():
				self.tableWriter = self._getSharedTableWriter()
			else:
				self.tableWriter = self._getOwnedTableWriter(
					self.dataSet.getRd().get_schema())
		self.feeder = self.tableWriter.getFeeder(dropIndices=dropIndices)

	def getTableName(self):
		return self.tableWriter.getTableName()

	def addData(self, record):
		self.feeder(record)

	def finishBuild(self):
		self.nUpdated = self.feeder.close()
		Table.finishBuild(self)
		self.tableWriter.finish()

	def exportToSql(self, schema):
		return

	def copyIn(self, copySrc):
		"""initiates a binary copy from file copySrc to the table.
		"""
		cp = sqlsupport.Copier(self.name, self.dbConnection)
		cp.copyIn(copySrc)
