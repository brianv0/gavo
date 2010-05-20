"""
A grammar taking its rows from a VOTable.
"""

# XXX TODO: return PARAMs as the docrow

import gzip
import re
from itertools import *

from gavo import adql
from gavo import base
from gavo import rscdef
from gavo import votable
from gavo.grammars import common


class VOTNameMaker(object):
	"""A class for generating db-unique names from VOTable fields.

	This is important to avoid all kinds of weird names the remaining
	infrastructure will not handle.  "Normal" TableDefs assume unquoted
	SQL identifiers as names, and want all names unique.

	Using this class ensures these expectations are met in a reproducible
	way (i.e., given the same table, the same names will be assigned).
	"""
	def __init__(self):
		self.knownNames, self.index = self._getNameBlacklist().copy(), 0

	# words not allowed as column names generated for VOTable FIELDs, in addition
	# to python keywords and names used in rscdef.rmkfuncs
	customNameBlacklist = set(["result_", "rowdict_"])

	@classmethod
	def _getNameBlacklist(cls):
		"""returns a set of names not suitable for table column names since
		they would damage rowmakers.
		"""
		if not hasattr(cls, "blacklist"):
			import keyword
			from gavo.rscdef import rmkfuncs
			blacklist = (set(keyword.kwlist)
				| set(dir(rmkfuncs))
				| cls.customNameBlacklist
				| adql.allReservedWords)
			cls.blacklist = blacklist
		return cls.blacklist

	def makeName(self, field):
		preName = re.sub("[^\w]+", "x", (getattr(field, "a_name", None) 
			or getattr(field, "a_ID", None)
			or "field%02d"%self.index))
		if not re.match("[A-Za-z_]", preName):
			preName = "col_"+preName
		while preName.lower() in self.knownNames:
			preName = preName+"_"
		self.knownNames.add(preName.lower())
		self.index += 1
		return preName


class VOTableRowIterator(common.RowIterator):
	"""An iterator returning rows of the first table within a VOTable.
	"""
	def __init__(self, grammar, sourceToken, **kwargs):
		common.RowIterator.__init__(self, grammar, sourceToken, **kwargs)
		if self.grammar.gunzip:
			inF = gzip.open(sourceToken)
		else:
			inF = sourceToken
		self.rowSource = votable.parse(inF).next()

	def _iterRows(self):
		nameMaker = VOTNameMaker()
		fieldNames = [nameMaker.makeName(f) 
			for f in self.rowSource.tableDefinition.
					iterChildrenOfType(votable.V.FIELD)]
		for row in self.rowSource:
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
	_gunzip = base.BooleanAttribute("gunzip", description="Unzip sources"
		" while reading?", default=False)

	rowIterator = VOTableRowIterator

rscdef.registerGrammar(VOTableGrammar)
