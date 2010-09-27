"""
A grammar parsing key-value pairs from plain text files.
"""

import re

from gavo import base
from gavo import rscdef
from gavo.grammars.common import Grammar, FileRowIterator, MapKeys, REAttribute


class KVIterator(FileRowIterator):
	"""is an iterator over a file containing key, value pairs.

	Depending on the parent grammar, it returns the whole k,v record as
	one row or one pair per row.
	"""
	def _iterRows(self):
		data = self.inputFile.read()
		if self.grammar.enc:
			data = data.decode(self.grammar.enc)
		completeRecord = {"parser_": self}
		data = re.sub(self.grammar.commentPattern, "", data)
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
				raise base.ui.logOldExc(
					base.SourceParseError("Not a key value pair: %s"%(repr(rec))))
		if not self.grammar.yieldPairs:
			yield self.grammar.mapKeys.doMap(completeRecord)
		self.inputFile.close()

	def getLocator(self):
		return self.sourceToken


class KeyValueGrammar(Grammar):
	"""A grammar to parse key-value pairs from files.

	The default assumes one pair per line, with # comments and = as
	separating character.

	yieldPairs makes the grammar return an empty docdict
	and {"key":, "value":} rowdicts.

	Whitespace around key and value is ignored.
	"""
	name_ = "keyValueGrammar"
	_kvSeps = base.UnicodeAttribute("kvSeparators", default=":=",
		description="Characters accepted as separators between key and value")
	_pairSeps = base.UnicodeAttribute("pairSeparators", default="\n",
		description="Characters accepted as separators between pairs")
	_cmtPat = REAttribute("commentPattern", default=re.compile("(?m)#.*"),
		description="A regular expression describing comments.")
	_yieldPairs = base.BooleanAttribute("yieldPairs", default=False,
		description="Yield key-value pairs instead of complete records?")
	_mapKeys = base.StructAttribute("mapKeys", childFactory=MapKeys,
		default=None, description="Mappings to rename the keys coming from"
		" the source files.  Use this, in particular, if the keys are"
		" not valid python identifiers.")

	rowIterator = KVIterator

	def onElementComplete(self):
		self.recSplitter = re.compile("[%s]"%self.pairSeparators)
		self.pairSplitter = re.compile("([^%s]+)[%s](.*)"%(
			self.kvSeparators, self.kvSeparators))
		if self.mapKeys is None:
			self.mapKeys = base.makeStruct(MapKeys)
		self._onElementCompleteNext(KeyValueGrammar)


rscdef.registerGrammar(KeyValueGrammar)
