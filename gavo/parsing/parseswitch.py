"""
Code to decide how to parse with a given grammar.

Right now, we either simply call the parse method of the grammar or
start a cgbooster.  More special handling of this kind may be necessary
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
from gavo.parsing import resource


class BoosterException(gavo.Error):
	pass

class BoosterNotDefined(BoosterException):
	pass

class BoosterNotAvailable(BoosterException):
	pass

class BoosterFailed(BoosterException):
	pass


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
	def __init__(self, id, recordDef):
		self.id = id
		self.recordDef = recordDef
		self.rows = []
		self.dumpOnly = False

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

	def getId(self):
		return self.id

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
			self.recordDef.getSqlFielddef())
		tableExporter.ensureSchema(schema)
		tableExporter.createTable()
		self._exportToMetaTable(schema)
		return tableExporter

	def _exportOwnedTable(self, schema):
		"""recreates our data in an SQL database.

		cf. exportToSql.
		"""
		tableWriter = self._getOwnedTableWriter(schema)
		gavo.ui.displayMessage("Exporting %s to table %s"%(
			self.getId(), tableWriter.getTableName()))
		self._feedData(tableWriter.getFeeder())

	def _getSharedTableWriter(self):
		"""returns a sqlsupportTableWriter instance for this data set's
		target Table.
		"""
		tableName = self.recordDef.get_table()
		tableWriter = sqlsupport.TableWriter(tableName,
			self.recordDef.getSqlFielddef())
		tableWriter.deleteMatching(self.recordDef.get_owningCondition())
		return tableWriter

	def _exportSharedTable(self):
		"""updates data owned by this data set.

		cf. exportToSql
		"""
		tableWriter = self._getSharedTableWriter()
		gavo.ui.displayMessage("Exporting %s to table %s"%(
			self.getId(), tableWriter.getTableName()))
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

	To make this work, we need to know the sql schema name
	up front, so the Table and DirectWritingTable have different constructor
	interfaces.  Also, getRow and friends don't work (though one
	could, in principle, grab the stuff from the DB if it were really
	necessary at some point).

	You need to call an instance's close method when done with it.
	"""
	def __init__(self, id, recordDef, schema):
		Table.__init__(self, id, recordDef)
		if self.recordDef.get_shared():
			self.tableWriter = self._getSharedTableWriter()
		else:
			self.tableWriter = self._getOwnedTableWriter(schema)
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
	if not isinstance(grammar, columngrammar.ColumnGrammar):
		raise BoosterNotDefined("Boosters only work for ColumnGrammars")
	host, port, dbname = config.settings.get_db_dsn().split(":")
	booster = grammar.get_booster()
	if booster==None:
		raise BoosterNotDefined
	booster = os.path.join(descriptor.get_resdir(), booster)
	if grammar.get_local():
		connDesc = "dbname=%s\n"%dbname
	else:
		connDesc = "host=%s port=%s user=%s password=%s dbname=%s\n"%(
			host, port, config.settings.get_db_user(), 
			config.settings.get_db_password(), dbname)
	f = os.popen("%s '%s' '%s'"%(booster, inputFileName, tableName), "w")
	f.write(connDesc)
	f.flush()
	retval = f.close()
	if retval!=None:
		retval = (retval&0xff00)>>8
	if retval==126: 
		raise BoosterNotAvailable("Invalid binary format")
	if retval==127:
		raise BoosterNotAvailable("Binary not found")
	if retval:
		raise BoosterFailed()


def _parseSource(src, grammar, descriptor, tables):
	"""uses grammar to parse src.

	This is the place to teach the program special tricks to bypass
	the usual source processing using grammars.
	"""
	if len(tables)==1 and isinstance(tables[0], DirectWritingTable):
		try:
			_tryBooster(grammar, src, tables[0].getTableName(), descriptor)
			return
		except BoosterNotDefined:
			pass
		except BoosterNotAvailable, msg:
			gavo.ui.displayMessage("Booster defined, but not available"
				" (%s).  Falling back to normal parse."%msg)
		except BoosterFailed:
			raise gavo.Error("Booster failed.")
	grammar.parse(src)


def _parseSources(grammar, srcDesc, descriptor, tables):
	"""applies grammar to all sources given by descriptor.

	In the standard case, neither descriptor nor tables is actually
	needed, since everything has been set up before.  However, to
	enable tricks in _parseSource, we pass these things through.
	"""
	counter = gavo.ui.getGoodBadCounter("Parsing source(s)", 5)
	for src in srcDesc.iterSources():
		try:
			_parseSource(src, grammar, descriptor, tables)
		except gavo.StopOperation, msg:
			gavo.logger.warning("Prematurely aborted %s (%s)."%(
				src, str(msg).decode("utf-8")))
			break
		except gavo.Error, msg:
			logger.error("Error while parsing %s (%s) -- aborting source."%(
				src, str(msg).decode("utf-8")))
			counter.hitBad()
		except KeyboardInterrupt:
			logger.warning("Interrupted while processing %s.  Quitting"
				" on user request"%src)
			raise
		except (UnicodeDecodeError, sqlsupport.OperationalError), msg:
			# these are most likely due to direct writing
			logger.error("Error while exporting %s (%s) -- aborting source."%(
				src, str(msg)))
		except Exception, msg:
			logger.error("Unexpected exception while parsing %s.  See"
				" log.  Source is ignored."%src, exc_info=sys.exc_info())
			counter.hitBad()
		counter.hit()
	counter.close()

def getDataset(srcDesc, descriptor, dumpOnly=False, debugProductions=[],
			maxRows=None, directWriting=False):
	"""parses the data source described by descriptor returns a DataSet.
	containing the data and the governing semantics.
	"""
	grammar = srcDesc.get_Grammar()
	grammar.enableDebug(debugProductions)
	if directWriting:
		tables = [DirectWritingTable(srcDesc.get_id(), recordDef, 
				descriptor.get_schema())
			for recordDef in srcDesc.get_Semantics().get_recordDefs()]
	else:
		tables = [Table(srcDesc.get_id(), recordDef)
			for recordDef in srcDesc.get_Semantics().get_recordDefs()]
	data = resource.DataSet(srcDesc.get_id(), tables)
	data.setHandlers(srcDesc, maxRows)
	_parseSources(grammar, srcDesc, descriptor, tables)
	if directWriting:
		for table in tables:
			table.close()
	return data
