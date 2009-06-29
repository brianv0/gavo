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


class VOTNameMaker(object):
	"""A class for generating db-unique names from VOTable fields.
	"""
	def __init__(self):
		self.knownNames, self.index = set(), 0
	
	def makeName(self, field):
		preName = re.sub("[^\w]+", "x", (field.name or field.id or 
			"field%02d"%self.index))
		while preName.lower() in self.knownNames:
			preName = preName+"_"
		self.knownNames.add(preName.lower())
		self.index += 1
		return preName


class VOTableRowIterator(common.RowIterator):
	def __init__(self, grammar, sourceToken, **kwargs):
		common.RowIterator.__init__(self, grammar, sourceToken, **kwargs)
		self.vot = VOTable.parse(sourceToken)

	def _iterRows(self):
		srcTable = self.vot.resources[0].tables[0]
		nameMaker = VOTNameMaker()
		fieldNames = [nameMaker.makeName(f) for f in srcTable.fields]
		for row in srcTable.data:
			yield dict(izip(fieldNames, row))
		self.grammar = None

	def getLocator(self):
		return "VOTable file %s"%self.sourceToken


class VOTableGrammar(common.Grammar):
	"""A grammar parsing from VOTables.

	Currently, the PARAM fields are ignored, only the data rows are
	returned.

	voTableGrammars result in typed records, i.e., values normally come
	in in the types they are supposed to have (with obvious exceptions;
	e.g., VOTables have no datetime type.
	"""
	name_ = "voTableGrammar"
	rowIterator = VOTableRowIterator

rscdef.registerGrammar(VOTableGrammar)
