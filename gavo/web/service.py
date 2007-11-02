"""
Classes and functions to build "services".

Roughly, a service consists of 

 * an optional input adapter
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
from gavo.web import common


class TableContainer(object):
	"""is a nevow.IContainer exposing tables.
	"""
	pass

class CoreResult(object):
	"""is a nevow.IContainer that has the result and also makes the input
	dataset accessible.
	"""
	implements(inevow.IContainer)

	def __init__(self, resultData, inputData, queryPars):
		self.original = resultData
		self.queryPars = queryPars
		self.inputData = inputData
		for n in dir(self.original):
			if not n.startswith("_"):
				setattr(self, n, getattr(self.original, n))

	def data_resultmeta(self, ctx):
		result = self.original.getTables()[0]
		return {
			"itemsMatched": len(result.rows),
		}

	def data_querypars(self, ctx):
		return dict([(k, str(v)) for k, v in self.queryPars.iteritems()])

	def data_inputRec(self, ctx):
		return self.inputData.getDocRec()

	def data_table(self, ctx):
		return self.original.getPrimaryTable()

	def child(self, ctx, name):
		return getattr(self, "data_"+name)(ctx)


class Service(record.Record, meta.MetaMixin):
	"""is a model for a service.

	It mainly contains:

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
			"template": record.DictField,
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

	def run(self, rawInput, outputFilter=None):
		"""runs the input filter, the core, and the output filter and returns a
		deferred firing an adapted result table.

		The adapted result table has an additional method getInput returning the
		processed input data.
		"""
		queryMeta = common.QueryMeta(rawInput)
		inputData = self._getInputData(rawInput)
		return self._runCore(inputData, queryMeta).addCallback(
			self._postProcess, queryMeta).addErrback(
			lambda failure: failure).addCallback(
			CoreResult, inputData, rawInput).addErrback(
			lambda failure: failure)
