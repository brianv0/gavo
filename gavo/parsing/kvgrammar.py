"""
This module contains code for using key value pairs from plain text files
for data parsing.
"""

import re

from gavo import utils
from gavo.parsing import grammar

class KeyValueGrammar(grammar.Grammar):
	"""models a grammar for key-value pairs, one record per file.

	The default assumes one pair per line, with # comments and = as
	separating character.

	Whitespace around key and value is ignored.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"kvSeparators": ":=",
			"pairSeparators": "\n",
			"commentPattern": "(?m)#.*",
		})
		self.set_docIsRow(True)
	
	def _parse(self, inputFile):
		"""parses the inputFile and returns the parse result as suitable for
		row handlers.
		"""
		recSplitter = re.compile("[%s]"%self.get_pairSeparators())
		pairSplitter = re.compile("([^%s]+)[%s](.*)"%(
			self.get_kvSeparators(), self.get_kvSeparators()))
		data = inputFile.read()
		re.sub(self.get_commentPattern(), "", data)
		items = {}
		for rec in recSplitter.split(data):
			if rec.strip():
				key, value = pairSplitter.match(rec).groups()
				items[key.strip()] = value.strip()
		self.handleDocument(items)
	
	def setRowHandler(self, callable):
		if callable:
			raise Error("KvGrammars can have no row handlers (yet)")
	
	def enableDebug(self, debugProductions):
		pass
