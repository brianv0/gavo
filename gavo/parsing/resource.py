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
from gavo.datadef import DataField

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
			"create": utils.BooleanField,  # create table?
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

	def _runParsing(self, src, grammar, descriptor):
		"""decides how the current source is to be parsed and then starts
		the parsing.
		"""
		grammar.parse(open(src))

	def importData(self, opts):
		"""reads all data sources and applies all resource processors to them.
		"""
		from gavo.parsing import parseswitch

		for dataSrc in self.getDescriptor().get_dataSrcs():
			gavo.ui.displayMessage("Importing %s"%dataSrc.get_id())
			self.addDataset(parseswitch.getDataset(dataSrc, self.getDescriptor(),
				debugProductions=opts.debugProductions, maxRows=opts.maxRows,
				directWriting=opts.directWriting))
		for processor in self.getDescriptor().get_processors():
			processor(self)

	def addDataset(self, dataset):
		self.dataSets.append(dataset)

	def removeDataset(self, id):
		self.dataSets = [ds for ds in self if ds.getId()!=id]

	def getDescriptor(self):
		return self.desc

	def exportToSql(self):
		for dataSet in self:
			dataSet.exportToSql(self.getDescriptor().get_schema())
		sqlRunner = sqlsupport.ScriptRunner()
		for scriptType, scriptName, script in self.getDescriptor().get_scripts():
			gavo.ui.displayMessage("Running script %s"%scriptName)
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
