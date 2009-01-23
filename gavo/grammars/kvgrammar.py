"""
This module contains code for using key value pairs from plain text files
for data parsing.
"""

import re

from gavo import base
from gavo import rscdef
from gavo.grammars.common import Grammar, FileRowIterator, MapKeys


class KVIterator(FileRowIterator):
	"""is an iterator over a file containing key, value pairs.

	Depending on the parent grammar, it returns the whole k,v record as
	one row or one pair per row.
	"""
	def _iterRows(self):
		data = self.inputFile.read()
		completeRecord = {"parser_": self}
		data = re.sub(self.grammar.compiledComment, "", data)
		items = {}
		for rec in self.grammar.recSplitter.split(data):
			try:
				if rec.strip():
					key, value = self.grammar.pairSplitter.match(rec).groups()
					if self.grammar.yieldPairs:
						yield {"key": key.strip(), "value": value.strip(), "parser_": self}
					else:
						completeRecord[key.strip()] = value.strip()
			except:
				self.inputFile.close()
				raise base.SourceParseError("Not a key value pair: %s"%(
					repr(rec)))
		if not self.grammar.yieldPairs:
			yield self.grammar.mapKeys.doMap(completeRecord)
		self.inputFile.close()

	def getLocator(self):
		return self.sourceToken


class KeyValueGrammar(Grammar):
	"""models a grammar for key-value pairs, one record per file.

	The default assumes one pair per line, with # comments and = as
	separating character.

	yieldPairs makes the grammar return an empty docdict
	and {"key":, "value":} rowdicts.

	Whitespace around key and value is ignored.
	"""
	name_ = "keyValueGrammar"
# XXX TODO: Make these REAttributes
	_kvSeps = base.UnicodeAttribute("kvSeparators", default=":=",
		description="Characters accepted as separators between key and value")
	_pairSeps = base.UnicodeAttribute("pairSeparators", default="\n",
		description="Characters accepted as separators between pairs")
	_cmtPat = base.UnicodeAttribute("commentPattern", default="(?m)#.*",
		description="A RE describing comments.")
	_yieldPairs = base.BooleanAttribute("yieldPairs", default=False,
		description="Yield key-value pairs instead of complete records?")
	_mapKeys = base.StructAttribute("mapKeys", childFactory=MapKeys,
		default=None)

	rowIterator = KVIterator

	def onElementComplete(self):
		self.recSplitter = re.compile("[%s]"%self.pairSeparators)
		self.pairSplitter = re.compile("([^%s]+)[%s](.*)"%(
			self.kvSeparators, self.kvSeparators))
		self.compiledComment = re.compile(self.commentPattern)
		if self.mapKeys is None:
			self.mapKeys = base.makeStruct(MapKeys)
		self._onElementCompleteNext(KeyValueGrammar)


rscdef.registerGrammar(KeyValueGrammar)
