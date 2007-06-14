""" 
This module contains row processors and their infrastructure.

A row processor is some python code that takes a right row after parsing
and produces zero or more new rows from it that are then either processed
by other row processors or added to a row set.
"""

from gavo import utils
from gavo.parsing import parsehelpers

class RowProcessor(parsehelpers.RowFunction):
	"""is an abstract base class for all row processors.
	"""
	def __call__(self, record):
		return self._makeRecords(record, **self._buildArgDict(record))


class RowExpander(RowProcessor):
	"""is a row processor that produces copies of rows.

	The idea is that sometimes rows have specifications like Star 10
	through Star 100.  These are a pain if untreated.  A RowExpander
	could create 90 individual rows from this.

	A RowExpander has three arguments: The names of the nonterminals
	giving the beginning and the end of the range, and the name of
	the nonterminal that the new index should be assigned to.
	"""
	@staticmethod
	def getName():
		return "expandRow"
	
	def _makeRecords(self, record, lowerInd, upperInd, fieldName):
		try:
			lowerInd = int(lowerInd)
			upperInd = int(upperInd)
		except (ValueError, TypeError): # either one not given
			return [record]
		res = []
		for ind in range(lowerInd, upperInd+1):
			newRec = record.copy()
			newRec[fieldName] = ind
			res.append(newRec)
		return res


getProcessor = utils._buildClassResolver(RowProcessor, globals().values())
