"""
A grammar that just splits the source into input lines and then
lets you name character ranges.
"""

import re

from gavo import base
from gavo import rscdef
from gavo.grammars.common import Grammar, FileRowIterator


class REIterator(FileRowIterator):
	"""is an iterator based on regular expressions.
	"""
	chunkSize = 8192

	def _iterInRecords(self):
		curPos = 0
		splitPat = self.grammar.recordSep
		buffer = ""
		while True:
			mat = splitPat.search(buffer, curPos)
			if not mat:  # no match, fetch new stuff.
				newStuff = self.inputFile.read(self.chunkSize)
				if not newStuff:  # file exhausted
					break
				buffer = buffer[curPos:]+newStuff
				curPos = 0
				continue
			res = buffer[curPos:mat.end()]
			yield res
			curPos = mat.end()
			self.curLine += res.count("\n")
		# yield stuff left if there's something left
		res = buffer[curPos:]
		if res.strip():
			yield res

	def _iterRows(self):
		for rawRec in self._iterInRecords():
			res = self._makeRec(rawRec)
			res["parser_"] = self
			yield res
		self.inputFile.close()
		self.grammar = None
	
	def _makeRec(self, inputLine):
		return dict(zip(self.grammar.names, self.grammar.fieldSep.split(
			inputLine)))

	def getLocator(self):
		return "%s, line %d"%(self.sourceToken, self.curLine)


class REAttribute(base.UnicodeAttribute):
	"""is an attribute a (compiled) RE
	"""
	def parse(self, value):
		try:
			return re.compile(value)
		except re.error, msg:
			raise base.LiteralParseError("Bad Regexp: '%s' (%s)"%(
				value, unicode(msg)), self.name_, value)
	
	def unparse(self, value):
		return value.pattern


class REGrammar(Grammar):
	"""is a grammar that builds rowdicts from records and field specified
	via REs separating them.
	"""
	name_ = "reGrammar"

	rowIterator = REIterator

	_recordSep = REAttribute("recordSep", default=re.compile("\n"), 
		description="RE for separating two records in the source.")
	_fieldSep = REAttribute("fieldSep", default=re.compile(r"\s+"), 
		description="RE for separating two fields in a record.")
	_names = base.StringListAttribute("names", description=
		"Names for the parsed columns, in sequence of the particles")


rscdef.registerGrammar(REGrammar)
