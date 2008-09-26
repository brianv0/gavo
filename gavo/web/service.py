"""
Classes and functions to build "services".

Roughly, a service consists of 

 * an optional input adapter
 * a Data instance (the "core")
 * a (possibly empty) registry of output filters

Filters and the core all have Semantics and a (possibly null) grammar

The interface of a service is built through:

 * The input arguments are given by the grammar of the first
   filter (which will usually be a ContextGrammar)
 * The output columns are given by the selected table of the output filter.
"""

import cStringIO
import weakref

from nevow import inevow
from twisted.internet import defer
from twisted.python import components

from zope.interface import implements

import gavo
from gavo import config
from gavo import datadef
from gavo import macros
from gavo import meta
from gavo import record
from gavo import table
from gavo import record
from gavo.parsing import contextgrammar
from gavo.parsing import tablegrammar
from gavo.parsing import resource
from gavo.parsing import scripting
from gavo.web import common


class TableContainer(object):
	"""is a nevow.IContainer exposing tables.
	"""
	pass


class SvcResult(object):
	"""is a nevow.IContainer that has the result and also makes the input
	dataset accessible.

	SvcResult objects have a resultmeta dictionary that you can, in
	principle, use to communicate any kind of information.  However,
	renderers should at least check for the presence of a non-empty
	message and display its contents prominently.

	SvcResult objects must be able to fall back to sensible behaviour
	without a service.  This may be necessary in error handling.
	"""
	implements(inevow.IContainer)
	
	def __init__(self, coreResult, inputData, queryMeta, service=None):
		self.queryPars = queryMeta.get("formal_data", {})
		self.inputData = inputData
		self.queryMeta = queryMeta
		self.service = service
		for n in dir(coreResult):
			if not n.startswith("_"):
				setattr(self, n, getattr(coreResult, n))
		self.original = self._adaptCoreResult(coreResult, queryMeta)

	def _adaptCoreResult(self, coreResult, queryMeta):
		"""returns the DataSet coreResult adapted for self.service's interface.

		There are five cases:
		(1) coreResult set has exactly the fields the service expects -- return it
		(2) the service expects a restriction of coreResult -- do the restriction
		(3) coreResult is missing columns -- fill up the missing values with
		    Nones unless the service has declared one of them as non-optional
			  (in which case an error will be raised).
		(4) coreResult is a tuple (file), a string or a table-less data --
		    return it untouched.
		(5) the core has a noPostprocess attribute -- leave the data alone.
		"""
		if isinstance(coreResult, (str, tuple)) or (self.service and hasattr(
				self.service.get_core(), "noPostprocess")):
			return coreResult
		if len(coreResult.tables)==0 or not self.service:
			return coreResult
		svcFields = self.service.getCurOutputFields(queryMeta)
		if coreResult.getPrimaryTable().getFieldDefs()==svcFields:
			return coreResult
		else:
			res = resource.InternalDataSet(
				resource.makeGrammarDataDesc(self.service.rd, svcFields, 
					tablegrammar.TableGrammar()),
				dataSource=coreResult)
			return res

	def data_resultmeta(self, ctx):
		result = self.original.getPrimaryTable()
		resultmeta = {
			"itemsMatched": len(result.rows),
			"filterUsed": self.queryMeta.get("outputFilter", ""),
# XXX TODO: We want to be able to communicate mild error messages from
# cores.  Right now, we hack a message attribute into the datasets, but
# that's bad.  We don't use this yet, but we want some structured means
# for this in a rewrite.
			"message": getattr(self.original, "message", ""),
		}
		return resultmeta

	def data_querypars(self, ctx=None):
		return dict((k, str(v)) for k, v in self.queryPars.iteritems()
			if not k in common.QueryMeta.metaKeys and v and v!=[None])

	suppressedParNames = set(["submit"])
		
	def data_queryseq(self, ctx=None):
		if self.service:
			fieldDict = dict((f.get_dest(), f) 
				for f in self.service.getInputFields())
		else:
			fieldDict = {}

		def getTitle(key):
			title = None
			if key in fieldDict:
				title = fieldDict[key].get_tablehead()
			return title or key
		
		s = [(getTitle(k), v) for k, v in self.data_querypars().iteritems()
			if k not in self.suppressedParNames and not k.startswith("_")]
		s.sort()
		return s

	def data_inputRec(self, ctx=None):
		return self.inputData.getDocRec()

	def data_table(self, ctx=None):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class Service(record.Record, meta.MetaMixin, macros.StandardMacroMixin):
	"""is a model for a service.

	It mainly contains:

	 * a list of Adapter instances for input (inputFilters)
	 * a dict mapping output ids to pairs of adapters and names of tables
	   within those adapters.
	 * a core
	
	The inputFilters are processed sequentially, while only exactly one of
	the outputs is selected when a service runs.

	The first inputFilter must have a getInputFields method that returns
	a sequence of datadef.DataField instances describing what input it
	requries.
	"""
	def __init__(self, rd, initvals):
		self.rd = weakref.proxy(rd)
		self.setMetaParent(self.rd)
		record.Record.__init__(self, {
			"outputFields": record.DataFieldList,
			"condDescs": record.DataFieldList,
			"inputFilter": None,
			"output": record.DictField,
			"core": record.RequiredField,
			"id": record.RequiredField,
			"template": record.DictField,
			"property": record.DictField,
			"publications": record.ListField,
			"requiredGroup": None,
			"staticData": None,
			"customPage": None,
			"allowedRenderers": None,
			"specRend": record.DictField, # additional renderers in the core result.
# temporary hack: map field names to ones known to the form.
			"fieldNameTranslations": None,
		}, initvals)

	def __repr__(self):
		return "<Service at %x>"%id(self)

	def __str__(self):
		return "<Service at %x>"%id(self)

	def addto_publications(self, pubDict):
		if not "render" in pubDict:
			pubDict["render"] = "form"
		if not "sets" in pubDict:
			pubDict["sets"] = ""
		self.dataStore["publications"].append(pubDict)

	def set_core(self, core):
		self.dataStore["core"] = core
		core.set_service(self)

	def getInputFields(self):
		if self.dataStore["inputFilter"]:
			return self.dataStore["inputFilter"].get_Grammar().get_inputKeys()
		res = []
		for cd in self.get_condDescs():
			res.extend(cd.get_inputKeys())
		return res

	def getOutputFieldsByVerbosity(self, tableName, verbosity):
		"""returns OutputFields for for all fields in tableName with 
		a verbLevel<=verbosity.
		"""
		tableDef = self.rd.getTableDefByName(srcTable)
		return [datadef.OutputField.fromDataField(f)
			for f in self.tableDef.get_items()
			if f.get_verbLevel()<=verbLimit]

	def addAutoOutputFields(self, tableName, verbosity):
		"""adds all fields matching verbLevel<=queryMeta["verbosity"].

		This is used by the import parser.
		"""
		for f in self.getOutputFieldsByVerbosity(tableName, int(verbosity)):
			self.addto_outputFields(f)

	def _getVOTableOutputFields(self, queryMeta):
		"""returns a list of OutputFields suitable for a VOTable response described
		by queryMeta
		"""
		verbLevel = queryMeta.get("verbosity", 20)
		if verbLevel=="HTML":
			fieldList = record.DataFieldList([
					f for f in self.getHTMLOutputFields(queryMeta)
				if f.get_displayHint().get("noxml")!="true"])
		else:
			try:
				baseFields = self.get_core().getOutputFields()
			except KeyError:
				baseFields = self.get_outputFields()
			fieldList = record.DataFieldList([f for f in baseFields
				if f.get_verbLevel()<=verbLevel and 
					f.get_displayHint().get("type")!="suppress" and
					f.get_displayHint().get("noxml")!="true"])
		return fieldList

	def getHTMLOutputFields(self, queryMeta, ignoreAdditionals=False):
		"""returns a list of OutputFields suitable for an HTML response described
		by queryMeta
		"""
		res = record.DataFieldList([f for f in self.get_outputFields()
			if f.get_displayHint().get("type")!="suppress"])
		if not ignoreAdditionals and queryMeta["additionalFields"]:
			cofs = self.get_core().getOutputFields()
			try:
				for fieldName in queryMeta["additionalFields"]:
					res.append(datadef.OutputField.fromDataField(
						cofs.getFieldByName(fieldName)))
			except KeyError, msg:
				raise gavo.Error("Sorry, the additional field %s you requested"
					" does not exist"%str(msg))
		return res

	def _getTarOutputFields(self, queryMeta):
		return record.DataFieldList()  # Not used.

	def getCurOutputFields(self, queryMeta=None):
		"""returns a list of desired output fields for query meta.

		This is for both the core and the formatter to figure out the
		structure of the tables passed.

		If queryMeta is not None, both the format and the verbLevel given
		there can influence this choice.
		"""
		queryMeta = queryMeta or common.emptyQueryMeta
		outputFilter = queryMeta.get("outputFilter")
		if outputFilter and self.get_output(outputFilter):
			return self.get_output(outputFilter).getPrimaryTableDef().get_items()
		format = queryMeta.get("format", "HTML")
		if format=="HTML":
			return self.getHTMLOutputFields(queryMeta)
		else:
			return self._getVOTableOutputFields(queryMeta)

	def _getDefaultInputFilter(self):
		"""returns an input filter from a web context implied by the service.
		"""
		# XXX TODO: id and table name is not unique, ask rd for an id.
		if not hasattr(self, "_defaultInputFilter"):
			coreFields = self.getInputFields()
			self._defaultInputFilter = datadef.DataTransformer(self.rd,
				initvals={
					"Grammar": contextgrammar.ContextGrammar(initvals={
							"inputKeys": coreFields,
						}),
					"Semantics": resource.Semantics(initvals={
							"tableDefs": [resource.TableDef(self.rd, initvals={
								"table": "NULL",
								})]
						}),
					"id": "<generated>", 
					"items": coreFields,
				})
		return self._defaultInputFilter

	def get_inputFilter(self):
		# The default input filter is given by the core
		if self.dataStore["inputFilter"] is None:
			return self._getDefaultInputFilter()
		else:
			return self.dataStore["inputFilter"]

	defaultAllowedRenderers = set(["form"])
	def get_allowedRenderers(self):
		if self.dataStore["allowedRenderers"] is None:
			return self.defaultAllowedRenderers
		else:
			return self.dataStore["allowedRenderers"]

	def register_output(self, key, value):
		# the first key added becomes the default.
		if not self.dataStore["output"]:
			self.dataStore["output"]["default"] = value
		else:
			self.dataStore["output"][key] = value

	def translateFieldName(self, name):
		"""returns a field name present in the input for a field name
		that may only have been introduced in later processing stages.
		"""
		if self.get_fieldNameTranslations():
			return self.get_fieldNameTranslations().get(name, name)
		return name

	def getInputData(self, inputData):
		dD = self.get_inputFilter()
		curData = resource.InternalDataSet(dD, table.Table, inputData)
		return curData

	def _postProcess(self, coreOutput, queryMeta):
		"""sends the result of the core through the output filter.
		"""
		outputFilter = queryMeta["outputFilter"]
		if outputFilter and self.get_output(outputFilter):
			result = resource.InternalDataSet(self.get_output(outputFilter), 
				coreOutput.getPrimaryTable().getInheritingTable, coreOutput)
		else:
			result = coreOutput
		return result

	def run(self, inputData, queryMeta=common.emptyQueryMeta):
		"""runs the input filter, the core, and the output filter and returns a
		deferred firing an adapted result table.

		The adapted result table has an additional method getInput returning the
		processed input data.
		"""
		return self.get_core().run(inputData, queryMeta).addCallback(
			self._postProcess, queryMeta).addErrback(
			lambda failure: failure).addCallback(
			SvcResult, inputData, queryMeta, self).addErrback(
			lambda failure: failure)
	
	def getURL(self, renderer, method="POST"):
		"""returns the full canonical access URL of this service together 
		with renderer.
		"""
		qSep = ""
		if method=="GET":
			qSep = "?"
		elif renderer=="soap":
			qSep = "/go"
		return "".join([
			config.get("web", "serverURL"),
			config.get("web", "nevowRoot"),
			"/",
			self.rd.sourceId,
			"/",
			self.get_id(),
			"/",
			renderer,
			qSep])
	
	def getDefaultMeta(self, key):
		if key=="referenceURL":
			try:
				return self.getMetaParent().getMeta("referenceURL", raiseOnFail=True)
			except gavo.NoMetaKey:
				return meta.MetaItem(
					meta.makeMetaValue(self.getURL("info"),
						type="link", title="Service info"))
		raise KeyError(key)
