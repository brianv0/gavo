"""
A grammar using python's csv module to parse files.
"""

from __future__ import with_statement

import csv

from gavo import base
from gavo import utils
from gavo.grammars.common import Grammar, FileRowIterator, FileRowAttributes


class CSVIterator(FileRowIterator):
	def __init__(self, grammar, sourceToken, **kwargs):
		FileRowIterator.__init__(self, grammar, sourceToken, **kwargs)
		self.csvSource = csv.DictReader(self.inputFile,
			delimiter=str(self.grammar.delimiter))

	def _iterRows(self):
		return self.csvSource

	def getLocator(self):
		return "FIXME"


class CSVGrammar(Grammar, FileRowAttributes):
	"""A grammar that uses python's csv module to parse files.
	"""
	name_ = "csvGrammar"

	_delimiter = base.UnicodeAttribute("delimiter", 
		description="CSV delimiter", default=",")
		
	rowIterator = CSVIterator
