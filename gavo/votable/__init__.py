"""
GAVO's VOTable python library.
"""

from gavo.votable.coding import unravelArray

from gavo.votable.common import VOTableError

from gavo.votable.model import VOTable as V, voTag

from gavo.votable.parser import parse, parseString, readRaw

from gavo.votable.simple import open

from gavo.votable.tablewriter import DelayedTable, write, asString

from gavo.votable.tapquery import ADQLTAPJob
