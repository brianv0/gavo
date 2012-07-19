"""
GAVO's VOTable python library.
"""

from gavo.votable.coding import unravelArray

from gavo.votable.common import (VOTableError, VOTableParseError,
	BadVOTableLiteral, BadVOTableData)

# escapeX were part of this package's interface
from gavo.utils.stanxml import (escapePCDATA, escapeAttrVal)

from gavo.votable.model import VOTable as V, voTag

from gavo.votable.parser import parse, parseString, readRaw

from gavo.votable.simple import load, save

from gavo.votable.tablewriter import (
	DelayedTable, OverflowElement, write, asString)

from gavo.votable.tapquery import ADQLTAPJob, ADQLSyncJob
