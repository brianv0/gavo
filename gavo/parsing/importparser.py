"""
This module contains code for reading raw resources and their descriptors.
"""

import pkg_resources
import os
import re
import time
import traceback
from xml.sax import make_parser
from xml.sax.handler import EntityResolver

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import interfaces
from gavo import logger
from gavo import meta
from gavo import nodebuilder
from gavo import parsing
from gavo import record
from gavo import resourcecache
from gavo import sqlsupport
from gavo import utils
from gavo.parsing.cfgrammar import CFGrammar
from gavo.parsing.columngrammar import ColumnGrammar
from gavo.parsing.customgrammar import CustomGrammar
from gavo.parsing.fitsgrammar import FitsGrammar
from gavo.parsing.grammar import Grammar
from gavo.parsing.simpleregrammar import SimpleREGrammar
from gavo.parsing.votablegrammar import VOTableGrammar
from gavo.parsing import conditions
from gavo.parsing import contextgrammar
from gavo.parsing import elgen
from gavo.parsing import macros
from gavo.parsing import parsehelpers
from gavo.parsing import processors
from gavo.parsing import resource
from gavo.parsing import tablegrammar
from gavo.parsing import typeconversion
from gavo.parsing.dictlistgrammar import DictlistGrammar
from gavo.parsing.directgrammar import DirectGrammar
from gavo.parsing.kvgrammar import KeyValueGrammar
from gavo.parsing.nullgrammar import NullGrammar
from gavo.parsing.regrammar import REGrammar
from gavo.parsing.rowsetgrammar import RowsetGrammar
from gavo.web import common as webcommon
from gavo.web import core
from gavo.web import gwidgets
from gavo.web import resourcebased
from gavo.web import scs  # for registration
from gavo.web import service
from gavo.web import siap
from gavo.web import standardcores
from gavo.web import uploadservice  # for registration
import gavo


class Error(gavo.Error):
	pass

def makeAttDict(attrs):
	"""returns a dictionary suitable as keyword arguments from a sax attribute
	dictionary.
	"""
	return dict([(str(key), val) for key, val in attrs.items()])


class RdParser(nodebuilder.NodeBuilder):
	"""is a builder for a resource descriptor.

	When constructing, give forImport=True if the corresponding resource may
	not exist yet (i.e., when importing).
	"""
	noQueries = False
	keepWhitespaceNames = set(["meta"])

	def __init__(self, sourcePath, forImport=False):
		self.forImport = forImport
		nodebuilder.NodeBuilder.__init__(self)
		self.rd = resource.ResourceDescriptor(sourcePath)

	def _collectTextNodes(self, children):
		"""returns all text children concatenated.

		For mixed content elements, the order of text and element content
		is completely ignored.
		"""
		res = []
		for c in children:
			if c[0] is None:
				res.append(c[1])
		return "".join(res)

	def resolveItemReference(self, id):
		"""returns the element with id.

		If there's a # in id, the stuff in front of it is
		an inputs-relative path to another resource descriptor,
		and the id then refers to one of its elements.
		"""
		if "#" in id:
			rdPath, id = id.split("#", 1)
			if rdPath.startswith("./"):
				rdPath = os.path.join(os.path.dirname(self.rd.sourceId), rdPath)
			rd = resourcecache.getRd(rdPath, noQueries=self.noQueries)
			element = rd.getById(id)[1].copy()
		else:
			element = self.getById(id)[1].copy()
		element.setExtensionFlag(True)
		return element

	def _pushFieldPath(self, name, attrs):
		"""pushes a fieldPath property on the stack.

		This is supposed to be used as a _start method for all elements supporting
		a fieldPath.  Right now, they all have to pop the fieldPath in their
		_make methods.
		"""
		if attrs.has_key("fieldPath"):
			self.pushProperty("fieldPath", attrs["fieldPath"])
		else:
			try:
				self.pushProperty("fieldPath", self.getProperty("fieldPath"))
			except IndexError:
				self.pushProperty("fieldPath", "")

	def _start_ResourceDescriptor(self, name, attrs):
		self.rd.set_resdir(attrs["srcdir"])
		self.sourceDir = os.path.join(config.get("inputsDir"), attrs["srcdir"])

	def _make_schema(self, name, attrs, children):
# Has to happen as early as possible
		self.rd.set_schema(self._makeTextNode(name, attrs, children))

	def _make_ResourceDescriptor(self, name, attrs, children):
		self.rd.setIdMap(self.elementsById)
		self._processChildren(self.rd, name, {
			"DataProcessor": self.rd.addto_processors,
			"recreateAfter": self.rd.addto_dependents,
			"script": self.rd.addto_scripts,
			"Data": lambda val:0,      # these register themselves
			"Adapter": lambda val: 0,  # these register themselves
			"Service": lambda val: 0,  # these register themselves
			"property": lambda val: self.rd.register_property(*val),
			"meta": lambda mv: self.rd.addMeta(mv[0], mv[1]),
			"core": lambda val: 0, # referenced by services via id.
		}, children)
		# XXX todo: coordinate systems
		return self.rd

	_start_Data = _pushFieldPath

	def _make_Data(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		dd = resource.DataDescriptor(self.rd)
		dd.set_source(attrs.get("source"))
		dd.set_sourcePat(attrs.get("sourcePat"))
		dd.set_computer(attrs.get("computer"))
		dd.set_encoding(attrs.get("encoding", None))
		dd.set_id(attrs.get("id"))
		dd.set_virtual(attrs.get("virtual", "False"))
		dd.set_token(attrs.get("token", None))
		self.rd.addto_dataSrcs(dd)

		if "fieldsFrom" in attrs:
			for field in self.resolveItemReference(attrs["fieldsFrom"]).get_items():
				newField = field.copy()
				dd.addto_items(newField)
	
		res = self._processChildren(dd, name, {
			"Field": dd.addto_items,
			"Semantics": dd.set_Semantics,
			"Macro": dd.addto_macros,
			"Grammar": dd.set_Grammar,
			"meta": lambda mv: dd.addMeta(mv[0], mv[1]),
			"property": lambda val: dd.register_property(*val),
			"script": dd.addto_scripts,
			"ignoreSources": dd.set_ignoredSources,
		}, children)
		self.popProperty("fieldPath")
		return res

	def _make_ignoreSources(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		if "fromdb" in attrs:
			try:
				if self.noQueries:
					return set()
				else:
					res = set(r[0] for r in sqlsupport.SimpleQuerier().runIsolatedQuery(
						attrs["fromdb"]))
			except sqlsupport.DbError: # table probably doesn't exist yet.
				return set()
		else:
			raise Error("Can't interpret ignoreSources spec.")
		return res

	def _fillGrammarNode(self, grammar, attrs, children, classHandlers):
		"""handles children and attributes common to all grammar classes.

		grammar is an instance of the desired grammar class.

		classHandlers is a dict of _processChildren-like handlers for the
		children of the concrete grammar.

		For convenience, the function returns the instance passed in.
		"""
		if attrs.has_key("docIsRow"):
			grammar.set_docIsRow(attrs["docIsRow"])
		handlers = {
			"Macro": grammar.addto_macros,
			"RowProcessor": grammar.addto_rowProcs,
			"constraints": grammar.set_constraints,
		}
		handlers.update(classHandlers)
		return self._processChildren(grammar, grammar.__class__.__name__, 	
			handlers, children)
	
	def _make_CFGrammar(self, name, attrs, children):
		return nodebuilder.NamedNode("Grammar",
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
		return nodebuilder.NamedNode("Grammar", grammar)

	def _make_SimpleREGrammar(self, name, attrs, children):
		grammar = SimpleREGrammar()
		self._fillGrammarNode(grammar, attrs, children, {
				"rowProduction": grammar.set_rowProduction,
				"parseRE": grammar.set_parseRE,
			})
		return nodebuilder.NamedNode("Grammar", grammar)

	def _make_VOTableGrammar(self, name, attrs, children):
		grammar = VOTableGrammar()
		self._fillGrammarNode(grammar, attrs, children, {
			})
		return nodebuilder.NamedNode("Grammar", grammar)

	def _make_FitsGrammar(self, name, attrs, children):
		grammar = self._fillGrammarNode(FitsGrammar(), attrs, children, {})
		grammar.set_qnd(attrs.get("qnd", "False"))
		return nodebuilder.NamedNode("Grammar", grammar)

	def _make_ColumnGrammar(self, name, attrs, children):
		grammar = self._fillGrammarNode(ColumnGrammar(), attrs, children, {})
		grammar.set_topIgnoredLines(attrs.get("topIgnoredLines", 0))
		return nodebuilder.NamedNode("Grammar", grammar)

	def _make_DirectGrammar(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		grammar = DirectGrammar(**attrs)
		return nodebuilder.NamedNode("Grammar", 
			self._processChildren(grammar, name, {}, children))

	def _make_CustomGrammar(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		grammar = CustomGrammar(initvals=attrs)
		return nodebuilder.NamedNode("Grammar", 
			self._processChildren(grammar, name, {}, children))

	def _make_NullGrammar(self, name, attrs, children):
		return nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(NullGrammar(), attrs, children, {}))

	def _make_KeyValueGrammar(self, name, attrs, children):
		return nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(KeyValueGrammar(), attrs, children, {}))

	def _make_TableGrammar(self, name, attrs, children):
		return nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(tablegrammar.TableGrammar(), attrs, children, {}))

	_start_RowsetGrammar = _pushFieldPath

	def _make_RowsetGrammar(self, name, attrs, children):
		grammar = RowsetGrammar()
		res = nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(grammar, attrs, children, {
				"Field": grammar.addto_dbFields
			}))
		if attrs.has_key("fieldsFrom"):
			fieldSrc = self.getById(attrs["fieldsFrom"])[1]
			for field in fieldSrc.get_items():
				newField = field.copy()
				if not isinstance(fieldSrc, RowsetGrammar):
					newField.set_source(newField.get_dest())
				res.node.addto_dbFields(newField)
		self.popProperty("fieldPath")
		return res

	def _make_ContextGrammar(self, name, attrs, children):
		grammar = contextgrammar.ContextGrammar()
		return nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(grammar, attrs, children, {
				"inputKey": grammar.addto_inputKeys,
			}))

	def _make_DictlistGrammar(self, name, attrs, children):
		grammar = DictlistGrammar()
		return nodebuilder.NamedNode("Grammar",
			self._fillGrammarNode(grammar, attrs, children, {}))

	def _make_Semantics(self, name, attrs, children):
		semantics = resource.Semantics()
		return self._processChildren(semantics, name, {
			"Record": semantics.addto_tableDefs,
			"Table": semantics.addto_tableDefs,
		}, children)

	_start_Table = _pushFieldPath
	_start_Record = _pushFieldPath

	def _make_Table(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		if attrs.has_key("original"):
			tableDef = self.resolveItemReference(attrs["original"]).copy()
			setDefaults = False
		else:
			tableDef = resource.TableDef(self.rd)
			setDefaults = True
		# Ouch -- if I have a copy, I don't want to overwrite attributes
		# not given with defaults.  This sort of mess would be necessary
		# wherever we deal with copies like this.  Yikes.
		for attName, default in [("table", None), ("onDisk", "False"),
				("forceUnique", "False"), ("create", "True"), ("conflicts", "check"),
				("role", None), ("id", None)]:
			if attrs.has_key(attName):
				tableDef.set(attName, attrs[attName])
			elif setDefaults:
				tableDef.set(attName, default)
		if name.startswith("Shared"):
			tableDef.set_shared(True)

		if "fieldsFrom" in attrs:
			for field in self.resolveItemReference(attrs["fieldsFrom"]).get_items():
				newField = field.copy()
				newField.set_source(newField.get_dest())
				tableDef.addto_items(newField)
		
		interfaceNodes, children = self.filterChildren(children, "implements")
		for _, (interface, args) in interfaceNodes:
			children.extend(interface.getNodes(tableDef, **args))

		record = self._processChildren(tableDef, name, {
			"Field": tableDef.addto_items,
			"constraints": tableDef.set_constraints,
			"owningCondition": tableDef.set_owningCondition,
			"meta": lambda mv: tableDef.addMeta(mv[0], mv[1]),
			"script": tableDef.addto_scripts,
			"readRoles": tableDef.set_readRoles,
			"allRoles": tableDef.set_allRoles,
			"adql": tableDef.set_adql,
		}, children)

		for _, (interface, args) in interfaceNodes:
			for nodeDesc in interface.getDelayedNodes(tableDef, **args):
				self.registerDelayedChild(*nodeDesc)
		self.popProperty("fieldPath")

		for _, (interface, args) in interfaceNodes:
			interface.mogrifyNode(tableDef)

		return nodebuilder.NamedNode("Table", record)

	_make_Record = _make_Table
	_start_SharedTable = _start_Table
	_make_SharedTable = _make_Table
	_start_SharedRecord = _start_SharedTable
	_make_SharedRecord = _make_SharedTable

	def _make_fromgrammar(self, name, attrs, children):
		return self._processChildren("", name, {}, children)

	def _make_implements(self, name, attrs, children):
		args = dict([(key, val) for key, val in attrs.items()])
		interfaceName = args["name"]
		del args["name"]
		return interfaces.getInterface(interfaceName), args

	def _make_owningCondition(self, name, attrs, children):
		return attrs["colName"], attrs["value"]

	def _grabField(self, fieldPath):
		"""returns the field pointed to by fieldPath.

		fieldPath is a dot-seperated triple TableCarrier.Table.fieldName.

		TableCarrier can be anything that has a getTableDefByName method and 
		can be referred by id; primarily, that's DataDescriptors, but also
		computed cores or similar qualify.

		If fieldPath starts with a dot, it is interpreted relative to
		the fieldPath property.
		"""
		if fieldPath.startswith("."):
			fieldPath = self.getProperty("fieldPath")+fieldPath
		try:
			dataId, tableName, fieldName = fieldPath.split(".")
		except ValueError:
			raise Error("Invalid field path '%s'.  Did you forget a leading dot?"%
				fieldPath)
		try:
			return self.resolveItemReference(dataId).getTableDefByName(tableName
				).getFieldByName(fieldName)
		except KeyError:
			raise Error("Field does not exist: %s"%fieldPath)

	def _makeFieldInstance(self, fieldClass, name, attrs, children, nodeHandlers):
		"""creates an instance of the datafield.DataDef-derived class fieldClass
		according to attrs and children.
		"""
		attrs = makeAttDict(attrs)
		if attrs.has_key("original"):
			field = fieldClass.fromDataField(
				self._grabField(attrs["original"]))
			del attrs["original"]
		else:
			field = fieldClass()
		for key, val in attrs.items():
			field.set(key, val)
		handlers = {
			"longdescr": field.set_longdescription,
			"Values": field.set_values,
			"property": lambda val: field.register_property(*val),
		}
		for key, hdlr in nodeHandlers.iteritems():
			handlers[key] = getattr(field, hdlr)
		return self._processChildren(field, name, handlers, children)

	def _make_Field(self, name, attrs, children):
		return self._makeFieldInstance(datadef.DataField, 
			"Field", attrs, children, {})

	def _make_outputField(self, name, attrs, children):
		f = self._makeFieldInstance(datadef.OutputField, "outputField", 
			attrs, children, {
				"renderer": "set_renderer"})
		if not f.get_source():
			f.set_source(f.get_dest())
		return f

	def _make_inputKey(self, name, attrs, children):
		return self._makeFieldInstance(gwidgets.InputKey, "inputKey",
			attrs, children, {})

	def _make_copyof(self, name, attrs, children):
		name, obj = self.getById(attrs["idref"])
		if hasattr(obj, "copy"):
			obj = obj.copy()
		return nodebuilder.NamedNode(name, obj)

	def _make_longdescr(self, name, attrs, children):
		return attrs.get("type", "text/plain"), self.getContent(children)

	def _make_Values(self, name, attrs, children):
		def getOptionsFromDb(expr):
			if self.noQueries:
				return []
			return [a[0] for a in
				sqlsupport.SimpleQuerier().runIsolatedQuery("SELECT DISTINCT %s"%(
					expr))]
		vals = datadef.Values()
		for key, val in attrs.items():
			if key=="fromdb": 
				if not self.forImport:
					vals.set_options(getOptionsFromDb(val))
			elif key=="id":
				continue
			else:
				vals.set(key, val)
		return self._processChildren(vals, name, {
			"option": vals.addto_options,
		}, children)

	def _make_Macro(self, name, attrs, children):
		initArgs = dict([(str(key), value) 
			for key, value in attrs.items() if key!="name"])
		macro = macros.getMacro(attrs["name"])(**initArgs)
		return self._processChildren(macro, name, {
			"arg": macro.addArgument,
		}, children)

	def _make_macrodef(self, name, attrs, children):
		code = children[0][1]
		return nodebuilder.NamedNode("Macro", 
			macros.compileMacro(attrs["name"], code))

	def _make_RowProcessor(self, name, attrs, children):
		initArgs = dict([(str(key), value) 
			for key, value in attrs.items() if key!="name"])
		proc = processors.getProcessor(attrs["name"])(**initArgs)
		return self._processChildren(proc, name, {
			"arg": proc.addArgument,
		}, children)

	def _make_procdef(self, name, attrs, children):
		code = children[0][1]
		return nodebuilder.NamedNode("RowProcessor",
			processors.compileProcessor(attrs["name"], code))

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
				# XXX TODO we should at least support @-expansions.
				raise Error("RdParser doesn't know what to do with computed"
					" arguments")
			res[str(name)] = val
		return res

	def _make_arg(self, name, attrs, children):
		defaultValue = self.getContent(children) or None
		return attrs["name"], attrs.get("source"), attrs.get("value", defaultValue)

	def _make_tokenizer(self, name, attrs, children):
		return self.getContent(children), attrs["type"]

	def _make_script(self, name, attrs, children):
		return (attrs["type"], attrs.get("name", "<anonymous>"),
			self.getContentWS(children))

	def _make_renderer(self,name, attrs, children):
		return self.getContentWS(children)

	def _make_constraints(self, name, attrs, children):
		constraints = conditions.Constraints(fatal=record.parseBooleanLiteral(
			attrs.get("fatal", "False")))
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
		attrs = makeAttDict(attrs)
		adapter = resource.DataDescriptor(self.rd, id=attrs["id"])
		adapter.set_name(attrs["name"])
		self.rd.register_adapter(adapter.get_id(), adapter)

		if "fieldsFrom" in attrs:
			for field in self.resolveItemReference(attrs["fieldsFrom"]).get_items():
				newField = field.copy()
				adapter.addto_items(newField)
	
		return self._processChildren(adapter, name, {
			"Field": adapter.addto_items,
			"Semantics": adapter.set_Semantics,
			"Macro": adapter.addto_macros,
			"Grammar": adapter.set_Grammar,
			"meta": lambda mv: adapter.addMeta(mv[0], mv[1]),
		}, children)

	def _start_Service(self, name, attrs):
		self._pushFieldPath(name, attrs)
		svc = service.Service(self.rd, {"id": attrs["id"],
			"staticData": attrs.get("staticData")})
		self.pushProperty("currentService", svc)

	def _make_Service(self, name, attrs, children):
		svc = self.popProperty("currentService")
		self.rd.register_service(svc.get_id(), svc)
		res = self._processChildren(svc, name, {
			"inputFilter": svc.set_inputFilter,
			"core": svc.set_core,
			"customPage": svc.set_customPage,
			"outputFilter": lambda val: 
				svc.register_output(val.get_id(), val),
			"meta": lambda mv: svc.addMeta(mv[0], mv[1]),
			"template": lambda val: svc.register_template(*val),
			"property": lambda val: svc.register_property(*val),
			"fieldNameTranslation": svc.set_fieldNameTranslations,
			"nevowRender": lambda c: svc.register_specRend(*c),
			"protect": lambda v: svc.set_requiredGroup(v["group"]),
			"publish": svc.addto_publications,
			"renderers": svc.set_allowedRenderers,
			"srvInput": svc.set_condDescs,
			"srvOutput": svc.set_outputFields,
		}, children)
		self.popProperty("fieldPath")
		return res
	
	def _make_srvInput(self, name, attrs, children):
		inputs = record.DataFieldList()
		def handleFromCore(ignored):
			try:
				svcCore = self.getWaitingChild("core", maxLevels=2)
				for f in svcCore.getInputFields():
					inputs.append(standardcores.CondDesc.fromInputKey(f))
			except AttributeError:
				traceback.print_exc()
				raise gavo.Error("%s cores do not support fromCore"%
					svcCore.__class__.__name__)
			except nodebuilder.NoWaitingChild:
				raise gavo.Error("fromCore requires previous core definition")
		return self._processChildren(inputs, name, {
			"condDesc": inputs.append,
			"fromCore": handleFromCore,
		}, children)
	
	def _make_srvOutput(self, name, attrs, children):
		outputs = record.DataFieldList()
		def handleFromCore(attrs):
			verbLimit = int(attrs.get("verbLevel", 20))
			try:
				svcCore = self.getWaitingChild("core", maxLevels=2)
				for f in svcCore.getOutputFields():
					if f.get_verbLevel()<=verbLimit:
						outputs.append(datadef.OutputField.fromDataField(f))
			except AttributeError:
				raise gavo.Error("%s cores no not support fromCore"%
					svcCore.__class__.__name__)
			except nodebuilder.NoWaitingChild:
				raise gavo.Error("fromCore requires previous core definition")
		return self._processChildren(outputs, name, {
			"outputField": outputs.append,
			"fromCore": handleFromCore,
			"property": lambda val: outputs.register_property(*val),
		}, children)

	def _make_fromCore(self, name, attrs, children):
		return makeAttDict(attrs)

	def _make_customPage(self, name, attrs, children):
		moduleName = attrs["module"]
		try:
			modNs, moddesc = parsehelpers.getModule(self.sourceDir, moduleName)
			page = modNs.MainPage
		except ImportError:
			traceback.print_exc()
			logger.error("Bad custom page %s"%moduleName)
			return None
		return page, (os.path.basename(moduleName),)+moddesc

	def _make_protect(self, name, attrs, children):
		return self._processChildren(makeAttDict(attrs), name, {}, children)

	def _make_allow(self, name, attrs, children):
		if attrs.has_key("renderers"):
			return nodebuilder.NamedNode("renderers", 
				set([s.strip() for s in attrs["renderers"].split(",")]))

	def _make_publish(self, name, attrs, children):
		return self._processChildren(makeAttDict(attrs), name, {}, children)

	def _make_fieldNameTranslation(self, name, attrs, children):
		"""temporary hack: use attributes as translation dictionary.

		We need to come up with something better...
		"""
		return makeAttDict(attrs)

	def _make_inputFilter(self, name, attrs, children):
		return self.rd.get_adapter(attrs["idref"])
	
	def _make_outputFilter(self, name, attrs, children):
		return self.rd.get_adapter(attrs["idref"])

	def _make_template(self, name, attrs, children):
		return (attrs["type"], attrs["src"])

	def _make_core(self, name, attrs, children):
		def handlerFactory(core, elName, methodName):
			if hasattr(core, methodName):
				return getattr(core, methodName)
			else:
				def raiseError(*args):
					raise gavo.Error("No %s children on these cores"%elName)
				return raiseError

		handlers = {
			"arg": lambda *args: None,  # Handled by core constructor
		}

		attrs = makeAttDict(attrs)
		args = self._collectArguments(children)
		if "module" in attrs:
			parsehelpers.getModule(self.sourceDir, attrs["module"])
			del attrs["module"]
		builtinName = attrs.pop("builtin")
		attrs.update(args)
		curCore = core.getStandardCore(builtinName)(self.rd, initvals=attrs)
		if builtinName=="computed":
			handlers["Table"] = curCore.addto_tables
		return self._processChildren(curCore, name, handlers, children)

	def _make_nevowRender(self, name, attrs, children):
		"""returns a pair of (name, function object) for a renderer to be
		inserted into the core result.
		"""
		return (attrs["name"], resourcebased.compileCoreRenderer(
			self._makeTextNode(name, attrs, children)))

	def _make_autoOutputFields(self, name, attrs, children):
		"""returns a web.common.QueryMeta instance out of attrs.
		"""
		return self._processChildren(webcommon.QueryMeta(
				dict((key, [attrs[key]]) for key in attrs.keys())),
			name, {}, children)

	def _make_autoCondDescs(self, name, attrs, children):
		return self._processChildren("", name, {}, children)

	_condDescAttrs = set(["original", "silent", "fixedSQL"])

	def _make_condDesc(self, name, attrs, children):
		fieldAttrs, cdAttrs = {}, {}
		if attrs.has_key("predefined"):
			cdAttrs = dict(attrs.items())
			del cdAttrs["predefined"]
			return self._processChildren(core.getCondDesc(attrs["predefined"]
					)(initvals=cdAttrs),
				name, {}, children)
		for key, val in attrs.items():
			if key in self._condDescAttrs:
				cdAttrs[key] = val
			else:
				fieldAttrs[key] = val
		if cdAttrs.has_key("original"):
			original = cdAttrs.pop("original")
			return self._processChildren(standardcores.CondDesc.fromInputKey(
					gwidgets.InputKey.fromDataField(
						self._grabField(original), fieldAttrs), cdAttrs),
				name, {}, children)
		else:
			condDesc = standardcores.CondDesc(initvals=cdAttrs)
			return self._processChildren(condDesc, name, {
				"inputKey": condDesc.addto_inputKeys,
			}, children)

	def _make_meta(self, name, attrs, children):
		content = self._collectTextNodes(children)
		attrs = makeAttDict(attrs)
		if attrs.get("format", "plain") in ["rst", "literal"]:
			content = utils.fixIndentation(content, "", 1)
		key = attrs["name"]
		metaValue = meta.makeMetaValue(content, **attrs)
		self._processChildren(metaValue, name, {
			"meta": lambda md: metaValue.addMeta(md[0], md[1]),
			None: lambda *args: True, # Text children processed above
		}, children)
		return key, metaValue

	def _make_property(self, name, attrs, children):
		return (attrs["name"], self._makeTextNode(name, attrs, children).strip())

	def _make_elgen(self, name, attrs, children):
		attrs = makeAttDict(attrs)
		genName = attrs.pop('name')
		self.runGenerator(elgen.getElgen(genName)(**attrs))

	def _makeTextNode(self, name, attrs, children):
		if len(children)==0:
			return ""
		if len(children)!=1 or children[0][0] is not None:
			raise Error("%s nodes have text content only"%name)
		return children[0][1]
	

	_make_rules = \
	_make_documentProduction = \
	_make_rowProduction = \
	_make_tabularDataProduction = \
	_make_tokenSequence = \
	_make_rowProduction = \
	_make_parseRE = \
	_make_option = \
	_make_adql = \
	_make_readRoles = \
	_make_allRoles = \
	_makeTextNode


class InputEntityResolver(EntityResolver):
	def resolveEntity(self, publicId, systemId):
		return open(os.path.join(config.get("parsing", "xmlFragmentPath"), 
			systemId+".template"))


def getParser(srcPath, parserClass=RdParser, forImport=False):
	"""returns a SAX parser set up for reading resouce descriptors.
	"""
	contentHandler = parserClass(srcPath, forImport=forImport)
	parser = make_parser()
	parser.setContentHandler(contentHandler)
	parser.setEntityResolver(InputEntityResolver())
	return contentHandler, parser


def getRdInputStream(srcId):
	"""returns a read-open stream for the XML source of the resource
	descriptor with srcId.
	"""
	userInput = srcId
	srcPath = os.path.join(config.get("inputsDir"), srcId)
	if os.path.isfile(srcPath):
		return srcPath, open(srcPath)
	if not srcId.endswith(".vord"):
		srcId = srcId+".vord"
	srcPath = os.path.join(config.get("inputsDir"), srcId)
	if os.path.isfile(srcPath):
		return srcPath, open(srcPath)
	srcPath = "/resources/inputs/"+srcId
	if pkg_resources.resource_exists('gavo', srcPath):
		return srcPath, pkg_resources.resource_stream('gavo', srcPath)
	raise gavo.RdNotFound("No such resource descriptor: %s"%userInput)


def getRd(srcId, parserClass=RdParser, forImport=False, noQueries=False):
	"""returns a ResourceDescriptor for srcId.

	srcId is something like an input-relative path; you'll generally
	omit the extension (unless it's not the standard .vord).
	"""
	srcPath, inputFile = getRdInputStream(srcId)
	contentHandler, parser = getParser(srcPath, parserClass, forImport)
	contentHandler.noQueries = noQueries
	try:
		parser.parse(inputFile)
		inputFile.close()
	except gavo.RdNotFound:
		raise
	except IOError, msg:
		logger.error("Could not open descriptor %s (%s)."%(srcPath, msg))
		gavo.raiseTb(gavo.RdNotFound, "Could not open descriptor %s (%s)."%(
			srcPath, msg))
	except Exception, msg:
		gavo.raiseTb(gavo.Error, "While parsing Desriptor %s: %s."
			"  Please check input validity."%(srcPath, msg))
	rd = contentHandler.getResult()
	if os.path.exists(srcPath+".blocked"):
		rd.currently_blocked = True
	if not rd.getMeta("dateUpdated"):
		try:
			rd.addMeta("dateUpdated", time.strftime("%Y-%m-%d", 
				time.gmtime(os.path.getmtime(rd.getTimestampPath()))))
		except os.error:
			pass
	return rd


def forAllSources(rdId, dataId, callable, *callableArgs):
	"""runs callable for all sources covered by DataDefinition dataId in the
	rd at rdId.

	callable will receive an absolute path to the source and callableArgs.
	"""
	datadef = resourcecache.getRd(rdId
		).getDataById(dataId)
	counter = gavo.ui.getGoodBadCounter("Processing sources", 1)
	for fName in datadef.iterSources():
		try:
			counter.hit()
			callable(fName, *callableArgs)
		except KeyboardInterrupt:
			counter.unhit()
			break
		except Exception, msg:
			counter.hitBad()
			logger.error("Error while processing %s: %s\n"%(fName, str(msg)),
				exc_info=True)
			gavo.ui.displayError("Processing %s failed: %s\n"%(fName, str(msg)))
	counter.close()


resourcecache.makeCache("getRd", getRd)


def _test():
	import doctest, importparser
	doctest.testmod(importparser)


if __name__=="__main__":
#	_test()
	parsing.verbose = True
	getRd("apfs/res/apfs_new.vord")
