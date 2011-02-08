"""
Wrinting data in CSV.
"""

import csv

from gavo import base
from gavo import rsc
from gavo.formats import common


def _encodeRow(row):
	"""return row with everything that's a unicode object turned into a
	utf-8 encoded string.
	"""
	res = []
	for val in row:
		if isinstance(val, unicode):
			res.append(val.encode("utf-8"))
		else:
			res.append(val)
	return res


def writeDataAsCSV(table, target, acquireSamples=True,
		dialect=base.getConfig("async", "csvDialect"), headered=False):
	"""writes table to the file target in CSV.

	The CSV format chosen is controlled through the async/csvDialect
	config item.
	"""
	if isinstance(table, rsc.Data):
		table = table.getPrimaryTable()
	sm = base.SerManager(table, acquireSamples=acquireSamples)
	writer = csv.writer(target, dialect)
	if headered:
		writer.writerow([c["name"] for c in sm])
	for row in sm.getMappedTuples():
		try:
			writer.writerow(_encodeRow(row))
		except UnicodeEncodeError:
			writer.writerow(row)
	

def writeDataAsHeaderedCSV(table, target, acquireSamples=True):
	return writeDataAsCSV(table, target, headered=True,
		acquireSamples=acquireSamples)

# NOTE: This will only serialize the primary table
common.registerDataWriter("csv", writeDataAsCSV, "text/csv")
common.registerDataWriter("csv+header", 
	lambda table, target, **kwargs: 
		writeDataAsCSV(table, target, headered=True, **kwargs),
	"text/csv;header=present")
