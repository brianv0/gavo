"""
Code to support PQL syntax (as found in various DAL protocols).

PQL range-list syntax is

valSep ::= ","
rangeSep ::= "/"
qualSep ::= ";"
step ::= somethingMagicallyDefined
range ::= [literal] rangeSep literal | literal rangeSep
steppedRange ::= range [rangeSep step]
qualification ::= qualSep somethingMagicallyDefined
listItem ::= steppedRange | literal 
rangeList ::= listItem {valSep listItem} [qualification]

This defines a regular language, and we're going to slaughter it using
REs and ad hoccing.

Since the actually allowed grammar depends on the type of the parameter
(e.g., steps make no sense for strings, and have a special grammar for
dates), parsing is done by the specific PQLPar types (fromLiteral).  See
the PQLPar docstring for further info.
"""

import datetime
import re
import urllib

from gavo import base
from gavo.base import literals
from gavo.base import sqlmunge
from gavo.base import typesystems
from gavo.utils import DEG, pgsphere


QUALIFIER_RE = re.compile("([^;]*)(;[^;]*)?$")
LIST_RE = re.compile("([^,]*),")
RANGE_RE = re.compile("([^/]*)(/[^/]*)?(/[^/]*)?$")


def _raiseNoSteps(val):
	raise ValueError("Step/stride specification not allowed here.")


def _parsePQLValue(val, valInd=0, vp=str):
	if not val or not val[valInd:]:
		return None
	else:
		return vp(urllib.unquote(val[valInd:]))


class PQLRange(object):
	"""a representation of a PQL range.

	PQLRanges have a value attribute that is non-None when there is
	only a single value.

	For ranges, there is start, stop and step, all of which may be
	None.

	The attributes contain whatever the parent's valParser (or stepParser)
	functions return.
	"""
	def __init__(self, value=None, start=None, stop=None, step=None):
		self.start, self.stop, self.step = start, stop, step
		self.value = value
		if (self.step is not None 
				and (self.start is None or self.stop is None)):
			raise ValueError("Open intervals cannot have steps")
		if (self.value is None 
				and (self.start is None and self.stop is None)):
			raise ValueError("Doubly open intervals are not allowed")

	def __eq__(self, other):
		return (isinstance(other, PQLRange)
			and self.value==other.value 
			and self.start==other.start 
			and self.stop==other.stop 
			and self.step==other.step)

	def __repr__(self):
		return "%s(%s, %s, %s, %s)"%(self.__class__.__name__,
			repr(self.value),
			repr(self.start),
			repr(self.stop),
			repr(self.step))

	def __str__(self):
		if self.value is not None:
			return urllib.quote(str(self.value))
		else:
			def e(v):
				if v is None:
					return ""
				else:
					return urllib.quote(str(v))
			return "/".join(e(v) for v in (self.start, self.stop, self.step))
			
	@classmethod
	def fromLiteral(cls, literal, destName, valParser, stepParser):
		"""creates a PQLRange from a PQL range literal.

		For the meaning of the arguments, see PQLPar.fromLiteral.
		"""
		if literal=="":
			return cls(value="")
		mat = RANGE_RE.match(literal)
		if not mat:
			raise base.LiteralParseError(destName, literal,
				hint="PQL ranges roughly have the form [start][/stop[/stop]]."
				" Literal slashes need to be escaped (as %2f).")
		vals = mat.groups()

		try:
			if vals[1] is None and vals[2] is None:
				return cls(value=_parsePQLValue(vals[0], vp=valParser))
			else:
				start, stop, step = vals
			return cls(
				start=_parsePQLValue(start, vp=valParser), 
				stop=_parsePQLValue(stop, 1, vp=valParser), 
				step=_parsePQLValue(step, 1, vp=stepParser))
		except ValueError, ex:
			raise base.LiteralParseError("range within %s"%destName, literal,
				hint=str(ex))

	def getValuesAsSet(self):
		"""returns a set containing all values matching the PQL condition if
		they form a discrete set or raises a ValueError if not.
		"""
		if self.value is not None:
			return set([self.value])
		elif (self.step is not None \
				and self.start is not None 
				and self.stop is not None):
			res, val = set(), self.start
			while val<=self.stop:
				res.add(val)
				val = val+self.step
			return res
		raise ValueError("No set representation for non-stepped or open ranges.")

	def getSQL(self, colName, sqlPars):
		"""returns an SQL boolean expression for representing this constraint.
		"""
		# Single Value
		if self.value is not None:
			return "%s = %%(%s)s"%(colName, 
				base.getSQLKey(colName, self.value, sqlPars))
		
		# Discrete Set
		try:
			return "%s IN %%(%s)s"%(colName, base.getSQLKey(colName, 
				self.getValuesAsSet(), sqlPars))
		except ValueError: # Not a discrete set
			pass

		# At least one half-open or non-stepped range
		if self.start is None and self.stop is not None:
			return "%s <= %%(%s)s"%(colName, 
				base.getSQLKey(colName, self.stop, sqlPars))
		elif self.start is not None and self.stop is None:
			return "%s >= %%(%s)s"%(colName, 
				base.getSQLKey(colName, self.start, sqlPars))
		else:
			assert self.start is not None and self.stop is not None
			return "%s BETWEEN %%(%s)s AND %%(%s)s "%(colName, 
				base.getSQLKey(colName, self.start, sqlPars),
				base.getSQLKey(colName, self.stop, sqlPars))

	def getSQLForInterval(self, lowerColName, upperColName, sqlPars):
		"""returns an SQL boolean expression for representing this constraint
		against an upper, lower interval in the DB table.

		This will silently discard any step specification.
		"""
		# Single Value
		if self.value is not None:
			return "%%(%s)s BETWEEN %s AND %s"%(
				base.getSQLKey("val", self.value, sqlPars),
				lowerColName, upperColName)
		else:
			constraints = []
			if self.stop is not None:
				constraints.append("%%(%s)s>%s"%(
					base.getSQLKey("val", self.stop, sqlPars),
					lowerColName))
			if self.start is not None:
				constraints.append("%%(%s)s<%s"%(
					base.getSQLKey("val", self.start, sqlPars),
					upperColName))
			return "(%s)"%" AND ".join(constraints)

					
class PQLPar(object):
	"""a representation for PQL expressions.

	PQLPar objects have an attribute qualifier (None or a string),
	and an attribute ranges, a list of PQLRange objects.
	
	As a client, you will ususally construct PQLPar objects using the
	fromLiteral class method; it takes a PQL literal and a name to be 
	used for LiteralParseErrors it may raise.

	The plain PQLPar parses string ranges and does not allow steps.

	Inheriting classes must override the valParser and stepParser attributes.
	Both take a string and have to return a typed value or raise a
	ValueError if the string does not contain a proper literal.
	The default for valParser is str, the default for stepParser
	a function that always raises a ValueError.

	Note: valParser and stepParser must not be *methods* of the
	class but plain functions; since they are function-like class attributes,
	you will usually have to wrap them in staticmethods
	"""
	valParser = str
	stepParser = staticmethod(_raiseNoSteps)

	def __init__(self, ranges, qualifier=None, destName=None):
		self.qualifier = qualifier
		self.ranges = ranges
		self.destName = None

	def __eq__(self, other):
		return (isinstance(other, PQLPar)
			and self.qualifier==other.qualifier
			and self.ranges==other.ranges)

	def __str__(self):
		res = ",".join(str(r) for r in self.ranges)
		if self.qualifier:
			res = res+";"+urllib.quote(self.qualifier)
		return res
	
	def __repr__(self):
		return "%s(%s)"%(self.__class__.__name__,
			repr(str(self)))

	@staticmethod
	def _parsePQLString(cls, val, destName):
		# this is the implementation of the fromLiteral class method(s)
		# It's static so the fromLiterals can upcall.
		if val is None:
			return None

		mat = QUALIFIER_RE.match(val)
		if not mat:
			raise base.LiteralParseError(destName, val, hint="Not more than one"
				" semicolon is allowed in PQL expressions")
		qualifier = _parsePQLValue(mat.group(2), 1)

		ranges = []
		listLiteral = mat.group(1)
		# harmless hack to avoid special-casing for one-element list
		rangeMat = re.match("", listLiteral)
		for rangeMat in LIST_RE.finditer(listLiteral):
			try:
				ranges.append(
					PQLRange.fromLiteral(rangeMat.group(1), destName, 
						cls.valParser, cls.stepParser))
			except base.LiteralParseError, ex:
				ex.pos = rangeMat.start()
				raise
		ranges.append(
			PQLRange.fromLiteral(listLiteral[rangeMat.end():], destName,
				cls.valParser, cls.stepParser))
		return cls(ranges, qualifier, destName)

	@classmethod
	def fromLiteral(cls, val, destName):
		"""returns a parsed representation of a literal in PQL range-list syntax.

		val is a string containing the PQL expression, destName is a name to
		be used for the LiteralParseErrors the function raises when there are
		syntax errors in val.
		"""
		return cls._parsePQLString(cls, val, destName)

	def getValuesAsSet(self):
		"""returns a set of all values mentioned within the PQL expression.

		This raises a ValueError if this is not possible (e.g., due to
		non-stepped intervals).
		"""
		res = set()
		for r in self.ranges:
			res.update(r.getValuesAsSet())
		return res

	def getSQL(self, colName, sqlPars):
		"""returns an SQL condition expressing this PQL constraint for colName.

		The parameters necessary are added to sqlPars.
		"""
		if len(self.ranges)==1: # Special case for SQL cosmetics
			return self.ranges[0].getSQL(colName, sqlPars)
		try:
			return "%s IN %%(%s)s"%(colName, base.getSQLKey(colName, 
				self.getValuesAsSet(), sqlPars))
		except ValueError:  # at least one open or non-stepped range
			return "(%s)"%" OR ".join(
				r.getSQL(colName, sqlPars) for r in self.ranges)


class PQLTextParIR(PQLPar):
	"""a PQL string parameter matching "google-like", "Information Retrieval".

	Basically, this matches the input and the database column as document
	vectors.  Correspondingly, ranges are disallowed.
	"""
	def getSQL(self, colName, sqlPars):
		try:
			docs = self.getValuesAsSet()
		except ValueError:
			# ranges were given; we don't support those with IR-searching
			raise base.LiteralParseError(colName, str(self), hint=
				"Ranges are not allowed with IR-matches (or did you want to"
				" to search for a slash?  In that case, please escape it)")

		keys = []
		for doc in docs:
			keys.append(base.getSQLKey(colName, doc, sqlPars))

		return "(%s)"%" OR ".join(
			"to_tsvector(%s) @@ plainto_tsquery(%%(%s)s)"%(
				colName,
				keyName)
			for keyName in keys)


class PQLIntPar(PQLPar):
	"""a PQL parameter containing an integer.

	steps in ranges are allowed.
	"""
	valParser = int
	stepParser = int


class PQLDatePar(PQLPar):
	"""a PQL parameter containing an integer.

	steps in ranges are allowed.
	"""
	valParser = staticmethod(literals.parseDefaultDatetime)

	@staticmethod
	def stepParser(val):
		return datetime.timedelta(days=float(val))


class PQLPositionPar(PQLPar):
	"""a PQL position parameter, as for SSA.

	Cones and intervals or real lists do not mix; we support STC-S 
	identifiers as qualifiers.

	The literals here are basically two-float lists.
	"""
	valParser = float

	def getSQL(self, colName, sqlPars):
		raise NotImplementedError("Ranges for PQL POS not implemented yet.")
	
	def getConeSQL(self, colName, sqlPars, coneSize):
		if self.qualifier and self.qualifier!='ICRS':
			# XXX TODO: implement at least a couple of common frames
			raise base.ValidationError("Cannot match against coordinates"
				" given in %s frame"%self.qualifier, self.destName)

		sizeName = base.getSQLKey("size", coneSize*DEG, sqlPars)
		parts = []
		if len(self.ranges)%2:
			raise base.ValidationError("PQL position values must be lists of"
				" length divisible by 2.", self.destName)
		lastCoo = None
		for r in self.ranges:
			if r.value is None:
				raise base.ValidationError("Ranges not allowed as cone centers",
					self.destName)
			if lastCoo is None:
				lastCoo = r.value
			else:
				parts.append("%s <-> %%(%s)s < %%(%s)s"%(colName,
					base.getSQLKey("pos", pgsphere.SPoint.fromDegrees(lastCoo, r.value), 
						sqlPars), sizeName))
				lastCoo = None
		return "(%s)"%" OR ".join(parts)


class PQLFloatPar(PQLPar):
	"""a PQL float parameter.

	This has a special getSQLForInterval method for cases like SSA's
	BAND.
	"""
	valParser = float

	def getSQLForInterval(self, lowerColName, upperColName, sqlPars):
		"""returns an SQL phrase against an interval in a table.
		"""
		if len(self.ranges)==1: # Special case for SQL cosmetics
			return self.ranges[0].getSQLForInterval(
				lowerColName, upperColName, sqlPars)
		else:
			return "(%s)"%" OR ".join(
				r.getSQLForInterval(lowerColName, upperColName, sqlPars) 
					for r in self.ranges)


def _makeFactory(parType):
	def factory(field, val, sqlPars):
		try:
			return parType.fromLiteral(val, field.name).getSQL(field.name, sqlPars)
		except ValueError:
			raise base.ui.logOldExc(utils.ValidationError(
				"Invalid input for type %s"
				" (valid PQL literals are described in the help)"%field.type, 
				field.name))
	return factory


sqlmunge.registerSQLFactory("pql-int", _makeFactory(PQLIntPar))
sqlmunge.registerSQLFactory("pql-float", _makeFactory(PQLFloatPar))
sqlmunge.registerSQLFactory("pql-string", _makeFactory(PQLPar))
sqlmunge.registerSQLFactory("pql-date", _makeFactory(PQLDatePar))


class ToPQLTypeConverter(typesystems.FromSQLConverter):
	typeSystem = "pqlexpr"
	simpleMap = {
		"smallint": "pql-int",
		"integer": "pql-int",
		"int": "pql-int",
		"bigint": "pql-int",
		"real": "pql-float",
		"float": "pql-float",
		"double precision": "pql-float",
		"double": "pql-float",
		"text": "pql-string",
		"char": "pql-string",
		"date": "pql-date",
		"timestamp": "pql-date",
		"pql-date": "pql-date",
		"pql-float": "pql-float",
		"pql-string": "pql-string",
	}

	def mapComplex(self, sqlType, length):
		if sqlType=="char":
			return "pql-string"
		if sqlType=="varchar":
			return "pql-string"

getPQLTypeFor = ToPQLTypeConverter().convert


def adaptInputKey(inputKey):
	"""returns inputKey changed to generate SQL for PQL-like expressions.

	This is used for buildFrom on CondDescs and renderers having
	parameterStyle pql.
	"""
	try:
		return inputKey.change(
			type=getPQLTypeFor(inputKey.type))
	except base.ConversionError:  # No vexpr type, leave things
		pass
	return inputKey


# Make the whole thing available to procDefs and such
import sys
from gavo import rscdef
rscdef.addProcDefObject("pql", sys.modules[__name__])
