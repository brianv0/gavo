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

from twisted.internet import defer
from twisted.python import components

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
		self.setMetaParent(self.rd)
		record.Record.__init__(self, {
			"inputFilter": None,
			"output": record.DictField,
			"core": record.RequiredField,
			"id": record.RequiredField,
			"template": record.DictField,
# temporary hack: map field names to ones known to the form.
			"fieldNameTranslations": None,   
		}, initvals)

	def _getDefaultInputFilter(self):
		"""returns an input filter from a web context implied by the service.
		"""
		# XXX TODO: id and table name is not unique, ask rd for an id.
		if not hasattr(self, "_defaultInputFilter"):
			coreFields = self.get_core().getInputFields()
			self._defaultInputFilter = datadef.DataTransformer(self.rd,
				initvals={
					"Grammar": contextgrammar.ContextGrammar(initvals={
							"inputKeys": coreFields,
						}),
					"Semantics": resource.Semantics(initvals={
							"recordDefs": [resource.RecordDef(initvals={
								"table": "NULL",
								})]
						}),
					"id": "<generated>", 
					"items": coreFields,
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

	def translateFieldName(self, name):
		"""returns a field name present in the input for a field name
		that may only have been introduced in later processing stages.
		"""
		if self.get_fieldNameTranslations():
			return self.get_fieldNameTranslations().get(name, name)
		return name

	def getInputFields(self):
		return self.get_inputFilter().getInputFields()
	
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

	def getOutputFields(self, queryMeta):
		"""returns a sequence of DataField instances matching the output table
		if known, or None otherwise.

		queryMeta may be none, but then we'll only know the output fields if
		there is not more than one output filter (because these usually change
		output fields).

		This can only be expected to work on database based cores (really, it's
		supposed to be used for a sort-by-type widget).
		"""
		# XXX this function shows there's something fundamentally wrong with my
		# design...  Not sure what to do about it.
		if self.count_output()>1:
			# find out what filter is requested from queryMeta
			if queryMeta:
				filterName = queryMeta["outputFilter"]
				if filterName and self.get_output(filterName):
					outputFilter = self.get_output(filterName)
					return outputFilter.getPrimaryTableDef().get_items()
		else:
			if self.get_output("default"):
				# There is an output filter
				outputFilter = self.get_output("default")
				return outputFilter.getPrimaryTableDef().get_items()
			else:
				# get output fields from core
				if queryMeta==None:
					queryMeta = {"format": "HTML"}
				try:
					return self.get_core().getOutputFields(queryMeta)
				except AttributeError:
					pass

	def run(self, inputData, queryMeta=common.emptyQueryMeta):
		"""runs the input filter, the core, and the output filter and returns a
		deferred firing an adapted result table.

		The adapted result table has an additional method getInput returning the
		processed input data.
		"""
		return self.get_core().run(inputData, queryMeta).addCallback(
			self._postProcess, queryMeta).addErrback(
			lambda failure: failure).addCallback(
			common.CoreResult, inputData, queryMeta).addErrback(
			lambda failure: failure)
