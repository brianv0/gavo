"""
Classes and functions to build "services".

Roughly, a service consists of 

 * a nonempty sequence of input adapters
 * a Data instance (the "core")
 * a (possibly empty) registry of output filters

Filters and the core all have Semantics and a (possibly null grammar)

The interface of a service is built through:

 * The input arguments are given by the grammar of the first
   filter (which will usually be a ContextGrammar)
 * The output columns are given by the selected table of the output filter.
"""

import cStringIO
import weakref

from twisted.internet import defer
from twisted.python import components
from nevow import inevow
from zope.interface import implements

from gavo import datadef
from gavo import record
from gavo import table
from gavo import record
from gavo.parsing import contextgrammar
from gavo.parsing import meta
from gavo.parsing import resource


class DataSetAdapter(object):
	"""is an adapter to make DataSets work as nevow.IContainers
	"""
	implements(inevow.IContainer)

	def __init__(self, original):
		self.original = original
		for n in dir(self.original):
			if not n.startswith("_"):
				setattr(self, n, getattr(self.original, n))

	def data_resultmeta(self, ctx):
		result = self.original.getTables()[0]
		return {
			"itemsMatched": len(result.rows),
		}

	def child(self, ctx, name):
		if name=="table":
			return self.original.getTables()[0]
		else:
			return getattr(self, "data_"+name)(ctx)

components.registerAdapter(DataSetAdapter, resource.InternalDataSet,
	inevow.IContainer)




class QueryMeta(dict):
	"""is a class keeping all data *about* a query, e.g., the requested
	output format.

	It is constructed with the dictionary-like thing mapping form keys
	to values.
	"""
	def __init__(self, formData):
		self._fillOutputOptions(formData)
		self._fillOutputFilter(formData)
	
	def _fillOutputOptions(self, formData):
		"""interprets values left by gwidget.OutputOptions.
		"""
		outputOptions = formData.get("output", {})
		self["format"] = outputOptions.get("format", "VOTable")
		self["verbosity"] = int(outputOptions.get("verbosity", '2'))*10
		self["tdEnc"] = outputOptions.get("tdEnc", False)
	
	def _fillOutputFilter(self, formData):
		self["outputFilter"] = formData.get("FILTER", "default")


class Service(record.Record, meta.MetaMixin):
	"""is a model for a service.

	It contains:

	 * a list of Adapter instances for input (inputFilters)
	 * a dict mapping output ids to pairs of adapters and names of tables
	   within those adapters.
	 * a core, i.e., an object having getInputFields, run, and parseOutput
	   methods.
	
	The inputFilters are processed sequentially, while only exactly one of
	the outputs is selected when a service runs.

	The first inputFilter must have a getInputFields method that returns
	a sequence of datadef.DataField instances describing what input it
	requries.
	"""
	def __init__(self, rd, initvals):
		self.rd = weakref.proxy(rd)
		record.Record.__init__(self, {
			"inputFilter": None,
			"output": record.DictField,
			"core": record.RequiredField,
			"id": record.RequiredField,
		}, initvals)

	def _getDefaultInputFilter(self):
		"""returns an input filter from a web context implied by the service.
		"""
		# XXX TODO: id and table name is not unique, ask rd for an id.
		if not hasattr(self, "_defaultInputFilter"):
			self._defaultInputFilter = datadef.DataTransformer(self.rd,
				initvals={
					"Grammar": contextgrammar.ContextGrammar(initvals={
							"inputKeys": self.get_core().getInputFields()
						}),
					"Semantics": resource.Semantics(initvals={
							"recordDefs": [resource.RecordDef(initvals={
								"table": "NULL",
								})]
						}),
					"id": "<generated>", 
					"items": self.get_core().getInputFields(),
				})
		return self._defaultInputFilter

	def get_inputFilter(self):
		# The default input filter is given by the core
		if self.dataStore["inputFilter"]==None:
			return self._getDefaultInputFilter()
		else:
			return self.dataStore["inputFilter"]

	def register_output(self, key, value):
		# the first key added becomes the default.
		if not self.dataStore["output"]:
			self.dataStore["output"]["default"] = value
		else:
			self.dataStore["output"][key] = value

	def getInputFields(self):
		return self.get_inputFilter().getInputFields()
	
	def _getInputData(self, inputData):
		dD = self.get_inputFilter()
		curData = resource.InternalDataSet(dD, table.Table, inputData)
		return curData

	def _runCore(self, inputTable, queryMeta):
		return self.get_core().run(inputTable, queryMeta)

	def _parseResult(self, input, queryMeta):
		"""sends the result of the core process through the core parser and
		the output filter, returning a result table.

		input must match core's grammar, i.e. needs to be a string for 
		text-processing grammars.
		"""
		result = self.get_core().parseOutput(input, queryMeta)
		outputFilter = queryMeta["outputFilter"]
		if outputFilter and self.get_output(outputFilter):
			result = resource.InternalDataSet(self.get_output(outputFilter), 
				result.getTables()[0].getInheritingTable, result)
		return DataSetAdapter(result)

	def getResult(self, rawInput, outputFilter=None):
		"""returns a Deferred for the raw output of core.
		"""
		queryMeta = QueryMeta(rawInput)
		inputData = self._getInputData(rawInput)
		retVal = defer.Deferred()
		data = self._runCore(inputData, queryMeta)
		data.addCallback(lambda res: 
			retVal.callback(self._parseResult(res, queryMeta)))
		data.addErrback(lambda res: retVal.errback(res))
		return retVal

