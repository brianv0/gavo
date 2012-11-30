"""
A module to parse unit strings a la 
http://vizier.u-strasbg.fr/doc/catstd-3.2.htx and compute conversion factors.
"""

from __future__ import with_statement

import math
import re
import traceback


from gavo import utils
from gavo.imp import pyparsing


class IncompatibleUnits(utils.Error):
	pass

class BadUnit(utils.Error):
	pass


# We can't yet restructure the tree, so we don't do SI-base-casting for
# compound units.  Also, we don't change anything when a change of exponent
# would be necessary
PLAIN_UNITS = units = {
	"a": (3600*24*365.25, "s"), # This is the SI/julian year!
	"A": (1, "A"),				# *Ampere* not Angstrom 
	"adu": (1, "adu"),
	u"\xc5": (1e-10, "m"),
	"Angstrom": (1e-10, "m"),
	"angstrom": (1e-10, "m"),
	"AU": (1.49598e11, "m"), 
	"arcmin": (math.pi/180./60., "rad"), 
	"arcsec": (math.pi/180./3600., "rad"), 
	"barn": (1, "barn"),  # 1e-28 m2
	"beam": (1, "beam"), 
	"bit": (1, "bit"), 
	"bin": (1, "bin"), 
	"byte": (1, "byte"),  # I don't think we ever want to unify bit and byte
	"C": (1, "C"),        # A.s
	"cd": (1, "cd"), 
	"ct": (1, "ct"), 
	"count": (1, "ct"), 
	"chan": (1, "chan"), 
	"D": (1e-19/3., "D"), # C.m
	"d": (3600*24, "s"), 
	"deg": (math.pi/180., "rad"), 
	"erg": (1e-7, "J"), 
	"eV": (1.602177e-19, "J"), 
	"F": (1, "F"),        # C/V
	"g": (1e-3, "kg"), 
	"G": (1e-4, "T"), 
	"h": (3600., "s"), 
	"H": (1, "H"),        # Wb/A
	"Hz": (1, "Hz"),      # s-1
	"J": (1, "J"), 				# kg m^2/s^2
	"Jy": (1, "Jy"),			# 1e-26 W/m2/Hz
	"K": (1, "K"), 
	"lm": (1, "lm"), 
	"lx": (1, "lx"), 
	"lyr": (2627980686828.0, "m"), 
	"m": (1, "m"), 
	"mag": (1, "mag"),    # correlate that with, erm, lux?
	"mas": (math.pi/180./3.6e6, "rad"), 
	"min": (60, "s"), 
	"mol": (1, "mol"), 
	"N": (1, "N"),        # kg.m/s2
	"Ohm": (1, "Ohm"),    # V/A
	"Pa": (1, "Pa"),      # N/m^2
	"pc": (3.0857e16, "m"), 
	"ph": (1, "ph"), 
	"photon": (1, "ph"), 
	"pix": (1, "pix"), 
	"pixel": (1, "pix"), 
	"rad": (1, "rad"), 
	"Ry": (2.17989e-18, "J"), 
	"s": (1, "s"), 
	"S": (1, "S"),        # A/V
	"solLum": (3.826e26, "W"),
	"solMass": (1.989e30, "kg"),
	"solRad": (6.9559e8, "m"), 
	"sr": (1, "sr"), 
	"T": (1, "T"),        # V.s/m2
	"u": (1.66053886e-27, "kg"),
	"V": (1, "V"), 
	"voxel": (1, "voxel"),
	"W": (1, "W"),        # kg.m2/s3 or A.V -- that's going to be a tough one
	"Wb": (1, "Wb"), 
	"yr": (3600*24*365.25, "s"), # This is the SI/julian year!
}

# These are the keys from PLAIN_UNITS that cannot take SI prefixes
NON_PREFIXABLE = frozenset([
	"AU", "D", "Ry", "arcmin", "beam", "bin", "chan", "d", "h", "mas",
	"min", "ph", "photon", "pix", "pixel", "solLum", "solMass", "solRad",
	"voxel"])

PREFIXES = prefixes = {"d": 1e-1, "c": 1e-2, "m":1e-3, "u":1e-6, 
	"n":1e-9, "p":1e-12, "f":1e-15, "a":1e-18, "z":1e-21, "y":1e-24,
	"da": 1e1, "h":1e2, "k":1e3, "M":1e6, "G":1e9, "T":1e12, "P":1e15, 
	"E":1e18, "Z":1e21, "Y":1e24}


def formatScaleFactor(aFloat):
	"""returns a float in the form <mantissa> 10<exponent>.

	Floats looking good as simple decimals (modulus between 0.01 and 1000)
	are returned without exponent.
	"""
	if 0.01<=abs(aFloat)<=1000:
		return ("%f"%aFloat).rstrip("0")

	exponent = int(math.log10(aFloat))
	mantissa = ("%f"%(aFloat/10**exponent)).rstrip("0")
	return "%s 10%+d"%(mantissa, exponent)


class _Node(object):
	"""the abstract base for a node in a Unit tree.
	"""


class UnitNode(_Node):
	"""a preterminal node containing a unit and possibly a prefix.

	It is constructed from the unit grammar.
	"""
	def __init__(self, s, pos, toks):
		if len(toks)==2:
			self.prefix, self.unit = toks[0], toks[1]
			self.prefixFactor = PREFIXES[self.prefix]
		else:
			self.prefix, self.prefixFactor = "", 1
			self.unit = toks[0]

	def __str__(self):
		return "%s%s"%(self.prefix, self.unit)

	def __repr__(self):
		return "U(%s ; %s)"%(self.prefix, repr(self.unit))

	def getSI(self):
		"""returns a pair of factor and basic unit.

		Basic units are what's in the defining pairs in the PLAIN_UNITS dict.
		"""
		factor, basic = PLAIN_UNITS[self.unit]
		return self.prefixFactor*factor, {basic: 1}


class Factor(_Node):
	"""An AtomicUnit with a power.
	"""
	def __init__(self, s, p, toks):
		self.unit = toks[0]
		self.power = toks[1]

	def __str__(self):
		powerLit = repr(self.power).rstrip("0").rstrip(".")
		if "." in powerLit:
			# see if we can come up with a nice fraction
			for denom in range(2, 8):
				if abs(int(self.power*denom)-self.power*denom)<1e-13:
					powerLit = "**(%d/%d)"%(round(self.power*denom), denom)
					break
			else:
				powerLit = "**"+powerLit
		return "%s%s"%(self.unit, powerLit)

	def __repr__(self):
		return "F(%s ; %s)"%(repr(self.unit), repr(self.power))
	
	def getSI(self):
		factor, powers = self.unit.getSI()
		powers[powers.keys()[0]] = self.power
		return factor**self.power, powers


class FunctionApplication(_Node):
	"""A function applied to a term.
	"""
	_pythonFunc = {
		"ln": math.log,
		"log": math.log10,
		"exp": math.exp,
		"sqrt": math.sqrt,
	}

	def __init__(self, s, p, toks):
		self.funcName = toks[0]
		self.term = toks[1]

	def __str__(self):
		return "%s(%s)"%(self.funcName, self.term)

	def __repr__(self):
		return "A(%s ; %s)"%(repr(self.funcName), repr(self.term))
	
	def getSI(self):
		factor, powers = self.term.getSI()
		if self.funcName=="sqrt":
			powers = dict((key, value/2.) 
				for key, value in powers.iteritems())
		else:
			powers = dict(((self.funcName, key), value) 
				for key, value in powers.iteritems())
		return self._pythonFunc[self.funcName](factor), powers


class Term(_Node):
	"""A Node containing two factors and an operator.
	"""
	def __init__(self, s, pos, toks):
		assert len(toks)==3
		self.op1, self.op2 = toks[0], toks[2]
		self.operator = toks[1]
		if self.operator=='.' or self.operator=='*':
			self.operator = ' '

	def __str__(self):
		op1Lit, op2Lit = str(self.op1), str(self.op2)
		if self.operator=='/' and isinstance(self.op2, Term):
			op2Lit = "(%s)"%op2Lit
		return "%s%s%s"%(op1Lit, self.operator, op2Lit)

	def __repr__(self):
		return "T(%s ; %s ; %s)"%(repr(self.op1), 
			repr(self.operator), repr(self.op2))

	def getSI(self):
		factor1, powers1 = self.op1.getSI()
		factor2, powers2 = self.op2.getSI()
		newPowers = powers1
		if self.operator==" ":
			for si, power in powers2.iteritems():
				newPowers[si] = newPowers.get(si, 0)+power
			return factor1*factor2, newPowers
		else:
			for si, power in powers2.iteritems():
				newPowers[si] = newPowers.get(si, 0)-power
			return factor1/factor2, newPowers


class Expression(_Node):
	"""The root node of an expression tree, giving a factor (defaulting to 1)
	and a term.
	"""
	def __init__(self, s, p, toks):
		if len(toks)==2:
			self.factor, self.term = toks
		elif len(toks)==1:
			self.factor, self.term = 1., toks[0]
		else:
			raise Exception("This can't happen")

	def __str__(self):
		if self.factor==1:
			return str(self.term)
		else:
			return "%s %s"%(formatScaleFactor(self.factor), self.term)

	def __repr__(self):
		return "R(%s ; %s)"%(repr(self.factor), repr(self.term))

	def getSI(self):
		"""returns a pair of a numeric factor and a dict mapping SI units to
		their powers.
		"""
		factor, siPowers = self.term.getSI()
		return factor*self.factor, siPowers


def _buildTerm(s, pos, toks):
	"""a parseAction for terms, making trees out of parse lists 
	left-associatively.
	"""
	toks = list(toks)
	curOperand = toks.pop(0)
	while len(toks)>1:
		curOperand = Term(s, pos, [curOperand, toks[0], toks[1]])
		del toks[:2]
	return curOperand


def _buildFactor(s, pos, toks):
	"""a parse action for factors, dispatching between the unit (1 operator)
	or unit with power (2 operators) cases).
	"""
	if len(toks)==2:
		return Factor(s, pos, toks)
	elif len(toks)==1:
		return toks[0]
	else:
		raise Exception("This can't happen")


def _parseScaleFactor(s, pos, toks):
	"""a parse action making a float out of the weird format for the global
	scale factor.

	toks must have dict keys; we evaluate mantissa and power.
	"""
	return float(toks.get("mantissa", 1))*10**float(toks.get("power", 0))


def evalAll(s, p, t):
	"""a parse action evaluating the whole match as a python expression.

	Obviously, this should only be added to carefully screened nonterminals.
	"""
	return eval("".join(t))


class getUnitGrammar(utils.CachedResource):
	"""the grammar to parse VOUnits.

	After initialization, the class has a "symbols" dictionary containing
	the individual nonterminals.
	"""
	@classmethod
	def impl(cls):
		from gavo.imp.pyparsing import (Word, Literal, Regex, Optional, ZeroOrMore,
			MatchFirst, ParseException, nums, Suppress, Forward)
		with utils.pyparsingWhitechars(''):
			prefixableUnit = Regex("|".join(u for u in
					sorted(PLAIN_UNITS, key=lambda k: -len(k))
				if u not in NON_PREFIXABLE))
			nonPrefixableUnit = Regex("|".join(u for u in
					sorted(PLAIN_UNITS, key=lambda k: -len(k))
				if u in NON_PREFIXABLE))

			prefix = Regex("|".join(p for p in PREFIXES if p!="da"))
			# da is a valid unit, and I'd need backtracking without
			# special casing.
			dekaPrefix = Literal("da")
			dekaPrefix.setWhitespaceChars("")

			function_name = Regex("sqrt|log|exp|ln")

			atomicUnit = (nonPrefixableUnit
				^ prefixableUnit 
				^ (prefix + prefixableUnit) 
				^ (dekaPrefix + prefixableUnit))
			atomicUnit.setParseAction(UnitNode)

			OPEN_P = Literal('(')
			CLOSE_P = Literal(')')
			SIGN = Literal('+') | Literal('-')
			UNSIGNED_INTEGER = Word("01234567890")
			SIGNED_INTEGER = SIGN + UNSIGNED_INTEGER
			FLOAT = Regex(r"[+-]?([0-9]+(\.[0-9]*)?)")

			integer = SIGNED_INTEGER | UNSIGNED_INTEGER
			power_operator = Suppress(Literal('**') | Literal("^"))
			multiplication_operator = Literal(".") | Literal(" ") | Literal("*")
			numeric_power = (integer 
				| power_operator + integer
				| power_operator + OPEN_P + integer + CLOSE_P 
				| power_operator + OPEN_P + FLOAT + CLOSE_P 
				| power_operator + OPEN_P + integer + '/'
					+ UNSIGNED_INTEGER.addParseAction(lambda s, p, t: t[0]+".") + CLOSE_P)
			numeric_power.setParseAction(evalAll)

			factor = (atomicUnit + numeric_power
				| atomicUnit).addParseAction(
					_buildFactor)

			term = Forward()
			function_application = (function_name
				+ Suppress(OPEN_P) + term + Suppress(CLOSE_P))
			function_application.setParseAction(FunctionApplication)

			unit_expression = (function_application
				| factor
				| Suppress(OPEN_P) + term + Suppress(CLOSE_P))

			term << (unit_expression 
					+ ZeroOrMore(multiplication_operator + unit_expression)
					+ Optional(Literal('/') + unit_expression)
				).setParseAction(_buildTerm)

			pow_10 = Literal("10") + numeric_power("power")
			scale_factor = (FLOAT("mantissa") + multiplication_operator + pow_10
				| pow_10
				| FLOAT("mantissa"))
			scale_factor.addParseAction(_parseScaleFactor)
			input = (
				Optional(scale_factor + Suppress(multiplication_operator))
				+ term).setParseAction(Expression)

			cls.symbols = locals()
			return input

	@classmethod
	def enableDebuggingOutput(cls):
		"""(not user-servicable)
		"""
		from gavo.imp.pyparsing import ParserElement
		for name, sym in cls.symbols.iteritems():
			if isinstance(sym, ParserElement):
				sym.setDebug(True)
				sym.setName(name)


def parseUnit(unitStr, unitGrammar=getUnitGrammar()):
	try:
		return utils.pyparseString(unitGrammar, unitStr, parseAll=True)[0]
	except pyparsing.ParseException, msg:
		raise utils.logOldExc(
			BadUnit("%s at col. %d"%(repr(unitStr), msg.column)))


def computeConversionFactor(unitStr1, unitStr2):
	"""returns the factor needed to get from quantities given in unitStr1
	to unitStr2.

	Both must be given in VOUnits form (we allow cy for century, though).

	This function may raise a BadUnit if one of the strings are
	malformed, or an IncompatibleUnit exception if the units don't have
	the same SI base.

	If the function is successful, unitStr1 = result*unitStr2
	"""
	if unitStr1==unitStr2:
		return 1
	factor1, powers1 = parseUnit(unitStr1).getSI()
	factor2, powers2 = parseUnit(unitStr2).getSI()
	if powers1!=powers2:
		raise IncompatibleUnits("%s and %s do not have the same SI base"%(
			unitStr1, unitStr2))
	
	# tuples as keys in powers come from non-polynomial function
	# applications; in such cases, multiplication is not good enough
	# for conversions, and thus we give up.
	for u in powers1.iterkeys():
		if isinstance(u, tuple):
			raise IncompatibleUnits("%s has a non-polynomial function. No"
				" conversion by multiplication possible"%(unitStr1))
	for u in powers2.iterkeys():
		if isinstance(u, tuple):
			raise IncompatibleUnits("%s has a non-polynomial function. No"
				" conversion by multiplication possible"%(unitStr2))

	return factor1/factor2


def computeColumnConversions(newColumns, oldColumns):
	"""returns a dict of conversion factors between newColumns and oldColumns.
	
	Both arguments are iterables of columns.

	For every column in newColumn, the function sees if the units of
	newColumn and oldColumn match.  If they don't, compute a conversion
	factor to be multiplied to oldColumns values to make them newColumns
	values and add it to the result dict.

	The function raises a DataError if a column in newColumns has no
	match in oldColumns.
	"""
	res = {}
	for newCol in newColumns:
		if not newCol.name in oldColumns:
			raise utils.DataError(
				"Request for column %s from %s cannot be satisfied in %s"%(
					newCol.name, oldColumns, newColumns))
		oldCol = oldColumns.getColumnByName(newCol.name)
		try:
			if newCol.unit!=oldCol.unit:
				res[newCol.name] = computeConversionFactor(oldCol.unit, newCol.unit)
		except BadUnit:  # we ignore bad units, assume they'll be handled by
			# valuemappers.
			pass
	return res


if __name__=="__main__":
	g = getUnitGrammar()
	res = g.parseString("ms")[0]
	print res
	res.normalize()
	print res
