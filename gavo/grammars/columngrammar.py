"""
A grammar that just splits the source into input lines and then
lets you name character ranges.
"""

from gavo import base
from gavo import rscdef
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
			base.ui.notifyIncomingRow(res)
			yield res
			self.lineNo += 1
			self.recNo += 1
		self.inputFile.close()
		self.grammar = None
	
	def _parse(self, inputLine):
		res = {}
		try:
			for key, (start, end) in self.grammar.colRanges.iteritems():
				res[key] = inputLine[start:end].strip()
		except IndexError:
			raise base.SourceParseError("Short line", inputLine, 
				self.getLocator())
		return res

	def getLocator(self):
		return "%s, line %d"%(self.sourceToken, self.lineNo)


class ColRangeAttribute(base.UnicodeAttribute):
	"""is an attribute holding a range of indices.

	They can be specified as either <int>-<int> or just <int>.  Ranges are,
	contrary to python slices, inclusive on both sides, and start counting
	from one.
	"""
	def parse(self, value):
		try:
			if "-" in value:
				start, end = map(int, value.split("-"))
				return start-1, end
			else:
				col = int(value)
				return col-1, col
		except ValueError:
			raise base.LiteralParseError("Bad column range: %s"%val,
				"colRanges", val)


class ColumnGrammar(Grammar):
	"""is a grammar that builds rowdicts out of column specifications.

	This works by using the colRanges attribute like <col key="mag">12-16</col>
	"""
	name_ = "columnGrammar"

	_til = base.IntAttribute("topIgnoredLines", default=0, description=
		"Skip this many lines at the top of each source file")
	_cols = base.DictAttribute("colRanges", description="Mapping of"
		" source keys to column ranges", itemAttD=ColRangeAttribute("col"))
	_gunzip = base.BooleanAttribute("gunzip", description="Unzip sources"
		" while reading?", default=False)
	
	rowIterator = SplitLineIterator
	
rscdef.registerGrammar(ColumnGrammar)
