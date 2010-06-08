"""
Functions for parsing and generating VOTables to and from internal data
representations.

The actual implementations are in two separate modules.  Always access
them through this module.
"""

from gavo.formats.votableread import (makeTableDefForVOTable,
	makeDDForVOTable, uploadVOTable,
	AutoQuotedNameMaker, QuotedNameMaker)
from gavo.formats.votablewrite import (getAsVOTable,
	writeAsVOTable, makeVOTable)
