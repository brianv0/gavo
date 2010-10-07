"""
A grammar splitting the input file into lines and lines into records
using REs.
"""

import re

from gavo import base
from gavo.grammars.common import Grammar, FileRowIterator, REAttribute


class REIterator(FileRowIterator):
	"""is an iterator based on regular expressions.
	"""
	chunkSize = 8192

	def _iterInRecords(self):
		for i in range(self.grammar.topIgnoredLines):
			self.inputFile.readline()
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
			yield res.strip()
			curPos = mat.end()
			self.curLine += res.count("\n")
		# yield stuff left if there's something left
		res = buffer[curPos:].strip()
		if res:
			yield res

	def _iterRows(self):
		for rawRec in self._iterInRecords():
			res = self._makeRec(rawRec)
			res["parser_"] = self
			yield res
		self.inputFile.close()
		self.grammar = None
	
	def _makeRec(self, inputLine):
		if self.grammar.recordCleaner:
			cleanMat = self.grammar.recordCleaner.match(inputLine)
			if not cleanMat:
				raise base.SourceParseError("'%s' does not match cleaner"%inputLine)
			inputLine = " ".join(cleanMat.groups(), source=str(self.sourceToken))
		return dict(zip(self.grammar.names, self.grammar.fieldSep.split(
			inputLine)))

	def getLocator(self):
		return "line %d"%self.curLine


class REGrammar(Grammar):
	"""A grammar that builds rowdicts from records and fields specified
	via REs separating them.
	"""
	name_ = "reGrammar"

	rowIterator = REIterator

	_til = base.IntAttribute("topIgnoredLines", default=0, description=
		"Skip this many lines at the top of each source file.")
	_recordSep = REAttribute("recordSep", default=re.compile("\n"), 
		description="RE for separating two records in the source.")
	_fieldSep = REAttribute("fieldSep", default=re.compile(r"\s+"), 
		description="RE for separating two fields in a record.")
	_recordCleaner = REAttribute("recordCleaner", default=None,
		description="A regular expression matched against each record."
			" The matched groups in this RE are joined by blanks and used"
			" as the new pattern.  This can be used for simple cleaning jobs;"
			" However, records not matching recordCleaner are rejected.")
	_names = base.StringListAttribute("names", description=
		"Names for the parsed columns, in sequence of the fields.")
	_gunzip = base.BooleanAttribute("gunzip", description="Unzip sources"
		" while reading?", default=False)
