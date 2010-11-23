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
"""

import re
import urllib

from gavo import base


QUALIFIER_RE = re.compile("([^;]*)(;[^;]*)?$")
LIST_RE = re.compile("([^,]*),")
RANGE_RE = re.compile("([^/]*)(/[^/]*)?(/[^/]*)?$")


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

	The attributes by default are string-valued or None; if you passed
	valParser (and possibly stepParser), they are whatever these
	functions returned.
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

		For the meaning of the arguments, see PQLRes.fromLiteral.
		"""
		if literal=="":
			return cls(value="")
		mat = RANGE_RE.match(literal)
		if not mat:
			raise base.LiteralParseError(destName, literal,
				hint="PQL ranges roughly have the form [start][/stop[/stop]]."
				" Literal slashes need to be escaped (as %2f).")
		vals = mat.groups()

		if vals[1] is None and vals[2] is None:
			return cls(value=_parsePQLValue(vals[0], vp=valParser))
		else:
			start, stop, step = vals
		try:
			return cls(
				start=_parsePQLValue(start, vp=valParser), 
				stop=_parsePQLValue(stop, 1, vp=valParser), 
				step=_parsePQLValue(step, 1, vp=stepParser))
		except ValueError, ex:
			raise base.LiteralParseError("range within %s"%destName, literal,
				hint=str(ex))

	def isSetExpressible(self):
		return self.value is not None or self.step is not None


class PQLRes(object):
	"""a representation for PQL expressions.

	PQLRes objects have an attribute qualifier (None or a string),
	and an attribute ranges, a list of PQLRange objects.
	
	As a client, you will ususally construct PQLRes objects using the
	fromLiteral class method; it takes a PQL literal and a name to be 
	used for LiteralParseErrors it may raise.
	"""
	def __init__(self, ranges, qualifier=None):
		self.qualifier = qualifier
		self.ranges = ranges

	def __eq__(self, other):
		return (isinstance(other, PQLRes)
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

	@classmethod
	def fromLiteral(cls, val, destName, valParser=str, stepParser=None):
		"""returns a parsed representation of a literal in PQL range-list syntax.

		val is a string containing the PQL expression, destName is a name to
		be used for the LiteralParseErrors the function raises when there are
		syntax errors in val.

		valParser is a function turning a value literal into a value.  It does
		not need to turn the empty string to None, since that is done by the
		machinery; bad values should raise a ValueError.  It defaults to str.
		stepParser is the same thing, except it is used to parse the stride
		of intervals.  It defaults to None, meaning "same as valParser" (they
		need to be different for dates).
		"""
		if val is None:
			return None
		if stepParser is None:
			stepParser = valParser

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
						valParser, stepParser))
			except base.LiteralParseError, ex:
				ex.pos = rangeMat.start()
				raise
		ranges.append(
			PQLRange.fromLiteral(listLiteral[rangeMat.end():], destName,
				valParser, stepParser))
		return cls(ranges, qualifier)

	def isSetExpressible(self):
		"""returns True if all ranges are expressible as discrete sets.
		"""
		for r in self.ranges:
			if not r.isSetExpressible():
				return False
		return True

	def iterClauses(self):
		if self.allRangesAreSimple():
			raise NotImplementedError
		else:
			raise NotImplementedError


parsePQL = PQLRes.fromLiteral

