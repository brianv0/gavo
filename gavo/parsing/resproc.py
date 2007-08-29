"""
CURRENTLY SUSPENDED.  This isn't currently used (for lack of a use case)
and has not been updated to reflect severe architectural changes.

This module contains resource processors and their infrastructure.
"""

from gavo import utils

class Error(Exception):
	pass


class ResourceProcessor:
	"""is an abstract base class vor resource processors.

	Resource processors run when all data belonging to a resource
	has been parsed and the semantics actions have been applied
	(i.e. everything in the rows has the correct type).  They *may*
	change the resource in any way the resource permits (including
	creating new datasets).  However, a resource processor should
	clearly document if it does more than change values in individual
	rows.

	This latter task is expected to be typical: link various data
	sets (e.g., column labels and rows, or notes and rows) together,
	resolve names, etc.

	Since there's not very much we can predict of this kind of task,
	the interface is rather generic: you call defineArgument(key,
	value), and you call the whole thing with your resource as
	argument -- this will call the child's _execute method with
	the resource as the first argument and the keyword arguments
	collected through defineArgument.
	"""
	def __init__(self):
		self.argDict = {}

	@staticmethod
	def getName():
		return "Uncallable abstract resource processor"

	def addArgument(self, key, src, value):
		if src!=None:
			raise Error("Resource Processor arguments cannot have a src.")
		self.argDict[key.encode("ascii")] = value
	
	def __call__(self, resource):
		self._execute(resource, **self.argDict)


class FieldnameResolver(ResourceProcessor):
	"""is a resource processor that replaces field indices with field names.

	To do that, it needs: The name of the target dataset and the target column
	index, and the name of the dataset we want to resolve names in.

	This is typically used to replace field indices in column documentation
	with the names of the fields.
	
	NOTE: This is usually *not* useful since the column indices in
	the original sources will probably not match our column indices when we
	have macros, and we have macros whenever there's positions involved.
	Use @-references in field names instead.
	"""
	@staticmethod
	def getName():
		return "resolveFieldnames"

	def _execute(self, resource, targetId, targetField, srcId):
		targetCol = resource.getDatasetById(targetId).getRecordDef(
			).getFieldIndex(targetField)
		fieldDefs = resource.getDatasetById(srcId).getRecordDef().get_items()
		try:
			for row in resource.getDatasetById(targetId):
				row[targetCol] = fieldDefs[int(row[targetCol])].get_dest()
		except IndexError:
			raise Error("Invalid column index while resolving field names"
				" in %s for %s in %s"%(srcId, row, targetId))


class FielddocBuilder(ResourceProcessor):
	"""is a resource processor that creates a new dataset from DataField
	metadata and possibly information from other datasets.

	Right now, this is tailored to the use case of adding the data description
	from another table.  I hope we can extend this to cover other use
	cases as they come up.
	"""
	@staticmethod
	def getName():
		return "buildFielddoc"
	
	def _makeFielddocDataset(self, newId):
		"""creates a data set to hold column descriptions for tabular data.

		The schema itself will probably be reflected in query interfaces,
		so it's constant and there's no point abstracting here.  If we want
		to make this flexible, the schema has to go to a place where query
		interfaces can see it.

		Right now, it copies all relevant data from the field definition
		of the argument srcId (default: main) and stores the resulting
		table in newTableId (default: fielddoc).  Then it checks all other
		arguments.  Their names are used as the names of the fields in
		the target table, their values as strings containing id.fieldname;
		values of the source fields are copied into the target field.

		This basically is some crooked sort of join with the source table(s).

		Currently hardcoded assumption: The field name is the primary
		key of the source table(s).
		"""
		recordDef = resource.RecordDef()
		recordDef.addto_items(
			DataField(name="type", type="str", length=None, primary=True))
		recordDef.addto_items(
			DataField(name="length", type="int"))
		recordDef.addto_items(
			DataField(name="ucd", type="str", length=None))
		recordDef.addto_items(
			DataField(name="unit", type="str", length=None))
		recordDef.addto_items(
			DataField(name="description", type="str", length=None))
		return resource.DataSet(recordDef)

	def _getDataFromMainSource(self, newDataset, srcDataset):
		"""fills rows with the field data from srcDataset.
		"""
		for fieldDef in srcDataset.getFieldDefs():
			rowDict = {}
			for targetField in newDataset.getFieldDefs():
				rowDict[targetField.get_dest()] = fieldDef.get(
					targetField.get_dest())

	def _parseOtherSources(self, srcDict):
		"""returns a list of triples (srcDatasetId, srcFieldname, targetFieldname)
		for sources added through kwargs.
		"""
		srcs = []
		for targetName, srcSpec in srcDict:
			srcId, srcField = srcSpec.split(".")
			srcs.append((srcId, srcField, targetName))
		return srcs

	def _getDataFromOtherSources(self, resource, newDataset, sources):
		for srcId, srcFieldname, targetFieldname in sources:
			srcDs = self.getDatasetById(srcId)
			srcIndex = srcDs.getRecordDef().getFieldIndex(srcFieldname)
			targetIndex = newDataset.getRecordDef().getFieldIndex(targetFieldname)
			for row in newDataset:
				row[targetIndex] = srcDs.getRow(row[0])

	def _execute(self, resource, newTableId="fielddoc", srcId="main",
			**kwargs):
		raise gavo.Error("OBSOLETE -- adapt to meta table & Co")
		newDataset = self._makeFielddocDataset(newTableId)
		self._getDataFromMainSource(newDataset, 
			resource.getDatasetById(srcId))
		self._getDataFromOtherSources(resource, newDataset,
			self._parseOtherSources(kwargs))
		resource.addDataset(newDataset)


class DatasetRemover(ResourceProcessor):
	"""is a resource processor that removes temporary datasets.

	To do that, it needs the id of the dataset.

	This is typically used to remove datasets not going into the database
	after picking any relevant information out of them.
	"""
	@staticmethod
	def getName():
		return "removeDataset"

	def _execute(self, resource, id):
		resource.removeDataset(id)


getResproc = utils.buildClassResolver(ResourceProcessor, globals().values())
