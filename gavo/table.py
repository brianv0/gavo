"""
Table classes.
"""

import weakref
import warnings
import compiler

import gavo
from gavo import logger
from gavo import sqlsupport
from gavo.parsing import meta
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
		self.maxRows = None
		self.fieldDefs = fieldDefs
		self.name = name
		self.rows = []
	
	def __iter__(self):
		return iter(self.rows)

	def __len__(self):
		return len(self.rows)

	def __getitem__(self, index):
		return self.rows[index]

	def setMaxRows(self, maxRows):
		"""sets after how many rows an attempt to add a row will raise a
		gavo.StopOperation exception.

		This is for debugging (e.g., of resource descriptors) only.
		"""
		self.maxRows = maxRows

	def finishBuild(self):
		pass

	def setDumpOnly(self, dumpOnly):
		"""ignored, no longer supported.
		"""
		warnings.warn("setDumpOnly no longer supported.")

	def addData(self, record):
		self.rows.append(record)
		if self.maxRows and len(self.rows)>=self.maxRows:
			raise gavo.StopOperation("Abort due to maxRows=%d"%self.maxRows)

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
	create = True

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
		"""
		counter = gavo.ui.getGoodBadCounter("Writing to db", 100)
		for row in self.rows:
			try:
				counter.hit()
				feed(row)
			except (UnicodeDecodeError, sqlsupport.OperationalError), msg:
				logger.error("Row %s bad (%s).  Aborting."%(row, msg))
				gavo.ui.displayError("Import of row %s failed (%s). ABORTING"
					" OPERATION."%(row, msg))
				raise # XXXXXXXXX should emit err msg wherever this is caught.
		counter.close()
		feed.close()

	def _getOwnedTableWriter(self, schema):
		tableName = "%s.%s"%(schema, self.recordDef.get_table())
		tableExporter = sqlsupport.TableWriter(tableName,
			self.recordDef.get_items(), self.dbConnection)
		tableExporter.ensureSchema(schema)
		if self.create:
			tableExporter.createTable(create=self.recordDef.get_create(),
				privs=self.recordDef.get_create())
		return tableExporter

	def _exportOwnedTable(self, schema):
		"""recreates our data in an SQL database.

		cf. exportToSql.
		"""
		self._exportToMetaTable(schema)
		if not self.metaOnly:
			tableWriter = self._getOwnedTableWriter(schema)
			gavo.ui.displayMessage("Exporting %s to table %s"%(
				self.getDataId(), tableWriter.getTableName()))
			self._feedData(tableWriter.getFeeder())

	def _getSharedTableWriter(self):
		"""returns a sqlsupportTableWriter instance for this data set's
		target Table.
		"""
		tableName = self.recordDef.get_table()
		tableWriter = sqlsupport.TableWriter(tableName,
			self.recordDef.get_items(), self.dbConnection)
		if self.recordDef.get_owningCondition():
			colName, colVal = self.recordDef.get_owningCondition()
			tableWriter.deleteMatching((colName, parsehelpers.atExpand(
				colVal, {}, self.dataSet.getDescriptor().getRD().get_atExpander())))
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
			self._feedData(tableWriter.getFeeder())

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
	def __init__(self, dataSet, recordDef, dbConnection=None, create=True,
			doUpdates=False):
		self.create = create
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
		self.feeder = self.tableWriter.getFeeder()

	def getTableName(self):
		return self.tableWriter.getTableName()

	def addData(self, record):
		self.feeder(record)

	def finishBuild(self):
		self.nUpdated = self.feeder.close()
		Table.finishBuild(self)

	def exportToSql(self, schema):
		return

