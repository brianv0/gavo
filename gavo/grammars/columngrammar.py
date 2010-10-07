"""
A grammar that just splits the source into input lines and then
lets you name character ranges.
"""

from gavo import base
from gavo.grammars.common import Grammar, FileRowIterator


class SplitLineIterator(FileRowIterator):
	def __init__(self, grammar, sourceToken, **kwargs):
		FileRowIterator.__init__(self, grammar, sourceToken, **kwargs)
		for i in range(self.grammar.topIgnoredLines):
			self.inputFile.readline()
		self.lineNo = self.grammar.topIgnoredLines+1

	def _iterRows(self):
		while True:
			inputLine = self.inputFile.readline()
			if not inputLine:
				break
			res = self._parse(inputLine)
			res["parser_"] = self
			yield res
			self.lineNo += 1
			self.recNo += 1
		self.inputFile.close()
		self.grammar = None
	
	def _parse(self, inputLine):
		res = {}
		try:
			for key, slice in self.grammar.colRanges.iteritems():
				res[key] = inputLine[slice].strip()
		except IndexError:
			raise base.ui.logOldExc(base.SourceParseError("Short line", inputLine, 
				self.getLocator(), self.sourceToken))
		return res

	def getLocator(self):
		return "line %d"%self.lineNo


class ColRangeAttribute(base.UnicodeAttribute):
	"""A range of indices.

	Ranges can be specified as either <int1>-<int2>, just <int>
	(which is equivalent to <int>-<int>), or as half-open ranges 
	(<int>- or -<int>) Ranges are, contrary to
	python slices, inclusive on both sides, and start counting
	from one.
	"""
	def parse(self, value):
		try:
			if "-" in value:
				startLit, endLit = value.split("-")
				start, end = None, None
				if startLit.strip():
					start = int(startLit)-1
				if endLit.strip():
					end = int(endLit)
				return slice(start, end)
			else:
				col = int(value)
				return slice(col-1, col)
		except ValueError:
			raise base.ui.logOldExc(
				base.LiteralParseError("colRanges", val, hint="A column range,"
				" (either int1-int2 or just an int) is expected here."))


class ColumnGrammar(Grammar):
	"""A grammar that builds rowdicts out of character index ranges.

	This works by using the colRanges attribute like <col key="mag">12-16</col>,
	which will take the characters 12 through 16 inclusive from each input
	line to build the input column mag.
	"""
	name_ = "columnGrammar"

	_til = base.IntAttribute("topIgnoredLines", default=0, description=
		"Skip this many lines at the top of each source file.")
	_cols = base.DictAttribute("colRanges", description="Mapping of"
		" source keys to column ranges.", itemAttD=ColRangeAttribute("col"))
	_gunzip = base.BooleanAttribute("gunzip", description="Unzip sources"
		" while reading?", default=False)
	
	rowIterator = SplitLineIterator
