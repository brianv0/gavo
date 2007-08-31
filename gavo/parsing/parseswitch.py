"""
Code that abstracts the parsing process.

Right now, we either simply call the parse method of the grammar or
start a cgbooster.  More special handling may be necessary
in the future.

cgboosters are C programs that are supposed to implement what ColumnGrammars
do.  Later on, we probably have people drop a C function into the res directory
and compile the stuff automatically.  For now, we hack the stuff such that the
protype (for ppmx) runs.
"""

import os
import sys

import gavo
from gavo import config
from gavo import sqlsupport
from gavo import logger
from gavo.parsing import columngrammar
from gavo.parsing import parsehelpers
from gavo.parsing import resource


class BoosterException(gavo.Error):
	pass

class BoosterNotDefined(BoosterException):
	pass

class BoosterNotAvailable(BoosterException):
	pass

class BoosterFailed(BoosterException):
	pass

# XXX TODO: Split off SQL related stuff into Table, leave the rest as BaseTable
class Table:
	"""is a container for essentially homogenous data.

	For SQL, this is a model for a table, with the twist that it
	also holds non-SQL metadata for the table.

	A Table is constructed with an id (the table name in SQL, schema
	qualification is allowed) and list for DataFields, which is used
	to set up the meta data and the addData method.

	The addData method takes a record, i.e., a dictionary mapping keys
	(corresponding to dest in DataField) to values (which usually
	come from the parser).
	"""
	def __init__(self, dataId, recordDef, resourceDescriptor, metaOnly=False):
		self.rd = resourceDescriptor
		self.dataId = dataId
		self.recordDef = recordDef
		self.rows = []
		self.dumpOnly = False
		self.metaOnly = metaOnly

	def __iter__(self):
		return iter(self.rows)

	def setDumpOnly(self, dumpOnly):
		self.dumpOnly = dumpOnly

	def _buildRowIndex(self):
		primaryIndex = self.recordDef.getFieldIndex(
			self.recordDef.getPrimary().get_dest())
		self.rowIndex = dict([(row[primaryIndex], row)
			for row in self])

	def addData(self, record):
		"""adds a record to the table.

		The tables are kept as lists of dictionaries (as opposed to
		tuples) because that's how we'll insert them into the database.
		"""
		if self.dumpOnly:
			print record
		self.rows.append(record)
	
	def getFieldDefs(self):
		"""returns the field Definitions.

		Do not change the result.  It is *not* a copy.
		"""
		return self.recordDef.get_items()

	def getRecordDef(self):
		return self.recordDef

	def getDataId(self):
		return self.dataId

	def getRow(self, key):
		"""returns the row with the primary key key.
		"""
		try:
			return self.rowIndex["key"]
		except AttributeError:
			self._buildRowIndex()
			return self.rowIndex["key"]

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
			self.recordDef.get_items())
		tableExporter.ensureSchema(schema)
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
			self.recordDef.get_items())
		colName, colVal = self.recordDef.get_owningCondition()
		tableWriter.deleteMatching((colName, parsehelpers.atExpand(
			colVal, {}, self.rd.get_atExpander())))
		return tableWriter

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

	You need to call an instance's close method when done with it.
	"""
	def __init__(self, id, recordDef, rd):
		Table.__init__(self, id, recordDef)
		self.rd = rd
		if self.recordDef.get_shared():
			self.tableWriter = self._getSharedTableWriter()
		else:
			self.tableWriter = self._getOwnedTableWriter(self.rd.get_schema())
		self.feeder = self.tableWriter.getFeeder()

	def getTableName(self):
		return self.tableWriter.getTableName()

	def addData(self, record):
		self.feeder(record)

	def getRow(self, key):
		raise "DirectWritingTables cannot retrieve rows."

	def close(self):
		self.feeder.close()

	def exportToSql(self, schema):
		return
		

def _tryBooster(grammar, inputFileName, tableName, descriptor):
	booster = grammar.get_booster()
	if booster==None:
		raise BoosterNotDefined
	connDesc = config.getDbProfile().getDsn()
	booster = os.path.join(descriptor.get_resdir(), booster)
	try:
		f = os.popen("%s '%s' '%s'"%(booster, inputFileName, tableName), "w")
		f.write(connDesc)
		f.flush()
		retval = f.close()
	except IOError, msg:
		if msg.errno==32:
			raise BoosterNotAvailable("Broken pipe")
		else:
			raise
	if retval!=None:
		retval = (retval&0xff00)>>8
	if retval==126: 
		raise BoosterNotAvailable("Invalid binary format")
	if retval==127:
		raise BoosterNotAvailable("Binary not found")
	if retval:
		raise BoosterFailed()

def _tryBooster(parseContext):
	"""checks if we can run a booster and returns True if a booster
	was run successfully and False if not.
	"""
	try:
		grammar = parseContext.getDataSet().getDescriptor().get_Grammar()
		if not isinstance(grammar, columngrammar.ColumnGrammar):
			raise BoosterNotDefined("Boosters only work for ColumnGrammars")
		tables = parseContext.getDataSet().getTables() 
		if len(tables)!=1 or not isinstance(tables[0], DirectWritingTable):
			raise BoosterNotDefined("Boosters only work for for single direct"
				" writing tables")
		_runBooster(grammar, src, tables[0].getTableName(), descriptor)
	except BoosterNotDefined:
		return False
	except BoosterNotAvailable, msg:
		gavo.ui.displayMessage("Booster defined, but not available"
			" (%s).  Falling back to normal parse."%msg)
		return False
	except BoosterFailed:
		raise gavo.Error("Booster failed.")
	return True


def _parseSource(parseContext):
	"""actually executes the parse process described by parseContext.

	This is the place to teach the program special tricks to bypass
	the usual source processing using grammars.
	"""
	if not _tryBooster(parseContext):
		parseContext.parse()


def _parseSources(data):
	"""parses all sources requrired to fill the DataSet data.
	"""
	counter = gavo.ui.getGoodBadCounter("Parsing source(s)", 5)
	for context in data.iterParseContexts():
		try:
			_parseSource(context)
		except gavo.StopOperation, msg:
			gavo.logger.warning("Prematurely aborted %s (%s)."%(
				context.sourceName, str(msg).decode("utf-8")))
			break
		except KeyboardInterrupt:
			logger.warning("Interrupted while processing %s.  Quitting"
				" on user request"%context.sourceName)
			raise
		except (UnicodeDecodeError, sqlsupport.OperationalError), msg:
			# these are most likely due to direct writing
			logger.error("Error while exporting %s (%s) -- aborting source."%(
				context.sourceName, str(msg)))
			counter.hitBad()
		except (gavo.Error, Exception), msg:
			errMsg = ("Error while parsing %s (%s) -- aborting source."%(
				context.sourceName, str(msg).decode("utf-8")))
			logger.error(errMsg, exc_info=True)
			gavo.ui.displayError(errMsg)
			counter.hitBad()

		counter.hit()
	counter.close()


def getDataset(srcDesc, descriptor, dumpOnly=False, debugProductions=[],
			maxRows=None, directWriting=False, metaOnly=False):
	"""parses the data source described by descriptor returns a DataSet.
	containing the data and the governing semantics.
	"""
	grammar = srcDesc.get_Grammar()
	grammar.enableDebug(debugProductions)
	if directWriting:
		tables = [DirectWritingTable(srcDesc.get_id(), recordDef, 
				descriptor)
			for recordDef in srcDesc.get_Semantics().get_recordDefs()]
	else:
		tables = [Table(srcDesc.get_id(), recordDef, descriptor, metaOnly)
			for recordDef in srcDesc.get_Semantics().get_recordDefs()]
	data = resource.DataSet(srcDesc, tables)
	if not metaOnly:
		_parseSources(data)
		if directWriting:
			for table in tables:
				table.close()
	return data
