"""
A module to parse unit strings a la 
http://vizier.u-strasbg.fr/doc/catstd-3.2.htx and compute conversion factors.
"""

import math
import re
import traceback

from pyparsing import Word, Literal, Regex, Optional, ZeroOrMore, StringEnd
from pyparsing import MatchFirst, ParseException, ParserElement

from gavo.utils import excs

ParserElement.enablePackrat()

class IncompatibleUnits(excs.Error):
	pass

class BadUnit(excs.Error):
	pass


# We can't yet restructure the tree, so we don't do SI-base-casting for
# compound units.  Also, we don't change anything when a change of exponent
# would be necessary
units = {
	"a": (3600*24*365.25, "s"), # This is the SI/julian year!
	"A": (1, "A"), 
	"AU": (1.49598e11, "m"), 
	"arcmin": (math.pi/180./60., "rad"), 
	"arcsec": (math.pi/180./3600., "rad"), 
	"barn": (1, "barn"),  # 1e-28 m2
	"bit": (1, "bit"), 
	"byte": (1, "byte"),  # I don't think we ever want to unify bit and byte
	"C": (1, "C"),        # A.s
	"cd": (1, "cd"), 
	"ct": (1, "ct"), 
	"D": (1e-19/3., "D"), # C.m
	"d": (3600*24, "s"), 
	"deg": (math.pi/180., "rad"), 
	"eV": (1.602177e-19, "J"), 
	"F": (1, "F"),        # C/V
	"g": (1e-3, "kg"), 
	"h": (3600., "s"), 
	"H": (1, "H"),        # Wb/A
	"Hz": (1, "Hz"),      # s-1
	"J": (1, "J"), 
	"Jy": (1, "Jy"),			# 1e-26 W/m2/Hz
	"K": (1, "K"), 
	"lm": (1, "lm"), 
	"lx": (1, "lx"), 
	"m": (1, "m"), 
	"mag": (1, "mag"),    # correlate that with, erm, lux?
	"mas": (math.pi/180./3.6e6, "rad"), 
	"min": (60, "s"), 
	"mol": (1, "mol"), 
	"N": (1, "N"),        # kg.m/s2
	"Ohm": (1, "Ohm"),    # V/A
	"Pa": (1, "Pa"),      # N/m^2
	"pc": (3.0857e16, "m"), 
	"pix": (1, "pix"), 
	"rad": (1, "rad"), 
	"Ry": (2.17989e-18, "J"), 
	"s": (1, "s"), 
	"S": (1, "S"),        # A/V
	"solLum": (3.826e26, "W"),
	"solMass": (1.989e30, "kg"),
	"solRad": (6.9559e8, "m"), 
	"sr": (1, "sr"), 
	"T": (1, "T"),        # Wb/m2
	"V": (1, "V"), 
	"W": (1, "W"),        # kg.m2/s2 or A.V -- that's going to be a tough one
	"Wb": (1, "Wb"), 
	"yr": (3600*24*365.25, "s"), # This is the SI/julian year!
}

prefixes = {"d": 1e-1, "c": 1e-2, "m":1e-3, "u":1e-6, 
	"n":1e-9, "p":1e-12, "f":1e-15, "a":1e-18, "z":1e-21, "y":1e-24,
	"da": 1e1, "h":1e2, "k":1e3, "M":1e6, "G":1e9, "T":1e12, "P":1e15, 
	"E":1e18, "Z":1e21, "Y":1e24}


class Prefix(object):
	"""is a decimal prefix to a unit.

	You find the float value of the thing in its float attribute.
	"""
	def __init__(self, s, pos, toks):
		self.prefix = toks[0]
		self.float = prefixes[self.prefix]


class ExedFloat(object):
	"""is a float in the mant x exp notation of CDS.
	"""
	pat = re.compile(r"([\d.]+)(?:x10([+-])(\d+))?$")

	def __init__(self, s, pos, toks):
		self.literal = toks[0]
		mat = self.pat.match(self.literal)
		mantissa = float(mat.group(1))
		exponent = 0
		if mat.group(3):
			exponent = int(mat.group(3))
			if mat.group(2)=="-":
				exponent = -exponent
		self.float = mantissa*10**exponent


class Unit(object):
	"""is a unit with an optional numeric factor and an optional prefix in
	front and an optional exponent at the end.
	"""
	def __init__(self, s, pos, toks):
		self.scale = 1
		self.exponent = 1
		self.unit = "--"
		for tok in toks:
			if isinstance(tok, Prefix) or isinstance(tok, ExedFloat):
				self.scale *= tok.float
			elif isinstance(tok, basestring):
				self.unit = tok
			elif isinstance(tok, int):
				self.exponent = tok
			else:
				raise Exception("This can't happen")
	
	def __str__(self):
		parts = []
		if self.scale!=1:
			parts.append(str(self.scale))
		parts.append(self.unit)
		if self.exponent!=1:
			parts.append(str(self.exponent))
		return "".join(parts)
	
	def toSI(self):
		"""tries to make self's unit SI.

		This will usually change scale.
		"""
		factor, newUnit = units.get(self.unit, (None, None))
		self.scale *= factor
		self.unit = newUnit
	
	def __cmp__(self, other):
		if isinstance(other, Unit):
			return cmp((self.unit, self.exponent), (other.unit, other.exponent))
		return super(Unit, self).__cmp__(other)


class Expression(object):
	"""is an expression made of possibly scaled units, multiplication, and
	division.
	"""
	def __init__(self, s, pos, toks):
		self.globalFactor = 1
		self.units = []
		self._addTokens(toks)

	def __str__(self):
		prefix = ""
		if self.globalFactor!=1:
			prefix = "%g "%self.globalFactor
		return prefix+" ".join([str(u) for u in self.units])

	def __repr__(self):
		return repr(self.__str__())

	def _addTokens(self, toks):
		curOperator = "."
		for tok in toks:
			if isinstance(tok, Unit):
				if curOperator=="/":
					tok.exponent = -tok.exponent
				self.units.append(tok)
			elif isinstance(tok, str):
				curOperator = tok
			else:
				raise Exception("This can't happen")
	
	def normalize(self):
		"""tries to convert all subordinate units to SI, collects all factors 
		into one and sorts the remaining units.
		"""
		for unit in self.units:
			unit.toSI()
		for unit in self.units:
			if unit.exponent<0:
				self.globalFactor /= float(unit.scale)
			else:
				self.globalFactor *= unit.scale
			unit.scale = 1
		return self

	def getFactor(self, other):
		"""returns a factor you have to multiply to values given in self
		to get values given in other.

		Both self and other have to be normalized.  The function will
		raise an IncompatibleUnits exception if self and other do not
		have the same dimension.
		"""
		if self.units!=other.units:
			raise IncompatibleUnits("%s, %s"%(str(self), str(other)))
		return self.globalFactor/other.globalFactor


def getUnitGrammar():
	unitStrings = units.keys()
	unitStrings.sort(lambda a,b: -cmp(len(a), len(b)))
# funkyUnits those that would partially parse, like mas or mag
	funkyUnit = Regex("cd|Pa|mas|mag")
	unit = Regex("|".join(unitStrings))
	unit.setWhitespaceChars("")
	prefix = Regex("|".join(prefixes))
	prefix.setParseAction(Prefix)
	number = Regex(r"[+-]?(\d+(?:\.?\d+)?)(x10[+-]\d+)?").setParseAction(
		ExedFloat)
	integer = Regex(r"[+-]?(?:\d+)").setParseAction(lambda s, p, toks: 
		int(toks[0]))
	operator = Literal(".") | Literal("/")
	completeUnit = (Optional(number) + ( funkyUnit | Optional(prefix) + unit ) + 
		Optional(integer))
	prefixlessUnit = Optional(number) + unit + Optional(integer)
# The longest match here is a bit unfortunate, but it's necessary to keep
# the machinery from happily accepting the m in ms as a unit and then
# stumble since there's not operator or number following
	unitLiteral = completeUnit | prefixlessUnit
	unitLiteral.setParseAction(Unit)
	expression = ( unitLiteral + ZeroOrMore( operator + unitLiteral ) +
		StringEnd() ).setParseAction(Expression)

	prefix.setName("metric prefix")
	unit.setName("naked unit")
	completeUnit.setName("unit with prefix")
	prefixlessUnit.setName("unit without prefix")

	if False:
		unit.setDebug(True)
		prefix.setDebug(True)
		prefixlessUnit.setDebug(True)
		completeUnit.setDebug(True)
		unitLiteral.setDebug(True)
	return expression


def parseUnit(unitStr, unitGrammar=getUnitGrammar()):
	try:
		return unitGrammar.parseString(unitStr)[0]
	except ParseException, msg:
#		traceback.print_exc()
		raise BadUnit("%s at col. %d"%(repr(unitStr), msg.column))


def computeConversionFactor(unitStr1, unitStr2):
	"""returns the factor needed to get from quantities given in unitStr1
	to unitStr2.

	Both must be given in a slightly relaxed form of CDS' unit notation.

	This function may raise a BadUnit if one of the strings are
	malformed, or an IncompatibleUnit exception if the units don't have
	the same SI base.
	"""
	if unitStr1==unitStr2:
		return 1
	unit1, unit2 = parseUnit(unitStr1), parseUnit(unitStr2)
	unit1.normalize()
	unit2.normalize()
	return unit1.getFactor(unit2)


def computeColumnConversions(newColumns, oldColumns):
	"""returns a dict of conversion factors between newColumns and oldColumns.
	
	Both arguments are rscdef.ColumnLists.

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
			raise excs.DataError(
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
