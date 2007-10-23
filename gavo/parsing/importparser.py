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
from gavo import resourcecache
from gavo import table
from gavo.parsing import meta
from gavo.web import service
from gavo.web import standardcores
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
from gavo.parsing import tablegrammar
from gavo.parsing import contextgrammar


class Error(gavo.Error):
	pass


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


def makeAttDict(attrs):
	"""returns a dictionary suitable as keyword arguments from a sax attribute
	dictionary.
	"""
	return dict([(str(key), val) for key, val in attrs.items()])


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
			rd = getRd(rdPath)
		else:
			rd = self.rd
		return rd.getDataById(id)

	def _make_ResourceDescriptor(self, name, attrs, children):
		self.rd.set_resdir(attrs["srcdir"])
		self.rd.set_profile(attrs.get("profile"))
		self._processChildren(self.rd, name, {
			"DataProcessor": self.rd.addto_processors,
			"recreateAfter": self.rd.addto_dependents,
			"script": self.rd.addto_scripts,
			"schema": self.rd.set_schema,
			"Data": lambda val:0,      # these register themselves
			"Adapter": lambda val: 0,  # these register themselves
			"Service": lambda val: 0,  # these register themselves
			"meta": self.rd.addMeta,
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
		dd.set_computer(attrs.get("computer"))
		dd.set_encoding(attrs.get("encoding", "ascii"))
		dd.set_id(attrs.get("id"))
		self.rd.addto_dataSrcs(dd)
		return self._processChildren(dd, name, {
			"Field": dd.addto_items,
			"Semantics": dd.set_Semantics,
			"Macro": dd.addto_macros,
			"Grammar": dd.set_Grammar,
			"meta": dd.addMeta,
		}, children)
	
	def _fillGrammarNode(self, grammar, attrs, children, classHandlers):
		"""handles children and attributes common to all grammar classes.

		grammar is an instance of the desired grammar class.

		classHandlers is a dict of _processChildren-like handlers for the
		children of the concrete grammar.

		For convenience, the function returns the instance passed in.
		"""
		grammar.setExtensionFlag(attrs.get("keep", "False"))
		if attrs.has_key("docIsRow"):
			grammar.set_docIsRow(attrs["docIsRow"])
		handlers = {
			"Macro": grammar.addto_macros,
			"RowProcessor": grammar.addto_rowProcs,
		}
		handlers.update(classHandlers)
		return self._processChildren(grammar, grammar.__class__.__name__, 	
			handlers, children)
	
	def _make_CFGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._fillGrammarNode(CFGrammar(), attrs, children, {}))
	
	def _make_REGrammar(self, name, attrs, children):
		grammar = REGrammar()
		self._fillGrammarNode(grammar, attrs, children, {
				"rules": grammar.set_rules,
				"documentProduction": grammar.set_documentProduction,
				"tabularDataProduction": grammar.set_documentProduction,
				"rowProduction": grammar.set_rowProduction,
				"tokenizer": grammar.set_tokenizer,
			})
		grammar.set_numericGroups(attrs.get("numericGroups", "False"))
		return utils.NamedNode("Grammar", grammar)

	def _make_FitsGrammar(self, name, attrs, children):
		grammar = self._fillGrammarNode(FitsGrammar(), attrs, children, {})
		grammar.set_qnd(attrs.get("qnd", "False"))
		return utils.NamedNode("Grammar", grammar)

	def _make_ColumnGrammar(self, name, attrs, children):
		grammar = self._fillGrammarNode(ColumnGrammar(), attrs, children, {})
		grammar.set_topIgnoredLines(attrs.get("topIgnoredLines", 0))
		grammar.set_booster(attrs.get("booster"))
		return utils.NamedNode("Grammar", grammar)

	def _make_NullGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._fillGrammarNode(NullGrammar(), attrs, children, {}))

	def _make_KeyValueGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._fillGrammarNode(KeyValueGrammar(), attrs, children, {}))

	def _make_TableGrammar(self, name, attrs, children):
		return utils.NamedNode("Grammar",
			self._fillGrammarNode(tablegrammar.TableGrammar(), attrs, children, {}))

	def _make_inputKey(self, name, attrs, children):
		inputKey = contextgrammar.InputKey(makeAttDict(attrs))
		return self._processChildren(inputKey, name, {}, children)
	
	def _make_ContextGrammar(self, name, attrs, children):
		grammar = contextgrammar.ContextGrammar()
		return utils.NamedNode("Grammar",
			self._fillGrammarNode(grammar, attrs, children, {
				"inputKey": grammar.addto_inputKeys,
			}))

	def _make_Semantics(self, name, attrs, children):
		semantics = resource.Semantics()
		semantics.setExtensionFlag(attrs.get("keep", "False"))
		return self._processChildren(semantics, name, {
			"Record": semantics.addto_recordDefs,
		}, children)
	
	def _make_Record(self, name, attrs, children):
		recDef = resource.RecordDef()
		recDef.setExtensionFlag(attrs.get("keep", "False"))
		recDef.set_table(attrs["table"])
		recDef.set_onDisk(attrs.get("onDisk", "False"))
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
			"meta": recDef.addMeta,
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

	def _make_copyof(self, name, attrs, children):
		return utils.NamedNode(*self.getById(attrs["idref"]))

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
		return self._processChildren(proc, name, {
			"arg": proc.addArgument,
		}, children)

	def _collectArguments(self, children):
		"""returns a dictionary mapping names to values for all arg elements
		in children.
		"""
		res = {}
		for childName, node in children:
			if childName!="arg":
				continue
			name, src, val = node
			if src or val.startswith("@"):
				# XXX we should at least support @-expansions.
				raise Error("RdParser doesn't know what to do with computed"
					" arguments")
			res[str(name)] = val
		return res

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
		adapter = DataDescriptor(self.rd, id=attrs["id"])
		adapter.set_name(attrs["name"])
		self.rd.register_adapter(adapter.get_id(), adapter)
		return self._processChildren(adapter, name, {
			"Field": adapter.addto_items,
			"Semantics": adapter.set_Semantics,
			"Macro": adapter.addto_macros,
			"Grammar": adapter.set_Grammar,
			"meta": adapter.addMeta,
		}, children)

	def _make_Service(self, name, attrs, children):
		svc = service.Service(self.rd, {"id": attrs["id"]})
		self.rd.register_service(svc.get_id(), svc)
		return self._processChildren(svc, name, {
			"inputFilter": svc.set_inputFilter,
			"core": svc.set_core,
			"outputFilter": lambda val: 
				svc.register_output(val.get_id(), val),
			"meta": svc.addMeta,
		}, children)

	def _make_inputFilter(self, name, attrs, children):
		return self.rd.get_adapter(attrs["idref"])
	
	def _make_outputFilter(self, name, attrs, children):
		return self.rd.get_adapter(attrs["idref"])

	def _make_core(self, name, attrs, children):
		if attrs.has_key("builtin"):
			core = standardcores.getStandardCore(attrs["builtin"])(self.rd,
				**self._collectArguments(children))
		elif attrs.has_key("computer"):
			core = standardcores.ComputedCore(self._getDDById(attrs["computer"]))
		else:
			raise Error("Invalid core specification")
		return core
	
	def _make_meta(self, name, attrs, children):
		content = self._makeTextNode(name, attrs, children)
		res = makeAttDict(attrs)
		res["content"] = content
		return res

	def _makeTextNode(self, name, attrs, children):
		if len(children)==0:
			return ""
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
	srcPath = os.path.join(config.get("inputsDir"), srcPath)
	if not os.path.exists(srcPath):
		srcPath = srcPath+".vord"
	contentHandler = parserClass()
	parser = make_parser()
	parser.setContentHandler(contentHandler)
	parser.setEntityResolver(InputEntityResolver())
	try:
		parser.parse(open(srcPath))
	except IOError, msg:
		raise Error("Could not open descriptor %s (%s)."%(
			srcPath, msg))
	except Exception, msg:
		if parsing.verbose:
			traceback.print_exc()
		logger.error("Exception while parsing:", exc_info=True)
		utils.fatalError("Unexpected Exception while parsing Desriptor %s: %s."
			"  Please check input validity."%(srcPath, msg))
	return contentHandler.getResult()


resourcecache.makeCache("getRd", getRd)


def _test():
	import doctest, importparser
	doctest.testmod(importparser)


if __name__=="__main__":
#	_test()
	parsing.verbose = True
	getRd("apfs/res/apfs_new.vord")
