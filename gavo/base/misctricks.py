"""
Basic code that doesn't really fit into either texttricks or codetricks.
"""

import re


from gavo.base import excs


class NameMap(object):
	"""is a name mapper fed from a simple text file.

	The text file format simply is:

	<target-id> "TAB" <src-id>{whitespace <src-id>}

	src-ids have to be encoded quoted-printable when they contain whitespace
	or other "bad" characters ("="!).  You can have #-comments and empty
	lines.
	"""
	def __init__(self, src, missingOk=False):
		self._parseSrc(src, missingOk)
	
	def __contains__(self, name):
		return name in self.namesDict

	def _parseSrc(self, src, missingOk):
		self.namesDict = {}
		try:
			f = open(src)
		except IOError:
			if not missingOk:
				raise
			else:
				return
		try:
			for ln in f:
				if ln.startswith("#") or not ln.strip():
					continue
				ob, names = re.split("\t+", ln)
				for name in names.lower().split():
					self.namesDict[name.decode("quoted-printable")] = ob
		except ValueError:
			raise excs.LiteralParseError(
				"Syntax error in %s: Line %s not understood."%(src, repr(ln)),
				src, ln)
		f.close()
	
	def resolve(self, name):
		return self.namesDict[name.lower()]
