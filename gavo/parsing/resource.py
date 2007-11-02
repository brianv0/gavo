"""
This module contains code defining and processing resources.
"""

import os
import re
import sys
import glob
import traceback

import gavo
from gavo import coords
from gavo import config
from gavo import datadef
from gavo import record
from gavo import sqlsupport
from gavo import logger
from gavo import utils
from gavo import votable
from gavo import table
from gavo import parsing
from gavo.datadef import DataField
from gavo.parsing import meta
from gavo.parsing import typeconversion
from gavo.parsing import tablegrammar
from gavo.parsing import parsehelpers

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


class Semantics(record.Record):
	"""is a specification for the semantics of nonterminals defined
	by the grammar.

	Basically, we have dataItems (which are global for the data source),
	and a recordDef (which defines what each record should look like).
	"""
	def __init__(self, initvals={}):
		record.Record.__init__(self, {
			"recordDefs": record.ListField,
		}, initvals=initvals)

	def getRecordDefByName(self, tablename):
		"""returns the RecordDef for table tablename.
		"""
		for recDef in self.get_recordDefs():
			if recDef.get_table()==tablename:
				return recDef
		raise KeyError(tablename)

	def clear_recordDefs(self):
		"""deletes all RecordDefs defined so far.

		This is necessary due to our crappy inheritance semantics for data
		descriptors and a clear sign that we should be doing the inheritance
		stuff differently...
		"""
		self.dataStore["recordDefs"] = []


class RecordDef(record.Record, meta.MetaMixin):
	"""is a specification for the semantics of a table line.
	"""
	def __init__(self, initvals={}):
		record.Record.__init__(self, {
			"table": record.RequiredField,  # name of destination table
			"items": record.ListField,      # list of FieldDefs for this record
			"constraints": None,        # a Constraints object rows have to satisfy
			"owningCondition": None,    # a condition to select our data from
			                            # shared tables.
			"shared": record.BooleanField,  # is this a shared table?
			"create": record.BooleanField,  # create table?
			"onDisk": record.BooleanField,  # write parsed data directly?
		}, initvals)
		self.fieldIndexDict = {}

	def __repr__(self):
		return "<RecordDef %s, %s>"%(id(self), id(self.get_items()))

	def validate(self, record):
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

	def set_items(self, items):
		self.fieldIndexDict = {}
		self.dataStore["items"] = []
		for item in items:
			self.addto_items(item)

	def getPrimary(self):
		for field in self.get_items():
			if field.get_primary():
				break
		else:
			raise Error("No primary field defined.")
		return field

	def getFieldIndex(self, fieldName):
		"""returns the index of the field named fieldName.
		"""
		return self.fieldIndexDict[fieldName]

	def copy(self):
		theCopy = record.Record.copy(self)
		theCopy.fieldIndexDict = self.fieldIndexDict.copy()
		return theCopy


class ParseContext:
	"""encapsulates the data specific to parsing one source and provides
	the methods for exporting data.

	Parse contexts provide the following items to grammars:

	* The attributes sourceFile and sourceName
	* The methods processDocdict and processRowdict to ship out
	  toplevel and row dictionaries
	* The function atExpand that provides @-expansions 

	For clarity: Grammars deliver dictionaries mapping keys (the
	preterminals) to values (which are strings), the rowdicts, to
	processRow (and analogously similar a similar dictionary to
	processDoc).  These have to be processed in multiple ways:

	* certain values may need to be computed using meta information
	  not available from the source itself (e.g., dates, paths).
	  Field computers are used for this.
	* string literals have to be converted to python values.  This
	  is done by the literal parser.
	
	After these manipulations, we have another dictionary mapping
	the dests of DataFields to python values.  This is what we call
	a record that's ready for ingestion into a db table or a VOTable.
	"""
# actually, the sourceName/ sourceFile interface is bad.  We need 
# abstraction, because basically, grammars should be able to read from
# anything.
	def __init__(self, sourceFile, grammar, dataSet, literalParser):
		if isinstance(sourceFile, basestring):
			self.sourceName = sourceFile
			self.sourceFile = open(self.sourceName)
		elif isinstance(sourceFile, dict):
			self.sourceName = "<dictionary>"
			self.sourceFile = sourceFile
		elif isinstance(sourceFile, table.Table):
			self.sourceName = "<parsed table>"
			self.sourceFile = sourceFile
		else:  # we assume it's something file-like
			self.sourceName = "<anonymous>"
			self.sourceFile = sourceFile
		self.dataSet = dataSet
		self.grammar = grammar
		self.literalParser = literalParser
		self.rowsProcessed = 0
		self.fieldComputer = parsehelpers.FieldComputer(self)
		self.rowTargets = self._makeRowTargets()

	def getDataSet(self):
		return self.dataSet

	def _makeRowTargets(self):
		return [(targetTable, targetTable.getRecordDef())
			for targetTable in self.dataSet.getTables()]

	def processRowdict(self, rowdict):
		"""is called by the grammar when a table line has been parsed.

		This method arranges for the record to be built, validates the
		finished record (i.e., makes sure all the non-optional fields are
		in place), checks constraints that may be defined and finally
		ships out the record.
		"""
		for targetTable, recordDef in self.rowTargets:
			targetTable.addData(self._buildRecord(recordDef, rowdict))
		self.rowsProcessed += 1
	
	def processDocdict(self, docdict):
		descriptor = self.dataSet.getDescriptor()
		for macro in descriptor.get_macros():
			macro(self.atExpand, docdict)
		self.dataSet.updateDocRec(self._buildRecord(descriptor, docdict))
	
	def _strToVal(self, field, rowdict):
		"""returns a python value appropriate for field's type
		from the values in rowdict (which may be a docdict as well).
		"""
		return self.literalParser.makePythonVal(
			field.getValueIn(rowdict, self.atExpand), 
			field.get_dbtype(), 
			field.get_literalForm())

	def _buildRecord(self, recordDef, rowdict):
		"""returns a record built from rowdict and recordDef's item definition.
		"""
		# Actually, this is being used for docdicts as well, which is a bit
		# clumsy because of the error message...
		record = {}
		try:
			for field in recordDef.get_items():
				record[field.get_dest()] = self._strToVal(field, rowdict)
		except Exception, msg:
			utils.raiseTb(gavo.Error, "Cannot convert row %s, field %s "
				" probably doesn't match its type %s (root cause: %s)"%(
					str(rowdict), field.get_dest(), field.get_dbtype(), msg))
		self._checkRecord(recordDef, rowdict, record)
		return record
	
	def _checkRecord(self, recordDef, rowdict, record):
		"""raises some kind of exception there is something wrong the record.
		"""
		recordDef.validate(record)
		if recordDef.get_constraints():
			if not recordDef.get_constraints().check(rowdict, record):
				raise gavo.InfoException("Record %s doesn't satisfy constraints,"
					" skipping."%record)

	def atExpand(self, val, rowdict):
		return parsehelpers.atExpand(val, rowdict, self.fieldComputer)

	def parse(self):
		self.grammar.parse(self)


class DataSet(meta.MetaMixin):
	"""is a collection of the data coming from one source.

	Think of a DataSet as the concrete object instanciated from a
	DataDescriptor (a Data element in a resource desciptor).

	As such, it contains the tables (which are "instances" of the
	Records in Semantics elements) and the global data parsed from
	the document (docRec with metadata docFields).

	A data set is constructed with the data descriptor, a function
	that returns empty table instances and optionally a function
	that does the actual parsing (which can override the parse
	function of the ParseContext).

	The tableMaker is a function receiving the dataSet and the record
	definition, the parseSwitcher, if defined, simply takes a parse
	context and arranges for the parse context's table to be filled.
	If no parseSwitcher is given, the parse method of the parse
	context will be called.
	"""
	def __init__(self, dataDescriptor, tableMaker, parseSwitcher=None, 
			tablesToBuild=[], maxRows=None, ignoreBadSources=False):
		self.tablesToBuild = set(tablesToBuild)
		self.dD = dataDescriptor
		self.setMetaParent(self.dD)
		self.maxRows, self.ignoreBadSources = maxRows, ignoreBadSources
		self.docFields = self.dD.get_items()
		self.docRec = {}
		self.tables = []
		self._fillTables(tableMaker, parseSwitcher)

	def _parseSources(self, parseSwitcher):
		"""parses all sources requrired to fill self.

		This will spew out a lot of stuff unless you set gavo.ui to NullUi
		or something similar.
		"""
		counter = gavo.ui.getGoodBadCounter("Parsing source(s)", 5)
		for context in self._iterParseContexts():
			try:
				if parseSwitcher:
					parseSwitcher(context)
				else:
					context.parse()
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
				if not self.ignoreBadSources:
					raise
			except (gavo.Error, Exception), msg:
				errMsg = ("Error while parsing %s (%s) -- aborting source."%(
					context.sourceName, str(msg).decode("utf-8")))
				counter.hitBad()
				if not self.ignoreBadSources:
					raise
			counter.hit()
		counter.close()

	def _fillTables(self, tableMaker, parseSwitcher):
		for recordDef in self.dD.get_Semantics().get_recordDefs():
			if (self.tablesToBuild and \
					not recordDef.get_table() in self.tablesToBuild):
				continue
			self.tables.append(tableMaker(self, recordDef))
			if self.maxRows:
				self.tables[-1].setMaxRows(self.maxRows)
		self._parseSources(parseSwitcher)
		for table in self.tables:
			table.finishBuild()

	def _iterParseContexts(self):
		"""iterates over ParseContexts for all sources the descriptor
		returns.
		"""
		literalParser = typeconversion.LiteralParser(self.dD.get_encoding())
		for src in self.dD.iterSources():
			yield ParseContext(src, self.dD.get_Grammar(),
				self, literalParser)

	def validate(self):
		self.dD.validate(self.docRec)

	def getId(self):
		return self.dD.get_id()

	def getTables(self):
		return self.tables

	def getPrimaryTable(self):
		return self.tables[0]

	def getDescriptor(self):
		return self.dD

	def updateDocRec(self, docRec):
		self.docRec.update(docRec)

	def getDocRec(self):
		return self.docRec

	def getDocFields(self):
		return self.docFields

	def exportToSql(self, schema):
		for table in self.tables:
			table.exportToSql(schema)

	def exportToVOTable(self, destination, tableNames=None, tablecoding="td",
			mapperFactories=[]):
		if tableNames==None:
			tableNames = [table.getName() for table in self.tables]
#		if len(tableNames)!=1:
#			raise Error("DataSets can't yet export to VOTable when containing"
#				" more than one table.")
		mapperFactoryRegistry = votable.getMapperRegistry()
		for mf in mapperFactories:
			mapperFactoryRegistry.registerFactory(mf)
		votable.writeVOTableFromTable(self,
			self.tables[0], destination, tablecoding,
			mapperFactoryRegistry=mapperFactoryRegistry)


class InternalDataSet(DataSet):
	"""is a data set that has a non-disk input.

	It is constructed with the data descriptor governing the data set,
	a class for generating tables (usually parseswitch.Table, a
	data source (anything ParseContext can handle) and optionally
	a sequence of table ids -- if this is given, only the specified tables
	are built.
	"""
	def __init__(self, dataDescriptor, tableMaker, dataSource, 
			tablesToBuild=[]):
		self.dataSource = dataSource
		DataSet.__init__(self, dataDescriptor, tableMaker, 
			tablesToBuild=tablesToBuild)
	
	def _iterParseContexts(self):
		literalParser = typeconversion.LiteralParser(self.dD.get_encoding())
		yield ParseContext(self.dataSource, self.dD.get_Grammar(), self,
			literalParser)


class SqlMacroExpander(object):
	"""is a collection of "Macros" that can be used in SQL scripts.

	This is a terrible hack, but there's little in the way of alternatives
	as far as I can see.
	"""
	def __init__(self, rd):
		self.rd = rd
		self.macrodict = {}
		for name in dir(self):
			if name.isupper():
				self.macrodict[name] = getattr(self, name)
	
	def _expandScriptMacro(self, matob):
		return eval(matob.group(1), self.macrodict)

	def expand(self, script):
		"""expands @@@...@@@ macro calls in SQL scripts
		"""
		return re.sub("@@@(.*?)@@@", self._expandScriptMacro, script)

	def TABLERIGHTS(self, tableName):
		return "\n".join(sqlsupport.getTablePrivSQL(tableName))
	
	def SCHEMARIGHTS(self, schema):
		return "\n".join(sqlsupport.getSchemaPrivSQL(schema))
	
	def SCHEMA(self):
		return self.rd.get_schema()


class Resource:
	"""is a model for a resource containing data sets and metadata.

	This, it is a concrete instance of data described by a 
	resource descriptor.

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
				debugProductions=getattr(opts, "debugProductions", None), 
				maxRows=getattr(opts, "maxRows", None),
				metaOnly=getattr(opts, "metaOnly", False), 
				ignoreBadSources=getattr(opts, "ignoreBadSources", False)))
		for processor in self.getDescriptor().get_processors():
			processor(self)

	def addDataset(self, dataset):
		self.dataSets.append(dataset)

	def removeDataset(self, id):
		self.dataSets = [ds for ds in self if ds.getId()!=id]

	def getDescriptor(self):
		return self.desc

	def exportToSql(self):
		if self.getDescriptor().get_profile():
			config.setDbProfile(self.getDescriptor().get_profile())
		for dataSet in self:
			dataSet.exportToSql(self.getDescriptor().get_schema())
		sqlRunner = sqlsupport.ScriptRunner()
		sqlMacroExpander = SqlMacroExpander(self.desc)
		for scriptType, scriptName, script in self.getDescriptor().get_scripts():
			gavo.ui.displayMessage("Running script %s"%scriptName)
			if scriptType=="postCreation":
				sqlRunner.run(sqlMacroExpander.expand(script))
		sqlRunner.commit()
		self.rebuildDependents()

	def exportNone(self):
		pass
	
	def exportToVOTable(self):
		for dataSet in self:
			dataSet.exportToVOTable(sys.stdout, tablecoding="td")

	def export(self, outputFormat):
		try: {
				"sql": self.exportToSql,
				"none": self.exportNone,
				"votable": self.exportToVOTable,
			}[outputFormat]()
		except KeyError:
			raise utils.raiseTb(gavo.Error,
				"Invalid export format: %s"%outputFormat)

	def rebuildDependents(self):
		"""executes the appropriate make commands to build everything that
		may have changed due to the current import.

		Errors are currently ignored, since it would be a pain if some minor
		error in one project would inhibit the rebuild of another.  But clearly,
		we should flag problems more prominently lest they disappear in the usual
		make linestorm.
		"""
		for dep in self.getDescriptor().get_dependents():
			os.system("cd %s; make update"%(os.path.join(
				config.get("inputsDir"), dep)))


class ResourceDescriptor(record.Record, meta.MetaMixin):
	"""is a container for all information necessary to import a resource into
	a VO data pool.
	"""
	def __init__(self, **initvals):
		record.Record.__init__(self, {
			"resdir": record.RequiredField, # base directory for source files
			"dataSrcs": record.ListField,   # list of data sources
			"processors": record.ListField, # list of resource processors
			"dependents": record.ListField, # list of projects to recreate
			"scripts": record.ListField,    # pairs of (script type, script)
			"adapter": record.DictField,    # data adapters and...
			"service": record.DictField,    # ...services for the data contained.
			"schema": None,    # Name of schema for that resource, defaults
			                   # to basename(resdir)
			"profile": None,   # override db profile used to create resource
			"atExpander": parsehelpers.RDComputer(self),
			"systems": coords.CooSysRegistry(),
		}, initvals)
		
	def set_resdir(self, relPath):
		"""sets resource directory, qualifing it and making sure
		there's no trailing slash.

		We don't want that trailing slash because some names
		fall back to basename(resdir).
		"""
		self.dataStore["resdir"] = os.path.join(config.get("inputsDir"), 
			relPath.rstrip("/"))

	def get_schema(self):
		return self.dataStore["schema"] or os.path.basename(
			self.dataStore["resdir"])
	
	def getDataById(self, id):
		"""returns the data source with id or raises a KeyError.
		"""
		for dataSrc in self.get_dataSrcs():
			if dataSrc.get_id()==id:
				return dataSrc
		raise KeyError(id)

	def notfiyParseFinished(self):
		for ds in self.get_dataSrcs():
			ds.setMetaParent(self)
		for key in self.itemsof_adapter():
			self.get_adapter(key).setMetaParent(self)
		for key in self.itemsof_service():
			self.get_service(key).setMetaParent(self)

	def getTableDefByName(self, name):
		"""returns the first RecordDef found with the matching name.

		This is a bit of a mess since right now we don't actually enforce
		unique table names and in some cases even force non-unique names.
		"""
		for ds in self.get_dataSrcs():
			for tableDef in ds.get_Semantics().get_recordDefs():
				if tableDef.get_table()==name:
					return tableDef


class DataDescriptor(datadef.DataTransformer):
	"""is a DataTransformer for reading data from files or external processes.
	"""
	def __init__(self, parentResource, **initvals):
		datadef.DataTransformer.__init__(self, parentResource, 
			additionalFields = {
				"source": None,    # resdir-relative filename of source
				                   # for single-file sources
				"sourcePat": None, # resdir-relative shell pattern of sources for
				                   # one-row-per-file sources
				"computer": None,  # rootdir-relative path of an executable producing 
				                   # the data
				"name": None,      # a terse human-readable description of this data
			},
			initvals=initvals)

	def get_source(self):
		if self.dataStore["source"]:
			return os.path.join(self.rD.get_resdir(), 
				self.dataStore["source"])

	def iterSources(self):
		if self.get_source():
			yield self.get_source()
		if not os.path.isdir(self.rD.get_resdir()):
			raise Error("Resource directory %s does not exist or is"
				" not a directory."%self.rD.get_resdir())
		if self.get_sourcePat():
			for path, dirs, files in os.walk(self.rD.get_resdir()):
				for fName in glob.glob(os.path.join(path, self.get_sourcePat())):
					yield fName


def parseFromTable(tableDef, inputData, rd=None):
	"""returns an InternalDataSet generated from letting tableDef parse
	from inputData's primary table.
	"""
	if rd is None:
		rd = ResourceDescriptor()
		rd.set_resdir("NULL")
	dataDesc = datadef.DataTransformer(rd, initvals={
		"id": "invalid",
		"Grammar": tablegrammar.TableGrammar(),
		"Semantics": Semantics(initvals={
			"recordDefs": [tableDef]})})
	return InternalDataSet(dataDesc, table.Table, inputData)
