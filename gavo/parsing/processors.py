""" 
This module contains row processors and their infrastructure.

A row processor is some python code that takes a right row after parsing
and produces zero or more new rows from it that are then either processed
by other row processors or added to a row set.

On NULL arguments, RowProcessors should, as a rule, fail.
"""

import datetime

from mx import DateTime

from gavo import utils
from gavo.parsing import parsehelpers

class RowProcessor(parsehelpers.RowFunction):
	"""is an abstract base class for all row processors.
	"""
	pass


class RowExpander(RowProcessor):
	"""is a row processor that produces copies of rows.

	The idea is that sometimes rows have specifications like "Star 10
	through Star 100".  These are a pain if untreated.  A RowExpander
	could create 90 individual rows from this.

	A RowExpander has three arguments: The names of the nonterminals
	giving the beginning and the end of the range, and the name of
	the nonterminal that the new index should be assigned to.
	"""
	@staticmethod
	def getName():
		return "expandRow"
	
	def _compute(self, record, lowerInd, upperInd, fieldName):
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


class DateExpander(RowProcessor):
	"""is a row processor to expand time ranges.

	The finished dates are left in destination as mxDateTime.Timestamp
	instances, i.e., you'll usually want these fields with a "do not touch"
	literal form.

	Dates can be given in any format supported by mxDateTime.Parse

	Constructor Argument:

	* destination -- name of the field we're writing into.

	Arguments:

	* start -- the start date
	* end -- the end date
	* hrInterval -- a float literal specifying how many hours should be between
	  the generated timestamps
	>>> m = DateExpander([("start", "start", ""), ("end", "end", ""),
	...  ("hrInterval", "", "24")], destination="genDate")
	>>> r = {"start": "1067-10-1", "end": "1067-10-3"}
	>>> m(None, r); r
	"""
	@staticmethod
	def getName():
		return "expandDateRange"
	
	def __init__(self, argTuples=[], destination="genDate"):
		RowProcessor.__init__(self, argTuples)
		self.destination = destination

	def _mkDateTime(self, val):
		if isinstance(val, basestring):
			val = DateTime.Parser.DateTimeFromString(val)
		if isinstance(val, datetime.datetime):
			val = DateTime.DateTime(val.year, val.month, val.day, 
				val.hour, val.minute, val.second)
		if isinstance(val, datetime.date):
			val = DateTime.DateTime(val.year, val.month, val.day)
		return val

	def _compute(self, record, start=None, end=None, hrInterval=24):
		stampTime = self._mkDateTime(start)
		endTime = self._mkDateTime(end)
		interval = DateTime.TimeDelta(hours=float(hrInterval))
		while stampTime<=endTime:
			newRec = record.copy()
			newRec[self.destination] = stampTime
			yield newRec
			stampTime = stampTime+interval


getProcessor = utils.buildClassResolver(RowProcessor, globals().values())
