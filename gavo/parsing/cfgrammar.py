""" 
This module contains code to handle context free (currently pyparsing)
grammars for data parsing.

CURRENTLY OUT OF ORDER
"""

import re

import gavo
from gavo import utils
from gavo.parsing import grammar


class Error(Exception):
	pass


def flattenAndJoin(nestedStrings):
	'''returns a join of all elements within nestedStrings, possibly flattening
	the structure.
	'''
	res = []
	for tok in nestedStrings:
		if isinstance(tok, list):
			res.append(flattenAndJoin(tok))
		else:
			res.append(tok)
	return "".join(res)

def joinChildren(_1, _2, toks):
	'''returns a join of all tokens of the pyparsing token list toks.

	This is supposed to be a parseAction, hence the weird signature, including
	the function returning a list.
	'''
	return flattenAndJoin(toks.asList())


# basic preterminals to use in grammars
commonPreterminals = """
import copy
from pyparsing import Word, Literal, Optional, OneOrMore, alphas, restOfLine,\
	LineEnd, StringEnd, NotAny, Suppress, Group, LineStart, SkipTo

from gavo.cfgrammar import joinChildren

One = copy.copy
ignoredLine = Suppress(restOfLine + LineEnd())
digits = "0123456789"
colsep = Suppress(Literal("|"))
sign = Literal("+") | Literal("-")
cardLit = Word(digits)
digit = Word(digits, exact=1)
intLit = Optional(sign) + cardLit
intLit.setParseAction(joinChildren)
fracLit = Group(One(cardLit) + Optional("." + Optional(cardLit))
	) | Group("." + One(cardLit))
fracLit.setParseAction(joinChildren)
floatLit =  Group(Optional(sign) + One(fracLit))
floatLit.setParseAction(joinChildren)
alphabetSoup = Word(digits+alphas+"_")
rightAscWithBlanks = Group(One(cardLit) + One(cardLit) + One(fracLit))
decWithBlanks = Group(One(sign) + One(cardLit) + One(cardLit) + One(fracLit))
"""

def getProductions(rawGrammar):
	r"""returns a dictionary containing the productions of the grammar
	in the form of pyparsing ParserElements.
	"""
	productionDict = {}
	exec commonPreterminals+"\n"+rawGrammar in productionDict
	return productionDict


def fixIndentation(rawCode):
	"""returns the string rawCode with the indent of the first line
	removed in all lines.

	The function raises an Error if any subsequent line has less
	indentation as the first one.
	"""
	lines = [ln for ln in rawCode.split("\n") if ln.strip()]
	if lines:
		indent = re.match(r"\s*", lines[0]).group()
		indentWidth = len(indent)
		for ln in lines:
			if not ln.startswith(indent):
				raise Error("Line %s indentation error."%
					repr(ln))
	else:
		indentWidth = 0
	return "\n".join([ln[indentWidth:] for ln in lines])


class CFGrammar(grammar.Grammar):
	"""is a container for the Grammar of a source with semi-structured
	Data.

	The rules of the Grammar are given as pyparsing rules for now.
	We should probably switch to EBNF at some point.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"rules": utils.RequiredField,
			"documentProduction": "document",
			"rowProduction": "tableLine",
		})

	def enableDebug(self, debugProductions):
		for prod in debugProductions:
			try:
				self.productions[prod].setDebug(True)
			except KeyError:
				gavo.ui.displayError("Production %s does not exist, not debugging it."
					%prod)

	def set_rules(self, rawGrammar):
		"""compiles a pyparsing specification in rawGrammar
		and stores the resulting code for later use in our
		parse method.

		To regularize indentation, the indentation of the first
		non-empty line will be substracted from all further lines.
		"""
		self.dataStore["rules"] = rawGrammar
		try:
			self.productions = getProductions(
				fixIndentation(rawGrammar))
		except Error, msg:
			raise utils.raiseTb(gavo.FatalError, 
				"Grammar could not be compiled: %s"%msg)

	def _parse(self, inputFile):
		res = self.productions[self.get_documentProduction()].parseString(
			inputFile.read())
	

if __name__=="__main__":
	_test()
