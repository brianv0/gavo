"""
This module contains code for using key value pairs from plain text files
for data parsing.
"""

import re

import gavo
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
	
	def parse(self, parseContext):
		recSplitter = re.compile("[%s]"%self.get_pairSeparators())
		pairSplitter = re.compile("([^%s]+)[%s](.*)"%(
			self.get_kvSeparators(), self.get_kvSeparators()))
		data = parseContext.sourceFile.read()
		re.sub(self.get_commentPattern(), "", data)
		items = {}
		for rec in recSplitter.split(data):
			try:
				if rec.strip():
					key, value = pairSplitter.match(rec).groups()
					items[key.strip()] = value.strip()
			except:
				raise gavo.Error("Not a key value pair in %s: %s"%(
					parseContext.sourceName, repr(rec)))
		self.handleDocdict(items, parseContext)
	
	def enableDebug(self, debugProductions):
		pass
