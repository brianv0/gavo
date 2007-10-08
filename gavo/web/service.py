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

from twisted.internet import defer

from gavo import record
from gavo import table
from gavo import datadef
from gavo import table
from gavo.parsing import resource
from gavo.parsing import meta
from gavo.web import runner


class Service(record.Record, meta.MetaMixin):
	"""is a model for a service.

	It contains:

	 * a list of Adapter instances for input (inputFilters)
	 * a dict mapping output ids to pairs of adapters and names of tables
	   within those adapters.
	 * a Data instance as the core.
	
	The inputFilters are processed sequentially, while only exactly one of
	the outputs is selected when a service runs.

	The first inputFilter must have a getInputFields method that returns
	a sequence of datadef.DataField instances describing what input it
	requries.
	"""
# XXX TODO: We only use the first item of the inputFilters.
# Either implement filter chaining or rebuild to allow only one
# input filter.
	def __init__(self, initvals):
		record.Record.__init__(self, {
			"inputFilters": record.ListField,
			"output": record.DictField,
			"core": record.RequiredField,
			"id": record.RequiredField,
		}, initvals)

	def register_output(self, key, value):
		# the first key added becomes the default.
		if not self.dataStore["output"]:
			self.dataStore["output"]["default"] = value
		else:
			self.dataStore["output"][key] = value

	def getInputFields(self):
		return self.get_inputFilters()[0].getInputFields()
	
	def _getInputData(self, inputData):
		dD = self.get_inputFilters()[0]
		curData = resource.InternalDataSet(dD, table.Table, inputData)
		return curData

	def _runCore(self, inputTable):
		core = self.get_core()
		if not core.get_computer():
			raise gavo.Error("Can only run executable cores yet.")
		return runner.run(core, inputTable)

	def _parseResult(self, input, outputFilter):
		"""sends the result of the core process through the core parser and
		the output filter, returning a result table.

		input must match core's grammar, i.e. needs to be a string for 
		text-processing grammars.
		"""
		result = resource.InternalDataSet(self.get_core(), table.Table, 
			cStringIO.StringIO(input), tablesToBuild=["output"])
		if outputFilter:
			result = resource.InternalDataSet(self.get_output(outputFilter), 
				result.getTables()[0].getInheritingTable, result)
		return result

	def getResult(self, rawInput, outputFilter=None):
		"""returns a Deferred for the raw output of core.
		"""
		inputData = self._getInputData(rawInput)
		retVal = defer.Deferred()
		data = self._runCore(inputData)
		data.addCallback(lambda res: 
			retVal.callback(self._parseResult(res, outputFilter)))
		data.addErrback(lambda res: retVal.errback(res))
		return retVal
