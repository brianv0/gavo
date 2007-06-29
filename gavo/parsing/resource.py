"""
This module contains code defining and processing resources.
"""

import os
import sys
import weakref

import gavo
from gavo import utils
from gavo import sqlsupport
from gavo import logger

class Error(gavo.Error):
	pass

class ValidationError(Error):
	pass


def getMetaTableRecordDef(tableName):
	"""returns a RecordDef suitable for meta tables.

	Meta tables are the ones that keep information on units, ucds, etc

	It is computed from sqlsupport's definition of the table in
	metaTableFields.  Unfortunately, DataField.getMetaRow
	also depends on that structure, so if anything serious changes
	in metaTableFields, you'll have to do work there, too.
	"""
	metaDef = RecordDef()
	metaDef.set_table(tableName)
	metaDef.addto_items(DataField(dest="tableName", dbtype="text",
		default=tableName))
	for fieldName, dbtype, options in sqlsupport.metaTableFields:
		metaDef.addto_items(DataField(dest=fieldName, dbtype=dbtype))
	return metaDef


class DataField(utils.Record):
	"""is a description of a data field.

	The primary feature of a data field is dest, which is used for, e.g.,
	the column name in a database.  Thus, they must be unique within
	a RecordDef.  The type information is also given for SQL dbs (or
	rather, postgresql), in dbtype.  Types for python or VOTables should
	be derivable from them, I guess.
	"""
	def __init__(self, **initvals):
		utils.Record.__init__(self, {
			"dest": utils.RequiredField,   # Name (used as column name in sql)
			"source": None,      # preterminal name to fill field from
			"default": None,     # constant value to fill field with
			"dbtype": "real",    # SQL type of this field
			"unit": None,        # physical unit of the value
			"ucd": None,         # ucd classification of the value
			"description": None, # short ("one-line") description
			"longdescription": None,  # long description
			"longmime": None,    # mime-type of contents of longdescription
			"tablehead": None,   # name to be used as table heading
			"utype": None,       # a utype
			"nullvalue": "",     # value to interpret as NULL/None
			"optional": utils.TrueBooleanField,  # NULL values in this field 
			                                     # don't invalidate record
			"literalForm": None, # special literal form that needs preprocessing
			"primary": utils.BooleanField,  # is part of the table's primary key
			"references": None,  # becomes a foreign key in SQL
			"index": None,       # if given, name of index field is part of
		})
		for key, val in initvals.iteritems():
			self.set(key, val)

	def getMetaRow(self):
		"""returns a dictionary ready for inclusion into the meta table.

		The keys have to match the definition sqlsupport.metaTableFields,
		so if these change, you will have to mirror these changes here.

		Since MetaTableHandler adds the tableName itself, we don't return
		it (also, we simply don't know it...).
		"""
		return {
			"fieldName": self.get_dest(),
			"unit": self.get_unit(),
			"ucd": self.get_ucd(),
			"description": self.get_description(),
			"tablehead": self.get_tablehead(),
			"longdescr": self.get_longdescription(),
			"longmime": self.get_longmime(),
			"literalForm": self.get_literalForm(),
			"utype": self.get_utype(),
			"type": self.get_dbtype(),
		}


class RecordDef(utils.Record):
	"""is a specification for the semantics of a table line.
	"""
	def __init__(self):
		utils.Record.__init__(self, {
			"table": utils.RequiredField,  # name of destination table
			"items": utils.ListField,      # list of FieldDefs for this record
			"constraints": None,        # a Constraints object rows have to satisfy
			"owningCondition": None,    # a condition to select our data from
			                            # shared tables.
			"shared": utils.BooleanField,  # is this a shared table?
		})
		self.fieldIndexDict = {}

	def _validate(self, record):
		"""checks that record complies with all known constraints on
		the data set.

		The function raises a ValidationError with an appropriate message
		if not.
		"""
		for field in self.get_items():
			if not field.get_optional() and record.get(field.get_dest())==None:
				raise ValidationError("%s is None but non-optional"%field.get_dest())

	def addto_items(self, item):
		if self.fieldIndexDict.has_key(item.get_dest()):
			raise Error("Duplicate field name: %s"%item.get_dest())
		self.fieldIndexDict[item.get_dest()] = len(self.get_items())
		self.get_items().append(item)

	def getPrimary(self):
		for field in self.items:
			if field.get_primary():
				break
		else:
			raise Error("No primary field defined.")
		return field

	def getSqlFielddef(self):
		"""returns a field definiton suitable for sqlsupport.TableWriter.
		"""
		def makeOpts(field):
			opts = {}
			if not field.get_optional():
				opts["notnull"] = True
			if field.get_index():
				opts["index"] = field.get_index()
			if field.get_references():
				opts["references"] = field.get_references()
			if field.get_primary():
				opts["primary"] = True
			return opts

		sqlFields = []
		for field in self.get_items():
			sqlFields.append((field.get_dest(), field.get_dbtype(),
			 makeOpts(field)))
		return sqlFields

	def getFieldIndex(self, fieldName):
		"""returns the index of the field named fieldName.
		"""
		return self.fieldIndexDict[fieldName]


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
				logger.error("Row %s bad (%s).  Ignoring."%(row, msg))
				counter.hitBad()
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
		"""recreates a table to an SQL database.

		cf. exportToSql.
		"""
		tableExporter = self._getOwnedTableWriter(schema)
		gavo.ui.displayMessage("Exporting %s to table %s"%(
			self.getId(), tableName))
		self._feedData(tableExporter.getFeeder())

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
			self.getId(), tableName))
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

	To make this working, we need to know the sql schema name
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
	
	def addData(self, record):
		self.feeder(record)

	def getRow(self, key):
		raise "DirectWritingTables cannot retrieve rows."

	def close(self):
		self.feeder.close()

	def exportToSql(self, schema):
		return
		

class DataSet:
	"""is a collection of all Tables coming from one source.
	"""
	def __init__(self, id, tables):
		self.tables = tables
		self.id = id

	def getId(self):
		return self.id

	def exportToSql(self, schema):
		for table in self.tables:
			table.exportToSql(schema)

	def setHandlers(self, descriptor, maxRows):
		"""makes descriptor set up handlers for all tables belonging to self.
		"""
		for table in self.tables:
			descriptor.setHandlers(table, maxRows=maxRows)


class Resource:
	"""is a model for a resource containing data sets and metadata.

	The real definition is contained in the descriptor -- Resource
	mainly defines the operations governed by the information in
	that file.

	It and the objects embedded roughly correspond to a VOTable.
	We may want to replace this class by some VOTable implementation.
	"""
	def __init__(self, descriptor):
		self.desc = descriptor
		self.dataSets = []

	def __iter__(self):
		"""iterates over all data sets contained in this resource.
		"""
		return iter(self.dataSets)

	def getDatasetById(self, id):
		"""returns the data set for id.

		This is currently implemented through linear search.  That shouldn't
		hurt, because we have few data sets and this method is rarely
		called.
		"""
		for ds in self:
			if id==ds.getId():
				break
		else:
			raise Error("No data set %s in this resource"%id)
		return ds

	def parseOne(self, descriptor, dumpOnly=False, debugProductions=[],
			maxRows=None, directWriting=False):
		"""parses the data source described by descriptor returns a DataSet 
		containing the data and the governing semantics.
		"""
		grammar = descriptor.get_Grammar()
		grammar.enableDebug(debugProductions)
		if directWriting:
			tables = [DirectWritingTable(descriptor.get_id(), recordDef, 
					self.desc.get_schema())
				for recordDef in descriptor.get_Semantics().get_recordDefs()]
		else:
			tables = [Table(descriptor.get_id(), recordDef)
				for recordDef in descriptor.get_Semantics().get_recordDefs()]
		data = DataSet(descriptor.get_id(), tables)
		data.setHandlers(descriptor, maxRows)

		counter = gavo.ui.getGoodBadCounter("Parsing source(s)", 5)
		for src in descriptor.iterSources():
			try:
				grammar.parse(open(src))
			except gavo.StopOperation, msg:
				gavo.logger.warning("Prematurely aborted %s (%s)."%(
					src, str(msg).decode("utf-8")))
				break
			except gavo.Error, msg:
				logger.error("Error while parsing %s (%s) -- ignoring source."%(
					src, str(msg).decode("utf-8")))
				counter.hitBad()
			except KeyboardInterrupt:
				logger.warning("Interrupted while processing %s.  Quitting"
					" on user request"%src)
				sys.exit(1)
			except Exception, msg:
				logger.error("Unexpected exception while parsing %s.  See"
					" log.  Source is ignored."%src, exc_info=sys.exc_info())
				counter.hitBad()
			counter.hit()
		counter.close()
		if directWriting:
			for table in tables:
				table.close()
		return data

	def importData(self, opts):
		"""reads all data sources and applies all resource processors to them.
		"""
		for dataSrc in self.desc.get_dataSrcs():
			gavo.ui.displayMessage("Importing %s"%dataSrc.get_id())
			self.addDataset(self.parseOne(dataSrc, 
				debugProductions=opts.debugProductions, maxRows=opts.maxRows,
				directWriting=opts.directWriting))
		for processor in self.desc.get_processors():
			processor(self)

	def addDataset(self, dataset):
		self.dataSets.append(dataset)

	def removeDataset(self, id):
		self.dataSets = [ds for ds in self if ds.getId()!=id]

	def getDescriptor(self):
		return self.desc

	def exportToSql(self):
		for dataSet in self:
			dataSet.exportToSql(self.desc.get_schema())
		sqlRunner = sqlsupport.ScriptRunner()
		for scriptType, script in self.desc.get_scripts():
			if scriptType=="postCreation":
				sqlRunner.run(script)
		sqlRunner.commit()
	
	def rebuildDependents(self):
		"""executes the appropriate make commands to build everything that
		may have changed due to the current import.

		Errors are currently ignored, since it would be a pain if some minor
		error in one project would inhibit the rebuild of another.  But clearly,
		we should flag problems more prominently lest they disappear in the usual
		make linestorm.
		"""
		for dep in self.getDescriptor().get_dependents():
			os.system("cd %s; make update"%(os.path.join(gavo.inputsDir, dep)))
