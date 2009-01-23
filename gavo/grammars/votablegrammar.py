"""
A grammar taking its rows from a VOTable.
"""

# XXX TODO: return PARAMs as the docrow

import re
from itertools import *

from gavo import base
from gavo import rscdef
from gavo.grammars import common
from gavo.imp import VOTable


def makeVOTableFieldName(field, ind):
	"""returns a suitable column name for a VOTable field structure.
	"""
	return re.sub("[^\w]+", "x", (field.name or field.id or "field%02d"%ind))


class VOTableRowIterator(common.RowIterator):
	def __init__(self, grammar, sourceToken, **kwargs):
		common.RowIterator.__init__(self, grammar, sourceToken, **kwargs)
		self.vot = VOTable.parse(sourceToken)

	def _iterRows(self):
		srcTable = self.vot.resources[0].tables[0]
		fieldNames = [makeVOTableFieldName(f, ind)
			for ind, f in enumerate(srcTable.fields)]
		for row in srcTable.data:
			yield dict(izip(fieldNames, row))
		self.grammar = None

	def getLocator(self):
		return "VOTable file %s"%self.sourceToken


class VOTableGrammar(common.Grammar):
	name_ = "voTableGrammar"
	rowIterator = VOTableRowIterator

rscdef.registerGrammar(VOTableGrammar)
