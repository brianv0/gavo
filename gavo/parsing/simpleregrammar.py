"""
Simple Regexp-based grammars.
"""

import re
import sys

import gavo
from gavo import record
import gavo.parsing
from gavo.parsing import grammar

class Error(gavo.parsing.ParseError):
	pass

class SimpleREGrammar(grammar.Grammar):
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"rowProduction": r"(?m)^.+$\n",
			"parseRE": record.RequiredField,
		})

	def set_rowProduction(self, val):
		self.dataStore["rowProduction"] = re.compile(val.strip())

	def set_parseRE(self, val):
		self.dataStore["parseRE"] = re.compile(val.strip())

	def _getDocdict(self, parseContext):
		return {}

	_onlyWhitespaceLeft = re.compile(r"\s*$")

	def _iterRows(self, parseContext):
		doc = parseContext.sourceFile.read()
		curPos = 0
		rp = self.get_rowProduction()
		pe = self.get_parseRE()
		while 1:
			mat = rp.match(doc, curPos)
			if not mat:
				if self._onlyWhitespaceLeft.match(doc, curPos):
					return
				else:
					raise Error("No record found, position %d, context %s"%(
						curPos, repr(doc[curPos:curPos+20])))
			curPos = mat.end()
			recMat = pe.match(mat.group())
			if not recMat:
				raise Error("Malformed record, position %d, context %s"%(
					curPos, repr(mat.group())))
			yield dict([(str(index+1), content.strip())
				for index, content in enumerate(recMat.groups())])
