"""
Writing table objects as CSV files.
"""

import csv

from gavo import base
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


def writeDataAsCSV(data, target):
	"""writes data's primary tables to the file target in CSV.

	The CSV format chosen is controlled through the async/csvDialect
	config item.
	"""
	sm = base.SerManager(data.getPrimaryTable())
	writer = csv.writer(target, base.getConfig("async", "csvDialect"))
	for row in sm.getMappedTuples():
		try:
			writer.writerow(_encodeRow(row))
		except UnicodeEncodeError:
			writer.writerow(row)
	

# NOTE: This will only serialize the primary table
common.registerDataWriter("csv", writeDataAsCSV)
