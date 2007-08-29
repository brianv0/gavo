"""
This module contains code for reading raw resources and their descriptors.
"""

import os
import re
import glob
import traceback
import copy
from xml.sax import make_parser
from xml.sax.handler import EntityResolver

import gavo
from gavo import utils
from gavo import record
from gavo import coords
from gavo import logger
from gavo import interfaces
from gavo import datadef
from gavo import config
from gavo import parsing
from gavo.web import service
from gavo.parsing import resource
from gavo.parsing import macros
from gavo.parsing import processors
from gavo.parsing import conditions
from gavo.parsing import typeconversion
from gavo.parsing import parsehelpers
from gavo.parsing.grammar import Grammar
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


class Semantics(record.Record):
	"""is a specification for the semantics of nonterminals defined
	by the grammar.

	Basically, we have dataItems (which are global for the data source),
	and a recordDef (which defines what each record should look like).
	"""
	def __init__(self):
		record.Record.__init__(self, {
			"recordDefs": record.ListField,
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
	def __init__(self, sourceFile, grammar, dataSet, literalParser):
		if isinstance(sourceFile, basestring):
			self.sourceName = sourceFile
			self.sourceFile = open(self.sourceName)
		else:  # we assume it's a file
			self.sourceFile = sourceFile
			self.sourceName = "<anonymous>"
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
# XXX TODO retrofit the max rows mechanism (keep it in grammar, I guess)
#		if self.maxRows and self.rowsProcessed>=self.maxRows:
#			raise gavo.StopOperation("Limit of %d rows reached"%self.maxRows)
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
		preVal = None
		if field.get_source()!=None:
			preVal = rowdict.get(field.get_source(), None)
		if preVal==field.get_nullvalue():
			preVal = None
		if preVal==None:
			preVal = self.atExpand(field.get_default(), rowdict)
		return self.literalParser.makePythonVal(preVal, 
			field.get_dbtype(), field.get_literalForm())

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
			if parsing.verbose:
				traceback.print_exc()
			raise Error("Cannot convert row %s, field %s probably doesn't match its"
				" type %s (root cause: %s)"%(str(rowdict), field.get_dest(), 
					field.get_dbtype(), msg))
		self._checkRecord(recordDef, record)
		return record
	
	def _checkRecord(self, recordDef, record):
		"""raises some kind of exception there is something wrong the record.
		"""
		recordDef._validate(record)
		if recordDef.get_constraints():
			if not recordDef.get_constraints().check(rowdict, record):
				raise gavo.InfoException("Record %s doesn't satisfy constraints,"
					" skipping."%record)

	def atExpand(self, val, rowdict):
		return parsehelpers.atExpand(val, rowdict, self.fieldComputer)

	def parse(self):
		self.grammar.parse(self)


class DataDescriptor(datadef.DataTransformer):
	"""is a DataTransformer for reading data from files.
	"""
	def __init__(self, parentResource, **initvals):
		datadef.DataTransformer.__init__(self, parentResource, 
			additionalFields = {
				"source": None, # resdir-relative filename of source
												# for single-file sources
				"sourcePat": None, # resdir-relative shell pattern of sources for
													 # one-row-per-file sources
				"encoding": "ascii", # of the source files
				"constraints": None, # ignored, present for RecordDef interface
			},
			initvals=initvals)

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

	def iterParseContexts(self, dataSet):
		literalParser = typeconversion.LiteralParser(self.get_encoding())
		for src in self.iterSources():
			yield ParseContext(src, self.get_Grammar(),
				dataSet, literalParser)

	def _validate(self, record):
		"""checks that the docRec record satisfies the constraints given
		by self.items.

		This method reflects that DataDescriptors are RecordDefs for
		the toplevel productions.
		"""
		for field in self.get_items():
			if not field.get_optional() and record.get(field.get_dest())==None:
				raise resource.ValidationError(
					"%s is None but non-optional"%field.get_dest())



class ResourceDescriptor(record.Record):
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


class RdParser(utils.NodeBuilder):
	def __init__(self):
		utils.NodeBuilder.__init__(self)
		self.rd = ResourceDescriptor()

	def handleError(self, exc_info):
		if parsing.verbose:
			traceback.print_exception(*exc_info)
		utils.NodeBuilder.handleError(self, exc_info)

	def _getDDById(self, id):
		"""returns the data descriptor with id.

		If there's a : in id, the stuff in front of the colon is
		an inputs-relative path to another resource descriptor,
		and the id then refers to one of its data descriptors.
		"""
		if ":" in id:
			rdPath, id = id.split(":", 1)
			rd = getRd(os.path.join(config.get("inputsDir"), rdPath))
		else:
			rd = self.rd
		return rd.getDataById(id)

	def _processChildren(self, parent, name, childMap, children):
		"""adds children to parent.

		Parent is some class (usually a record.Record instance),
		childMap maps child names to methods to call the children with,
		and children is a sequence as passed to the _make_xxx methods.

		The function returns parent for convenience.
		"""
		for childName, val in children:
			try:
				childMap[childName](val)
			except KeyError:
				raise Error("%s elements may not have %s children"%(
					name, childName))
		return parent

	def _make_ResourceDescriptor(self, name, attrs, children):
		self.rd.set_resdir(attrs["srcdir"])
		self._processChildren(self.rd, name, {
			"DataProcessor": self.rd.addto_processors,
			"recreateAfter": self.rd.addto_dependents,
			"script": self.rd.addto_scripts,
			"schema": self.rd.set_schema,
			"Data": lambda val:0,      # these register themselves
			"Adapter": lambda val: 0,  # these register themselves
			"Service": lambda val: 0,  # these register themselves
		}, children)
		# XXX todo: coordinate systems
		return self.rd

	def _make_Data(self, name, attrs, children):
		if attrs.has_key("extends"):
			dd = self._getDDById(attrs["extends"]).copy()
		else:
			dd = DataDescriptor(self.rd)
		dd.set_source(attrs.get("source"))
		dd.set_sourcePat(attrs.get("sourcePat"))
		dd.set_encoding(attrs.get("encoding", "ascii"))
		dd.set_id(attrs.get("id"))
		self.rd.addto_dataSrcs(dd)
		return self._processChildren(dd, name, {
			"Field": dd.addto_items,
			"Semantics": dd.set_Semantics,
			"Macro": dd.addto_macros,
			"Grammar": dd.set_Grammar,
		}, children)
	
	def _makeGrammar(self, grammarClass, attrs, children):
		"""internal base method for all grammar producing elements.
		"""
		grammar = grammarClass()
		grammar.setExtensionFlag(attrs.get("keep", "False"))
		if attrs.has_key("docIsRow"):
			grammar.set_docIsRow(attrs["docIsRow"])
		return self._processChildren(grammar, grammarClass.__name__, {
			"Macro": grammar.addto_macros,
		}, children)
	
	def _make_CFGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._makeGrammar(CFGrammar, attrs, children))
	
	def _make_REGrammar(self, name, attrs, children):
		grammar = self._makeGrammar(REGrammar, attrs, children)
		grammar.set_numericGroups(attrs.get("numericGroups", "False"))
		return utils.NamedNodes("Grammar",
			self._processChildren(grammar, name, {
				"rules": grammar.set_rules,
				"documentProduction": grammar.set_documentProduction,
				"tabularDataProduction": grammar.set_documentProduction,
				"rowProduction": grammar.set_rowProduction,
				"tokenizer": grammar.set_tokenizer,
			}, children))

	def _make_FitsGrammar(self, name, attrs, children):
		grammar = self._makeGrammar(FitsGrammar, attrs, children)
		grammar.set_qnd(attrs.get("qnd", "False"))
		return utils.NamedNode("Grammar", grammar)

	def _make_ColumnGrammar(self, name, attrs, children):
		grammar = self._makeGrammar(ColumnGrammar, attrs, children)
		grammar.set_topIgnoredLines(attrs.get("topIgnoredLines", 0))
		grammar.set_booster(attrs.get("booster"))
		return utils.NamedNode("Grammar", grammar)

	def _make_NullGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._makeGrammar(NullGrammar, attrs, children))

	def _make_KeyValueGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._makeGrammar(KeyValueGrammar, attrs, children))
	
	def _make_Semantics(self, name, attrs, children):
		semantics = Semantics()
		semantics.setExtensionFlag(attrs.get("keep", "False"))
		return self._processChildren(semantics, name, {
			"Record": semantics.addto_recordDefs,
		}, children)
	
	def _make_Record(self, name, attrs, children):
		recDef = resource.RecordDef()
		recDef.setExtensionFlag(attrs.get("keep", "False"))
		recDef.set_table(attrs["table"])
		recDef.set_create(attrs.get("create", "True"))
		if name=="SharedRecord":
			recDef.set_shared(True)
		
		interfaceNodes, children = self.filterChildren(children, "implements")
		for _, (interface, args) in interfaceNodes:
			children.extend(interface.getNodes(recDef, **args))
			for nodeDesc in interface.getDelayedNodes(
					recDef, **args):
				self.registerDelayedChild(*nodeDesc)

		record = self._processChildren(recDef, name, {
			"Field": recDef.addto_items,
			"constraints": recDef.set_constraints,
			"owningCondition": recDef.set_owningCondition,
		}, children)

		return utils.NamedNode("Record", record)
	
	_make_SharedRecord = _make_Record

	def _make_implements(self, name, attrs, children):
		args = dict([(key, val) for key, val in attrs.items()])
		interfaceName = args["name"]
		del args["name"]
		return interfaces.getInterface(interfaceName), args

	def _make_owningCondition(self, name, attrs, children):
		return attrs["colName"], attrs["value"]

	def _make_Field(self, name, attrs, children):
		field = datadef.DataField()
		for key, val in attrs.items():
			field.set(key, val)
		return self._processChildren(field, name, {
			"longdescr": field.set_longdescription,
		}, children)
	
	def _make_longdescr(self, name, attrs, children):
		return attrs.get("type", "text/plain"), self.getContent(children)
	
	def _make_Macro(self, name, attrs, children):
		initArgs = dict([(str(key), value) 
			for key, value in attrs.items() if key!="name"])
		macro = macros.getMacro(attrs["name"])(**initArgs)
		return self._processChildren(macro, name, {
			"arg": macro.addArgument,
		}, children)

	def _make_macrodef(self, name, attrs, children):
		code = children[0][1]
		return utils.NamedNode("Macro", 
			macros.compileMacro(attrs["name"], code))

	def _make_RowProcessor(self, name, attrs, children):
		initArgs = dict([(str(key), value) 
			for key, value in attrs.items() if key!="name"])
		proc = processors.getProcessor(attrs["name"])(**initArgs)
		return self._processChildren(macro, name, {
			"arg": proc.addArgument,
		}, children)

	def _make_arg(self, name, attrs, children):
		return attrs["name"], attrs.get("source"), attrs.get("value")

	def _make_tokenizer(self, name, attrs, children):
		return self.getContent(children), attrs["type"]

	scriptTypes = set(["postCreation"])

	def _make_script(self, name, attrs, children):
		assert attrs["type"] in self.scriptTypes # Just a quick hack
		return (attrs["type"], attrs.get("name", "<anonymous>"),
			self.getContent(children))

	def _make_constraints(self, name, attrs, children):
		constraints = conditions.Constraints()
		return self._processChildren(constraints, name, {
			"constraint": constraints.addConstraint,
		}, children)
	
	def _make_constraint(self, name, attrs, children):
		constraint = conditions.Constraint(attrs.get("name", "<anonymous>"))
		return self._processChildren(constraint, name, {
			"condition": constraint.addCondition,
		}, children)
	
	def _make_condition(self, name, attrs, children):
		return conditions.makeCondition(attrs)
	
	def _make_recreateAfter(self, name, attrs, children):
		return attrs["project"]

	def _make_coosys(self, name, attrs, children):
		self.rd.get_systems().defineSystem(children[0][1].strip(), 
			attrs.get("epoch"), attrs.get("system"))

	def _make_Adapter(self, name, attrs, children):
		adapter = service.Adapter(name=attrs["name"], id=attrs["id"])
		self.rd.register_adapter(adapter.get_id(), adapter)
		return self._processChildren(adapter, name, {
			"Field": adapter.addto_items,
			"Semantics": adapter.set_Semantics,
			"Macro": adapter.addto_macros,
			"Grammar": adapter.set_Grammar,
		}, children)

	def _makeService(self, name, attrs, children):
		service = service.Service(id=attrs["id"])
		self.rd.register_service(service.get_id(), service)
		return self._processChildren(service, name, {
			"inputFilter": service.addto_inputFilters,
			"core": serive.set_core,
			"outputTable": lambda val: 
				service.register_output(val[0], (val[1], val[2])),
		}, children)

	def _make_inputFilter(self, name, attrs, children):
		return self.rd.get_adapter(attrs["idref"])
	
	def _make_outputTable(self, name, attrs, children):
		return (attrs["id"], self.rd.get_adapter(attrs["idref"]), 
			attrs["table"])

	def _make_core(self, name, attrs, children):
		return self._getDDById(attrs["idref"])

	def _makeTextNode(self, name, attrs, children):
		if len(children)!=1 or children[0][0]!=None:
			raise Error("%s nodes have text content only"%name)
		return children[0][1]

	_make_rules = \
	_make_documentProduction = \
	_make_rowProduction = \
	_make_tabularDataProduction = \
	_make_tokenSequence = \
	_make_schema = \
	_makeTextNode


class InputEntityResolver(EntityResolver):
	def resolveEntity(self, publicId, systemId):
		return open(os.path.join(config.get("parsing", "xmlFragmentPath"), 
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
		if parsing.verbose:
			traceback.print_exc()
		logger.error("Exception while parsing:", exc_info=True)
		utils.fatalError("Unexpected Exception while parsing Desriptor %s: %s."
			"  Please check input validity."%(srcPath, msg))
	return contentHandler.getResult()


def _test():
	import doctest, importparser
	doctest.testmod(importparser)


if __name__=="__main__":
	_test()
