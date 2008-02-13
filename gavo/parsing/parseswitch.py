"""
Code that abstracts the parsing process.

Well, actually, this module is almost obsolete now.  It used to hold an
incredibly obtuse version of the booster system, which is why a bit of
the table selection still is here.
"""

import os
import sys

import gavo
from gavo import config
from gavo import table
from gavo.parsing import columngrammar
from gavo.parsing import parsehelpers
from gavo.parsing import resource


def parseSource(parseContext):
	"""actually executes the parse process described by parseContext.
	"""
# I had once planned to teach the special tricks for unusual parsing
# processes here.  However, it turns out that this is better handled
# the grammars and the tables.  Thus, this is largely a no-op and should
# probably go away.
	parseContext.parse()


def FreshDirectWritingTable(*args, **kwargs):
	"""is a factory for DirectWritingTables that have dropIndices=1.
	"""
	return table.DirectWritingTable(dropIndices=True, *args, **kwargs)

def getTableClassForRecordDef(recordDef):
	if recordDef.get_onDisk():
		if recordDef.get_forceUnique():
			raise gavo.Error(
				"Tables can't be onDisk and forceUnique at the same time.")
		TableClass = FreshDirectWritingTable
	elif recordDef.get_forceUnique():
		TableClass = table.UniqueForcedTable
	else:
		TableClass = table.Table
	return TableClass

def createTable(dataSet, recordDef):
	return getTableClassForRecordDef(recordDef)(dataSet, recordDef)
