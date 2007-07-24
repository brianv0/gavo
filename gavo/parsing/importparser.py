"""
This module contains code for reading raw resources and their descriptors.
"""

import os
import re
import weakref
import glob
import time
import traceback
import copy
from xml.sax import make_parser
from xml.sax.handler import EntityResolver

import gavo
from gavo import utils
from gavo import coords
from gavo import logger
from gavo import interfaces
from gavo import datadef
import gavo.parsing
from gavo.parsing import resource
from gavo.parsing import macros
from gavo.parsing import processors
from gavo.parsing import resproc
from gavo.parsing import conditions
from gavo.parsing import typeconversion
from gavo.parsing import parsehelpers
from gavo.parsing.cfgrammar import CFGrammar
from gavo.parsing.regrammar import REGrammar
from gavo.parsing.columngrammar import ColumnGrammar
from gavo.parsing.kvgrammar import KeyValueGrammar
from gavo.parsing.nullgrammar import NullGrammar
from gavo.parsing.fitsgrammar import FitsGrammar


class Error(gavo.Error):
	pass


class ResourceDescriptorError(Error):
	pass


class FieldComputer:
	"""is a container for various functions computing field values.

	The idea is that you can say ...source="@bla" in your field
	definiton and RecordBuilder.strToVal will call bla to obtain a literal
	for the field value, passing it the entire row dictionary as
	produced by the parser.

	The FieldComputer has a (weak) reference to the data descriptor
	and thus to the full grammar and the full semantics, so you
	should be able to compute quite a wide range of values.  However:
	If there's an alternative, steer clear of computed fields...

	To define new field computing functions, just add a method named
	_fc_<your name> receiving the row dictionary in this class.
	"""
	def __init__(self, dataDescriptor):
		self.dataDescriptor = weakref.proxy(dataDescriptor)
		self.curFile = None

	def compute(self, cfname, rows, *args):
		return getattr(self, "_fc_"+cfname)(rows, *args)
	
	def _fc_srcstem(self, rows):
		"""returns the stem of the source file currently parsed.
		
		Example: if you're currently parsing /tmp/foo.bar, the stem is foo.
		"""
		return os.path.splitext(
			os.path.basename(self.dataDescriptor.get_Grammar(
				).getCurFileName()))[0]

	def _fc_today(self, rows):
		"""returns the current date.
		"""
		return time.strftime("%Y-%m-%d")

	def _fc_lastSourceElements(self, rows, numElements):
		"""returns the last numElements items of the current source's path.
		"""
		newPath = []
		fullPath = self.dataDescriptor.get_Grammar().getCurFileName()
		for i in range(int(numElements)):
			fullPath, part = os.path.split(fullPath)
			newPath.append(part)
		newPath.reverse()
		return os.path.join(*newPath)

	def _getRelativePath(self, fullPath, rootPath):
		"""returns rest if fullPath has the form rootPath/rest and raises an
		exception otherwise.
		"""
		if not fullPath.startswith(rootPath):
			raise Error("Full path %s does not start with resource root %s"%
				(fullPath, rootPath))
		return fullPath[len(rootPath):].lstrip("/")

	def _fc_rootlessPath(self, rows):
		"""returns the the current source's path with the resource descriptor's
		root removed.
		"""
		fullPath = self.dataDescriptor.get_Grammar().getCurFileName()
		rootPath = self.dataDescriptor.getResource().get_resdir()
		return self._getRelativePath(fullPath, rootPath)

	def _fc_inputRelativePath(self, rows):
		"""returns the current source's path relative to gavo.inputsDir
		(or raises an error if it's not from there).
		"""
		fullPath = self.dataDescriptor.get_Grammar().getCurFileName()
		rootPath = gavo.inputsDir
		return self._getRelativePath(fullPath, rootPath)

	def _fc_inputSize(self, rows):
		"""returns the size of the current source.
		"""
		fullPath = self.dataDescriptor.get_Grammar().getCurFileName()
		return os.path.getsize(fullPath)

	def getDocs(self, underliner):
		docItems = []
		for name in dir(self):
			if name.startswith("_fc_"):
				docItems.append((name[4:], getattr(self, name).__doc__))
		return utils.formatDocs(docItems, underliner)


class RecordBuilder:
	"""is a class that knows how to translate raw terminals from
	a grammar (rowdicts) to records of python values.

	It is constructed with a resource.RecordDef instance, a 
	callable that receives the finished records and adds them to
	the target table, a FieldComputer instance and a 
	typeconversion.LiteralParser instance.

	For clarity: Grammars deliver dictionaries mapping keys (the
	preterminals) to values (which are strings), the rowdicts.  
	These have to be processed in multiple ways:

	* certain values may need to be computed using meta information
	  not available from the source itself (e.g., dates, paths).
	  Field computers are used for this.
	* string literals have to be converted to python values.  This
	  is done by the literal parser.
	
	After these manipulations, we have another dictionary mapping
	the dests of DataFields to python values.  This is what we call
	a record that's ready for ingestion into a db table or a VOTable.
	"""
	def __init__(self, recordDef, adderCallback, fieldComputer, 
			literalParser, dataDef, maxRows=None):
		self.recordDef, self.adderCallback = recordDef, adderCallback
		self.fieldComputer, self.literalParser = fieldComputer, literalParser
		self.maxRows = maxRows
		self.rowsProcessed = 0
		self.dataDef = dataDef
		self.docRec = {}

	def processRowdict(self, rowdict):
		"""is called by the grammar when a table line has been parsed.

		This method arranges for the record to be built, validates the
		finished record (i.e., makes sure all the non-optional fields are
		in place), checks constraints that may be defined and finally
		ships out the record.
		"""
		if self.maxRows and self.rowsProcessed>=self.maxRows:
			raise gavo.StopOperation("Limit of %d rows reached"%self.maxRows)
		record = self._buildRecord(rowdict)
		self.recordDef._validate(record)
		if self.recordDef.get_constraints():
			if not self.recordDef.get_constraints().check(rowdict, record):
				raise gavo.InfoException("Record %s doesn't satisfy constraints,"
					" skipping."%record)
		self.adderCallback(record)
		self.rowsProcessed += 1

	def processDocdict(self, docdict):
		self.docRec = {}
		for macro in self.dataDef.get_macros():
			macro(docdict)
		for field in self.dataDef.get_items():
			self.docRec[field.get_dest().encode("ascii")] = self.strToVal(
				field, docdict)

	def getDocRec(self):
		return self.docRec

	def strToVal(self, field, rowdict):
		"""returns a python value appropriate for field's type
		from the values in rowdict.
		"""
		preVal = None
		if field.get_source()!=None:
			preVal = rowdict.get(field.get_source(), None)
			if preVal==None and self.docRec:
				preVal = self.docRec.get(field.get_source(), None)
		if preVal==field.get_nullvalue():
			preVal = None
		if preVal==None:
			preVal = parsehelpers.atExpand(field.get_default(), rowdict,
				self.fieldComputer)
		return self.literalParser.makePythonVal(preVal, 
			field.get_dbtype(), field.get_literalForm())

	def _buildRecord(self, rowdict):
		"""returns a record built from rowdict and recordDef's item definition.

		The rowdict is changed by this method if macros are defined.  If
		macros change existing fields (which they shouldn't), this method
		is not idempotent.
		"""
		record = {}
		try:
			for field in self.recordDef.get_items():
				record[field.get_dest()] = self.strToVal(field, rowdict)
		except Exception, msg:
			raise Error("Cannot convert row %s, field %s probably doesn't match its"
				" type %s (root cause: %s)"%(str(rowdict), field.get_dest(), 
					field.get_dbtype(), msg))
		return record


class Semantics(utils.Record):
	"""is a specification for the semantics of nonterminals defined
	by the grammar.

	Basically, we have dataItems (which are global for the data source),
	and a recordDef (which defines what each record should look like).
	"""
	def __init__(self):
		utils.Record.__init__(self, {
			"recordDefs": utils.ListField,
		})

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


class DataDescriptor(utils.Record):
	"""is a container for all information necessary
	to parse one source data file.
	"""
	def __init__(self, parentResource, **initvals):
		utils.Record.__init__(self, {
			"source": None, # resdir-relative filename of source
			                # for single-file sources
			"sourcePat": None, # resdir-relative shell pattern of sources for
			                   # one-row-per-file sources
			"encoding": "iso-8859-1",
			"Grammar": utils.RequiredField,
			"Semantics": utils.RequiredField,
			"id": utils.RequiredField,        # internal id of the data set.
			"FieldComputer": utils.ComputedField,  # for @-expansion
			"items": utils.ListField,
			"macros": utils.ListField,
		}, initvals)
		self.resource = parentResource
		self.fieldComputer = FieldComputer(self)

	def __repr__(self):
		return "<DataDescriptor id=%s>"%self.get_id()

	def copy(self):
		"""returns a semi-deep copy of self.

		semi-deep means that the local lists are copied over, but
		mutables in dependent data structure (in particular grammar and
		semantics) are not.  We may want to change this when we get an
		idea of how to notate the intent of changing them in the resource
		descriptor.

		Until that time, changing anything in Grammar or Semantics will
		affect the original owner.
		"""
		nd = DataDescriptor(self.resource, 
			source=self.get_source(),
			sourcePat=self.get_sourcePat(),
			encoding=self.get_encoding())
		for item in self.get_items(): nd.addto_items(item)
		for macro in self.get_macros(): nd.addto_macros(macro)
		try:
			nd.set_Grammar(self.get_Grammar())
		except KeyError:
			pass
		try:
			nd.set_Semantics(self.get_Semantics())
		except KeyError:
			pass
		return nd

	def get_FieldComputer(self):
		return self.fieldComputer

	def get_source(self):
		if self.dataStore["source"]:
			return os.path.join(self.resource.get_resdir(), 
				self.dataStore["source"])
	
	def iterSources(self):
		if self.get_source():
			yield self.get_source()
		if not os.path.isdir(self.resource.get_resdir()):
			raise Error("Resource directory %s does not exist or is"
				" not a directory."%self.resource.get_resdir())
		if self.get_sourcePat():
			for path, dirs, files in os.walk(self.resource.get_resdir()):
				for fName in glob.glob(os.path.join(path, self.get_sourcePat())):
					yield fName
	
	def getResource(self):
		return self.resource

	def setHandlers(self, table, maxRows=None):
		"""builds a RecordBuilder that feeds into table and connects
		it with the grammar.

		The function returns the record builder instance used to 
		make the records from the rowdicts.
		"""
		rb = RecordBuilder(
			table.getRecordDef(),
			table.addData,
			self.get_FieldComputer(),
			typeconversion.LiteralParser(self.get_encoding()),
			self,
			maxRows=maxRows)
		self.get_Grammar().addDocumentHandler(rb.processDocdict)
		self.get_Grammar().addRowHandler(rb.processRowdict)
		return rb

	def validate(self, record):
		"""checks that record complies with all known constraints on
		the data set.

		The function raises a resource.ValidationError with an appropriate message
		if not.

		TODO: Refactor, using common stuff from RecordDef and DataSet (macros,
		validate &c) -- no, crap.  Documents shouldn't be validated, only
		rows should, since documents never go into the db.
		"""
		for field in self.get_items():
			if not field.get_optional() and record.get(field.get_dest())==None:
				raise resource.ValidationError(
					"%s is None but non-optional"%field.get_dest())


class ResourceDescriptor(utils.Record):
	"""is a container for all information necessary to import a resource into
	a VO data pool.
	"""
	def __init__(self):
		utils.Record.__init__(self, {
			"resdir": utils.RequiredField, # base directory for source files
			"dataSrcs": utils.ListField,   # list of data sources
			"processors": utils.ListField, # list of resource processors
			"dependents": utils.ListField, # list of projects to recreate
			"scripts": utils.ListField,    # pairs of (script type, script)
			"schema": None,    # Name of schema for that resource, defaults
			                   # to basename(resdir)
			"systems": coords.CooSysRegistry(),
		})
		
	def set_resdir(self, relPath):
		"""sets resource directory, qualifing it and making sure
		there's no trailing slash.

		We don't want that trailing slash because some names
		fall back to basename(resdir).
		"""
		self.dataStore["resdir"] = os.path.join(gavo.inputsDir, 
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

def catchErrors(fun):
	def wrappedFun(self, *args, **kwargs):
		try:
			return fun(self, *args, **kwargs)
		except Exception, msg:
			if gavo.parsing.verbose:
				traceback.print_exc()
			raise gavo.Error("Parse error in resource descriptor at"
				" %d:%d (%s)"%(self.locator.getLineNumber(), 
					self.locator.getColumnNumber(), msg))
	return wrappedFun


class RdParser(utils.StartEndHandler):
	def __init__(self):
		utils.StartEndHandler.__init__(self)
		self.locator = None
		self.dataSrcStack = []
		self.callableStack = []
		self.fieldContainerStack = []
		self.macroContainerStack = []

	def _keepInherited(self, attrs):
		"""returns true if attrs has a field keep with a true boolean literal.

		This is used by all mutable elements that can be inherited in
		a data descriptor to decide if a new element is to be instanciated
		or if a copy should be inserted.
		"""
		return utils.parseBooleanLiteral(attrs.get("keep", "False"))

	def setDocumentLocator(self, locator):
		self.locator = locator

	def _start_ResourceDescriptor(self, name, attrs):
		self.rd = ResourceDescriptor()
		self.rd.set_resdir(attrs["srcdir"])
	
	def _end_schema(self, name, attrs, content):
		self.rd.set_schema(content)

	def _getDDById(self, id):
		"""returns the data descriptor that has id.

		If there's a : in id, the stuff in front of the colon is
		an inputs-relative path to another resource descriptor,
		and the id then refers to one of its data descriptors.
		"""
		if ":" in id:
			rdPath, id = id.split(":", 1)
			rd = getRd(os.path.join(gavo.inputsDir, rdPath))
		else:
			rd = self.rd
		return rd.getDataById(id)

	def _start_Data(self, name, attrs):
		if attrs.has_key("extends"):
			self.curDD = self._getDDById(attrs["extends"]).copy()
		else:
			self.curDD = DataDescriptor(self.rd)
		self.curDD.set_source(attrs.get("source"))
		self.curDD.set_sourcePat(attrs.get("sourcePat"))
		self.curDD.set_id(attrs.get("id"))
		self.rd.addto_dataSrcs(self.curDD)
		self.dataSrcStack.append(self.curDD)
		self.fieldContainerStack.append(self.curDD)
		self.macroContainerStack.append(self.curDD)

	def _end_Data(self, name, attrs, content):
		self.dataSrcStack.pop()
		self.fieldContainerStack.pop()
		self.macroContainerStack.pop()

	@catchErrors
	def _startGrammar(self, grammarClass, attrs):
		if self._keepInherited(attrs):
			self.curGrammar = self.curDD.get_Grammar().copy()
		else:
			self.curGrammar = grammarClass()
			if attrs.has_key("docIsRow"):
				self.curGrammar.set_docIsRow(attrs["docIsRow"])
		self.dataSrcStack[-1].set_Grammar(self.curGrammar)
		self.macroContainerStack.append(self.curGrammar)

	def _start_CFGrammar(self, name, attrs):
		self._startGrammar(CFGrammar, attrs)

	def _start_REGrammar(self, name, attrs):
		self._startGrammar(REGrammar, attrs)
		self.curGrammar.set_numericGroups(attrs.get("numericGroups", "False"))

	def _start_ColumnGrammar(self, name, attrs):
		self._startGrammar(ColumnGrammar, attrs)
		self.curGrammar.set_topIgnoredLines(attrs.get(
			"topIgnoredLines", 0))
		self.curGrammar.set_booster(attrs.get(
			"booster"))

	def _start_KeyValueGrammar(self, name, attrs):
		self._startGrammar(KeyValueGrammar, attrs)

	def _start_FitsGrammar(self, name, attrs):
		self._startGrammar(FitsGrammar, attrs)
		self.curGrammar.set_qnd(attrs.get("qnd", "False"))

	def _start_NullGrammar(self, name, attrs):
		self._startGrammar(NullGrammar, attrs)

	def _endGrammar(self, name, attrs, content):
		self.macroContainerStack.pop()
	
	_end_CFGrammar = _end_REGrammar = _end_ColumnGrammar = \
		_end_KeyValueGrammar = _end_FitsGrammar = _end_NullGrammar = _endGrammar

	@catchErrors
	def _start_Semantics(self, name, attrs):
		if self._keepInherited(attrs):
			self.curSemantics = self.curDD.get_Semantics().copy()
		else:
			self.curSemantics = Semantics()
		self.dataSrcStack[-1].set_Semantics(self.curSemantics)

	@catchErrors
	def _start_Record(self, name, attrs):
		if self._keepInherited(attrs):
			self.curRecordDef = self.curSemantics.get_recordDefs()[0].copy()
			self.curSemantics.clear_recordDefs()
		else:
			self.curRecordDef = resource.RecordDef()
		self.curSemantics.addto_recordDefs(self.curRecordDef)
		self.curRecordDef.set_table(attrs["table"])
		self.curRecordDef.set_create(attrs.get("create", "True"))
		if name=="SharedRecord":
			self.curRecordDef.set_shared(True)
		self.fieldContainerStack.append(self.curRecordDef)

	_start_SharedRecord = _start_Record

	def _end_Record(self, name, attrs, content):
		self.fieldContainerStack.pop()

	def _start_owningCondition(self, name, attrs):
		self.curRecordDef.set_owningCondition((attrs["colName"], attrs["value"]))

	@catchErrors
	def _start_Field(self, name, attrs):
		f = datadef.DataField()
		for key, val in attrs.items():
			f.set(key, val)
		self.fieldContainerStack[-1].addto_items(f)
		self.currentField = f

	def _end_longdescr(self, name, attrs, content):
		self.currentField.set_longdescription(content)
		self.currentField.set_longmime(attrs.get("type", "text/plain"))

	@catchErrors
	def _start_Macro(self, name, attrs):
		initArgs = dict([(str(key), value) 
				for key, value in attrs.items()
			if key!="name"])
		mac = macros.getMacro(attrs["name"])(self.curDD.get_FieldComputer(),
			**initArgs)
		self.callableStack.append(mac)
		self.macroContainerStack[-1].addto_macros(mac)

	def _end_Macro(self, name, attrs, content):
		mac = self.callableStack.pop()

	@catchErrors
	def _end_macrodef(self, name, attrs, code):
		self.curGrammar.addto_macros(
			macros.compileMacro(attrs["name"], code, self.curDD.get_FieldComputer()))

	@catchErrors
	def _start_RowProcessor(self, name, attrs):
		proc = processors.getProcessor(attrs["name"])(
			self.curDD.get_FieldComputer())
		self.callableStack.append(proc)
		self.curGrammar.addto_rowProcs(proc)

	def _end_RowProcessor(self, name, attrs, content):
		self.callableStack.pop()

	@catchErrors
	def _start_ResourceProcessor(self, name, attrs):
		proc = resproc.getResproc(attrs["name"])()
		self.callableStack.append(proc)
		self.rd.addto_processors(proc)
	
	def _end_ResourceProcessor(self, name, attrs, content):
		self.callableStack.pop()

	def _end_arg(self, name, attrs, content):
		self.callableStack[-1].addArgument(attrs["name"], attrs.get("source"),
			attrs.get("value"))
	
	def _end_rules(self, name, attrs, contents):
		self.curGrammar.set_rules(contents)
	
	def _end_documentProduction(self, name, attrs, content):
		self.curGrammar.set_documentProduction(content.strip())

	def _end_rowProduction(self, name, attrs, content):
		self.curGrammar.set_rowProduction(content.strip())

	def _end_tabularDataProduction(self, name, attrs, content):
		self.curGrammar.set_tabularDataProduction(content.strip())

	def _end_tokenizer(self, name, attrs, content):
		self.curGrammar.set_tokenizer(content.strip(), attrs["type"])
	
	def _end_tokenSequence(self, name, attrs, content):
		self.curGrammar.set_tokenSequence(content.strip())

	def _end_coosys(self, name, attrs, content):
		self.rd.get_systems().defineSystem(content, attrs.get("epoch"),
			attrs.get("system"))

	scriptTypes = set(["postCreation"])

	def _end_script(self, name, attrs, content):
		assert attrs["type"] in self.scriptTypes # Just a quick hack
		self.rd.addto_scripts((attrs["type"], attrs.get("name", "<anonymous>"),
			content.strip()))

	def _start_implements(self, name, attrs):
		args = dict([(key, val) for key, val in attrs.items()])
		interfaceName = args["name"]
		del args["name"]
		interfaces.getInterface(interfaceName).changeRd(self, **args)

	def _start_constraints(self, name, attrs):
		self.curConstraints = conditions.Constraints()
		self.curRecordDef.set_constraints(self.curConstraints)

	def _start_constraint(self, name, attrs):
		self.curConstraint = conditions.Constraint(attrs["name"])
		self.curConstraints.addConstraint(self.curConstraint)

	def _start_condition(self, name, attrs):
		self.curConstraint.addCondition(
			conditions.makeCondition(attrs))

	def _start_recreateAfter(self, name, attrs):
		self.rd.addto_dependents(attrs["project"])

	def getResult(self):
		return self.rd


class InputEntityResolver(EntityResolver):
	def resolveEntity(self, publicId, systemId):
		return open(os.path.join(gavo.parsing.xmlFragmentPath, 
			systemId+".template"))


def getRd(srcPath, parserClass=RdParser):
	"""returns a ResourceDescriptor from the source in srcPath
	"""
	if not os.path.exists(srcPath):
		srcPath = srcPath+".vord"
	contentHandler = parserClass()
	parser = make_parser()
	parser.setContentHandler(contentHandler)
	parser.setEntityResolver(InputEntityResolver())
	try:
		parser.parse(open(srcPath))
	except IOError, msg:
		utils.fatalError("Could not open descriptor %s (%s)."%(
			srcPath, msg))
	except Exception, msg:
		if gavo.parsing.verbose:
			traceback.print_exc()
		logger.error("Exception while parsing:", exc_info=True)
		utils.fatalError("Unexpected Exception while parsing Desriptor %s: %s."
			"  Please check input validity."%(srcPath, msg))
	return contentHandler.getResult()


def _test():
	import doctest, importparser
	doctest.testmod(importparser)


if __name__=="__main__":
	import sys
	if len(sys.argv)>1 and sys.argv[1]=="docs":
		underliner = "."
		if len(sys.argv)>2:
			underliner = sys.argv[2]
		print FieldComputer(DataDescriptor(ResourceDescriptor())
			).getDocs(underliner)
	else:
		_test()
