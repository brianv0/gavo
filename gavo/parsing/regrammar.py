"""
This module contains code to handle regular grammars for data parsing.
"""

import re
import sys

import gavo
from gavo import record
import gavo.parsing
from gavo.parsing import grammar

class Error(gavo.parsing.ParseError):
	pass


def makeMatchTokenizer(splitRE):
	splitRE = re.compile(splitRE)
	def tokenizer(line):
		return splitRE.match(line).groups()
	return tokenizer


def makeColrangesTokenizer(rangeString):
	rangeString = re.sub("#[^\n]*\n", " ", rangeString)
	tokenRanges = []
	for range in rangeString.split():
		parts = range.split("-")
		if len(parts)==2:
			tokenRanges.append(slice(int(parts[0])-1, int(parts[1])))
		elif len(parts)==1:
			tokenRanges.append(int(parts[0])-1)
		else:
			raise Error("Column range %s invalid"%range)
	def tokenizer(line, tokenRanges=tokenRanges):
		for range in tokenRanges:
			yield line[range]
	return tokenizer


predefinedSymbols = {
	"restOfLine": "[^\n]*\n",
	"digit": "[0-9]",
	"sign": "[+-]",
	"char": r"[^\s]",
	"cardLit": r"\s*@(digit)+",
	"intLit": r"\s*@(sign)?\s*@(cardLit)",
	"fracLit": r"\s*@(cardLit)?\s*\.@(cardLit)?",
	"floatLit": r"\s*@(sign)?\s*@(fracLit)",
	"alphabetSoup": r"\s*\w+",
	"anything": r"\s*[^\s]+",
	"anythingAtAll": r"\s*.+",
	"rightAscWithBlanks": 
		r"\s*@(cardLit)\s*@(cardLit)\s*(?:@(fracLit)|@(cardLit))",
	"decWithBlanks": 
		r"\s*@(sign)\s*@(cardLit)\s*@(cardLit)\s*(?:@(fracLit)|@(cardLit))",
}

class REGrammar(grammar.Grammar):
	"""is a container for the (regular) Grammar of a source with
	semi-structured Data.

	The rules of the grammar are given in what basically are pcre
	expressions with slight extensions to keep them readable.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"rules": record.RequiredField,
			"documentProduction": "document",
			"numericGroups": record.BooleanField,
			"rowProduction": "tableLine",
			"tabularDataProduction": "tabularData",
			"tokenizer": record.RequiredField,
			"tokenSequence": record.RequiredField,
		})

	groupRe = re.compile(r"@\(([^,)]+)\)")
	matchingGroupRe = re.compile(r"@\(([^,)]*),([^,)]+)\)")

	def enableDebug(self, debugProductions):
		pass  # let's see how we'll be doing this.

	def _handleContinuations(self, lines):
		"""merges following lines to ones with a backslash at the end.
		"""
		newLines = []
		curLine = []
		for l in lines:
			if l.endswith("\\"):
				curLine.append(l[:-1])
			else:
				newLines.append(" ".join([s for s in curLine])+l)
				curLine = []
		return newLines

	def _getSymbols(self, lines):
		"""returns a "symbol table" from the re definitions in lines.

		The symbol table is just a dict mapping the "preterminals" to
		proto-REs.
		"""
		ruleRe = re.compile(r"(\w+)\s*=\s*(.*)")
		try:
			return dict([ruleRe.match(l).groups() for l in lines])
		except AttributeError:
			raise Error("Syntax error in rules: %s malformed"%repr(l))

	def _expandRE(self, expression):
		"""returns the expression with all @-references expanded.

		This is done by repeated lookups in the symbol table.  If your grammar
		is severly nonregular, this function will enter an endless loop.  You
		should then consider using a CFGrammar.
		"""
		try:
			while True:
				expression, gSubsMade = self.groupRe.subn(
					lambda mat: "(?:%s)"%self.symbolTable[mat.group(1)], expression)
				expression, mSubsMade = self.matchingGroupRe.subn(
					lambda mat: "(?P<%s>%s)"%(mat.group(1),
						self.symbolTable[mat.group(2)]), expression)
				if not (mSubsMade or gSubsMade):
					break
			return expression
		except KeyError, msg:
			raise Error("Error in REGrammar definition: %s used but"
				" not defined."%msg)

	def _getRE(self, production):
		"""returns the RE for production with all @-references expanded.
		"""
		return self._expandRE(self.symbolTable[production])
			
	def _getCleanedText(self, text):
		"""returns a list of lines, stripped and with #-on-a-line comments 
		removed.
		"""
		return [s.strip() for s in text.split("\n")
			if s.strip() and not s.strip().startswith("#")]

	def _buildSymbolTable(self, rawGrammar):
		"""parses the grammar specification and builds a symbol table
		for the grammar given.

		The grammar specification itself is regular and should probably stay
		that way.
		"""
		self.symbolTable = self._getSymbols(
				self._handleContinuations(
					self._getCleanedText(rawGrammar)))
		self.symbolTable.update(predefinedSymbols)
	
	def set_rules(self, rawGrammar):
		self._buildSymbolTable(rawGrammar)
	
	def set_tokenSequence(self, rawTokenSequence):
		try:
			self.dataStore["tokenSequence"] = [re.compile(
					self._expandRE(tokD+'$'))
				for tokD in self._getCleanedText(rawTokenSequence)]
		except (IndexError, re.error), msg:
			raise Error("Bad input: RE %s not well-formed (%s)"%(tokD, msg))

	def set_tokenizer(self, splitRE, tokenizerType="split"):
		if isinstance(splitRe, tuple):
			splitRE, tokenizerType = splitRE
		if tokenizerType=="split":
			splitRE = re.compile(splitRE)
			self.dataStore["tokenizer"] = lambda line: splitRE.split(line.strip())
		elif tokenizerType=="match":
			self.dataStore["tokenizer"] = makeMatchTokenizer(splitRE)
		elif tokenizerType=="colranges":
			self.dataStore["tokenizer"] = makeColrangesTokenizer(splitRE)
		else:
			raise Error("Undefined tokenizer type %s"%tokenizerType)

	def _buildREs(self):
		"""compiles the global regular expressions into attributes.
		"""
		self.documentRe = re.compile(
			self._getRE(self.get_documentProduction()))
		self.rowRe = re.compile(
			self._getRE(self.get_rowProduction()))
		self.recoverRe = re.compile("[^\n]*\n")
		try:
			self.preRowDebrisRe = re.compile(
				self._getRE("preRowDebris"))
		except KeyError:
			self.preRowDebrisRe = None
		try:
			self.postRowDebrisRe = re.compile(
				self._getRE("postRowDebris"))
		except KeyError:
			self.postRowDebrisRe = None

	def _matchRow(self, rawRow):
		rowdict = {}
		tokens = self.get_tokenizer()(rawRow)
		if len(tokens)!=len(self.get_tokenSequence()):
			raise Error("Found %d tokens in %s, but expected %d"%(len(tokens),
				repr(rawRow), len(self.get_tokenSequence())))
		for token, tokDef in zip(tokens, self.get_tokenSequence()):
			mat = tokDef.match(token)
			if not mat:
				raise Error("Could not match %s with %s in row %s"%(
					tokDef.pattern, repr(token), repr(rawRow)))
			rowdict.update(mat.groupdict())
		return rowdict

	def _matchRowIndex(self, rawRow):
		"""this row matcher kicks in for REGrammars with numericGroups.
		"""
		tokens = self.get_tokenizer()(rawRow)
		return dict((str(ct), token) for ct, token in enumerate(tokens))

	def _iterRows(self):
		"""applies the RE for rows to src until its end is reached.
		"""
		if self.get_numericGroups():
			matchRow = self._matchRowIndex
		else:
			matchRow = self._matchRow
		src = self.tabularData
		curPos = 0
		while curPos<len(src):
			if self.preRowDebrisRe:
				mat = self.preRowDebrisRe.match(src, curPos)
				if mat:
					curPos = mat.end()
			mat = self.rowRe.match(src, curPos)
			if not mat:
				raise Error("No row found near %s."%(repr(
					src[curPos:curPos+40])))
			try:
				if mat.lastindex:
					yield matchRow(mat.group(mat.lastindex))
				else:
					yield matchRow(mat.group())
			except Error:
				# recover by advancing to the next newline (or whatever recoverRe is)
				mat = self.recoverRe.match(src, curPos)
				raise
			curPos = mat.end()
			if self.postRowDebrisRe:
				mat = self.postRowDebrisRe.match(src, curPos)
				if mat:
					curPos = mat.end()


	def _setupParse(self):
		self._buildREs()
	
	def _getDocumentRow(self):
		src = self.inputFile.read()
		mat = self.documentRe.match(src)
		self.tabularData = mat.group(self.get_tabularDataProduction())
		return mat.groupdict()


if __name__=="__main__":
	g = REGrammar()
	g.set_rules(r"""
			document = @(header)@(tabularData,tabularData)$
			tabularData = .*
			header = @(restOfLine){10}
			doubleDigit = @(digit)@(digit)
			tableLine = \| @(hip_number,cardLit) \|\
					@(fk6_number,cardLit)? \|\
					@(subsampleflag,alphabetSoup)? \|\
					@(gc_number,cardLit)? \|\
					@(selectedcatalogue,alphabetSoup) \|\
					# 5
					@(alpha_2000_si,rightAscWithBlanks) \|\
					@(delta_2000_si,decWithBlanks) \|\
					@(mu_alpha_2000_si,floatLit) \|\
					@(mu_delta_2000_si,floatLit) \|\
					@(t_alpha_si,fracLit) \|\
					# 10
					@(epsilon_alpha_si,fracLit) \|\
					@(epsilon_mu_alpha_si,fracLit) \|\
					@(t_delta_si,fracLit) \|\
					@(epsilon_delta_si,fracLit) \|\
					@(epsilon_mu_delta_si,fracLit) \|\
					# 15
					@(p,floatLit) \|\
					@(epsilon_p,fracLit) \|\
					@(k_p,alphabetSoup) \|\
					@(v_rad,floatLit)? \|\
					@(m_v,floatLit) \|\
					# 20
					@(k_m,alphabetSoup)? \|\
					@(k_bin,doubleDigit) \|\
					@(k_delta_mu,cardLit) \|\
					@(k_ae,digit)? \|\
					@(delta_mu_alpha_ltp,floatLit) \|\
					# 25 
					@(delta_mu_alpha_stp,floatLit) \|\
					@(delta_mu_alpha_hip,floatLit) \|\
					@(delta_mu_delta_ltp,floatLit) \|\
					@(delta_mu_delta_stp,floatLit) \|\
					@(delta_mu_delta_hip,floatLit) \|\
					# 30
					@(epsilon_mu_alpha_ltp,floatLit) \|\
					@(epsilon_mu_alpha_stp,floatLit) \|\
					@(epsilon_mu_alpha_hip,floatLit) \|\
					@(epsilon_mu_delta_ltp,floatLit) \|\
					@(epsilon_mu_delta_stp,floatLit) \|\
					# 35  
					@(epsilon_mu_delta_hip,floatLit) \|\
					@(f_fh,fracLit)? \|\
					@(f_oh,fracLit)? \|\
					@(f_ogch,fracLit)? \|\
					@(f_of,fracLit)? \|\
					# 40
					@(f_th,fracLit)? \|\
					@(individualnotenr,cardLit)? \|\s*
""")
	import sys
	g.setRowHandler(lambda d:sys.stdout.write(str(d)+"\n"))
	g.parse("../../inputs/arihcp01/arihcp01.part")
