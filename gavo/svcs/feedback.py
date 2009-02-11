"""
Service and core to handle feedback requests.

Feedback services take a query for the base service, but instead of
returning a result data set, they return a dict of vizier expressions
defining ranges or enumerated values for the result set of data set.

For now, this only works with DBCores and the FeedbackForm renderer.
"""

from gavo import base
from gavo import rscdef
from gavo.svcs import common
from gavo.svcs import core
from gavo.svcs import inputdef
from gavo.svcs import outputdef
from gavo.svcs import service
from gavo.svcs import standardcores


class FeedbackCore(standardcores.DBCore):
	"""A special core for producing feedback queries.

	This core can only sensibly be used with the feedback renderer, since
	it returns a dict of vizier expressions covering the ranges (for
	every feedbackable column not enumerated) or values (for enumerated
	columns) for the primary keys given in the input data.

	You usually don't mention a feedback core in your RD explicitely.  If
	you specify a feedbackColumn in your dbCores, the software will set
	up a feedback service itself.
	"""
	name_ = "feedback"

	rangeTypes = frozenset(["vexpr-date", "vexpr-float"])
	enumeratedTypes = frozenset(["vexpr-string"])

	@classmethod
	def fromDBCore(self, core, outputColumns):
		res = FeedbackCore(None)
		res.queriedTable = core.queriedTable
		res.feedbackColumn = core.feedbackColumn
		res.feedObject("inputDD", res._makeInputDD(core))
		res.outputTable = None
		res._makeFeedbackableColumns(outputColumns)
		return res.finishElement()

	def _makeInputDD(self, core):
		resTableDef = base.makeStruct(rscdef.TableDef,
			columns=[inputdef.InputKey.fromColumn(
				standardcores.makeFeedbackColumn(
					core.queriedTable.columns,
					core.feedbackColumn))])
		return base.makeStruct(inputdef.InputDescriptor, 
			makes=[base.makeStruct(rscdef.Make, table=resTableDef)])

	def _makeFeedbackableColumns(self, inputColumns):
		self.rangedCols, self.enumeratedCols = [], []
		for f in inputColumns:
			if f.type in self.rangeTypes and f.name in self.queriedTable.columns:
				self.rangedCols.append(f)
			if (f.type in self.enumeratedTypes and 
					f.name in self.queriedTable.columns):
				self.enumeratedCols.append(f)

	def _makeFunctionColumn(self, column, fct):
		res = column.copy(self)
		res.select = "%s(%s)"%(fct, column.name)
		res.name = "%s_%s"%(fct, column.name)
		return res

	def _getRangeExprs(self, feedbackKeys, queryMeta):
		"""returns a dict containing vizier expressions for the ranges
		of rangeColumns in feedbackKeys.
		"""
		res = {}
		minCols = [self._makeFunctionColumn(c, "MIN") 
			for c in self.rangedCols]
		maxCols = [self._makeFunctionColumn(c, "MAX") 
			for c in self.rangedCols]
		resultTableDef = base.makeStruct(rscdef.TableDef, columns=minCols+maxCols,
			id="ranges")
		if not resultTableDef.columns:
			return res
		minmaxRow = self._runQuery(resultTableDef, 
			"%s IN %%(feedbackKeys)s"%self.feedbackColumn,
			{"feedbackKeys": feedbackKeys},
			queryMeta).rows[0]
		for c in self.rangedCols:
			# for the types we handle here, %s yields vexpr-compatible exprs.
			res[c.name] = "%s .. %s"%(minmaxRow["MIN_"+c.name],
				minmaxRow["MAX_"+c.name])
		return res

	def _getEnumeratedExprs(self, feedbackKeys, queryMeta):
		"""returns vizier expressions enumerating all values found for
		enumeratedColumns within the rows selected by feedbackKeys.
		"""
		res = {}
		for col in self.enumeratedCols:
			resultTableDef = base.makeStruct(rscdef.TableDef, 
				columns=[outputdef.OutputField.fromColumn(col)], id="ranges")
			vals = [str(r[col.name]) for r in self._runQuery(resultTableDef, 
				"%s IN %%(feedbackKeys)s"%self.feedbackColumn,
				{"feedbackKeys": feedbackKeys},
				queryMeta, distinct=True).rows]
			if len(vals)<15: # Ignore field if too many items matched to avoid
					# gargantuous strings
				res[col.name] = "=,%s"%(','.join(vals))
		return res

	def run(self, service, inputData, queryMeta):
		feedbackKeys = inputData.getPrimaryTable().rows[0]["feedbackSelect"] 
		res = self._getRangeExprs(feedbackKeys, queryMeta)
		res.update(self._getEnumeratedExprs(feedbackKeys, queryMeta))
		return res
		
	def _processRanged(self, result, rangeNames, enumeratedNames, feedbackKeys):
		result = result[0]
		rowdict = {}
		for index, n in enumerate(rangeNames):
			rowdict[n] = "%s .. %s"%(result[2*index], result[2*index+1])
		return self._queryEnumerated(rowdict, enumeratedNames, feedbackKeys)

core.registerCore(FeedbackCore)


class FeedbackService(service.Service):
	"""describes a feedback service.

	This is never defined through XML RDs, but is always constructed
	from FeedbackFrom.
	"""
	@classmethod
	def fromService(cls, service):
		res = cls(service.parent)
		res.feedObject("core",
			FeedbackCore.fromDBCore(service.core, service.getInputFields()))
		res.outputTable = None
		return res.finishElement()
