"""
A grammar that just splits the source into input lines and then
exposes the fields as character ranges.
"""

import gavo
from gavo import utils
from gavo.parsing import grammar



class ColumnExtractor:
	"""
	>>> c = ColumnExtractor("1234567890123456789 ")
	>>> c["1"]
	'1'
	>>> c["2-4"]
	'234'
	>>> c["18-30"]
	'89'
	>>> print c["20"]
	None
	>>> c["foo"] = 20
	>>> c["foo"]
	20
	"""
	def __init__(self, row):
		self.row = row
		self.precomputed = {}

	def __str__(self):
		return "<<%s>>"%self.row
	
	def __repr__(self):
		return str(self)

	def __getitem__(self, indexSpec):
		try:
			if indexSpec in self.precomputed:
				return self.precomputed[indexSpec]
			if "-" in indexSpec:
				start, end = [int(s) for s in indexSpec.split("-")]
				val = self.row[start-1:end].strip()
			else:
				val = self.row[int(indexSpec)-1].strip()
			self.precomputed[indexSpec] = val or None
			return val or None
		except (IndexError, ValueError):
			raise KeyError(indexSpec)

	def get(self, key, default=None):
		try:
			val = self[key]
		except KeyError:
			val = default
		return val

	def __setitem__(self, key, value):
		self.precomputed[key] = value


class ColumnGrammar(grammar.Grammar):
	"""is a grammar has character ranges like 10-12 as row preterminals.

	These never call any documentHandler (use REGrammars if you need
	this).	You can, however, ignore a couple of lines at the head.

	The row production of these grammars always is just a (text) line.

	_iterRows will return magic objects.  These magic object return
	row[start-1:end] if asked for the item "<start>:<end>".  They will
	return None if the matched string is empty.  Otherwise, they
	behave like rowdicts should (i.e., you can set values).
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"topIgnoredLines": 0,
			"booster": None,
			"local": utils.BooleanField,
		})

	def _iterRows(self):
		for i in range(int(self.get_topIgnoredLines())):
			self.inputFile.readline()
		while True:
			ln = self.inputFile.readline()
			if not ln:
				break
			yield ColumnExtractor(ln[:-1])

	def _getDocumentRow(self):
		return {}


def _test():
	import doctest, columngrammar
	doctest.testmod(columngrammar)


if __name__=="__main__":
	_test()
