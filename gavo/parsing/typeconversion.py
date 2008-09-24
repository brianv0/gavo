"""
This module provides a function to convert strings into python types
that in turn are ingestable by common dbapi2 applications for input into
SQL databases.  The types themselves are described through SQL types.

Basically, the idea is to control the conversion from some kind of
literal to whatever the database holds.
"""

from mx import DateTime
import math
import re

import gavo
from gavo import utils
from gavo import record
from gavo import logger
from gavo import coords


def make_timeDelta(days=0, hours=0, minutes=0, seconds=0):
	return DateTime.DateTimeDelta(days, hours, minutes, seconds)


def make_dateFromString(datestr, datePatterns=[
		re.compile("(?P<y>\d\d\d\d)-(?P<m>\d\d)-(?P<d>\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d)$"),
		]):
	"""
	"""
	if not isinstance(datestr, basestring):
		return datestr
	for pat in datePatterns:
		mat = pat.search(datestr)
		if mat:
			yearS, monthS, dayS = mat.group("y"), mat.group("m"), mat.group("d")
			if len(yearS)==2:
				yearS = "19"+yearS
			break
	else:
		raise gavo.Error("Date %s has unsupported format"%datestr)
	dateobj = DateTime.Date(int(yearS), int(monthS), int(dayS))
	return dateobj


def make_dateTimeFromString(literal):
	"""returns a mx.DateTime object from an ISO timestamp.
	"""
	if not isinstance(literal, basestring):
		return literal
	return DateTime.Parser.DateTimeFromString(literal)


class LiteralParser:
	"""is a class mapping literals to python values.

	It knows about literalForms (which characterize the input; these
	might handle crazy date formats, blanks within numbers, etc) and
	python types for the SQL dbtypes that strings after conversion
	from their literalForms are converted in.  These python types
	should be understood by the SQL wrapper used.

	The public interface to the class consists of the makePythonVal
	method.

	To do this, we keep a registry literalMogrifiers of methods converting
	literalForms to valid literals for the python value constructors.  The
	names of these methods should start with _parse_

	Since parsing sql type identifiers is a bit too much for a dictionary,
	the value constructors are returned by the _computeConverter method.
	Value constructors are either functions or methods with names starting
	with _make_.
	"""
	def __init__(self, encoding=None):
		self.encoding = encoding
		self.literalMogrifiers = {
			None: lambda a: a,
			"truefalse": self._parse_TrueFalse,
			"emptyfalse": self._parse_emptyfalse,
			"spuriousBlanks": self._parse_spuriousBlanks,
			"hourangle": self._parse_timeangle,
			"timeangle": self._parse_timeangle,
			"sexagesimal": self._parse_sexagesimal,
			"JYear": self._parse_JYear,
		}

	def _parse_timeangle(self, literal):
		"""returns a float in degrees from an h:m:s.sss literal (various
		separators supported).
		"""
		sepChar = None
		if ":" in literal:
			sepChar = ":"
		return coords.timeangleToDeg(literal, sepChar)
	
	def _parse_sexagesimal(self, literal):
		"""returns a float in degrees from a dms literal.
		"""
		sepChar = None
		if ":" in literal:
			sepChar = ":"
		return coords.dmsToDeg(literal, sepChar)
	
	def _parse_emptyfalse(self, literal):
		"""returns true if literal has characters other than whitespace.
		"""
		return not not literal.strip()

	def _parse_TrueFalse(self, literal):
		"""returns boolean values from literals like True, yes, no, False.
		"""
		return record.parseBooleanLiteral(literal)

	def _parse_JYear(self, literal):
		"""returns a DateTime instance for a fractional (julian) year.
		
		This refers to time specifications like J2001.32.
		"""
		return utils.dateTimeToJYear(literal)

	def _parse_spuriousBlanks(self, literal):
		"""removes all blanks from a literal (use it if, e.g. people
		inserted blanks into long numbers.
		"""
		if isinstance(literal, basestring):
			return literal.replace(" ", "")
		return literal

	simpleConverters = {
		"int" : int,
		"smallint" : int,
		"integer": int,
		"bigint": long,
		"real": float,
		"float": float,
		"float32": float,
		"float64": float,
		"double": float,
		"double precision": float,
		"boolean": bool,
		"date": make_dateFromString,
		"timestamp": make_dateTimeFromString,
		"vexpr-string": lambda a: a,
		"vexpr-date": lambda a: a,
		"vexpr-float": lambda a: a,
		"file": lambda a: a,
	}

	def _buildArrayParser(self, type, length):
		"""returns a function parsing an array of type.  Length so far is
		ignored.

		Arrays literals are, for now, represented as whitespace-seperated 
		entities.

		It is not clear what a sane handling of length should look like --
		postgres ignores it as sell.
		"""
		# XXX TODO: I guess we should parse SQL serializations here.  For now, this
		# isn't really used in the first place because any array-like things
		# zipping past here will be a python sequence already.
		if not type in self.simpleConverters:
			return None
		atomicConverter = self.simpleConverters[type]
		def convertArray(literal):
			if not isinstance(literal, basestring):
				return literal
			return [atomicConverter(v) for v in literal.split()]
		return convertArray

	def _make_string(self, literal):
		if self.encoding:
			if isinstance(literal, str):
				return literal.decode(self.encoding)
		return unicode(literal)

	def _identity(self, a):
		return a

	def _computeConverter(self, sqlType):
		"""returns a function converting a string into something suitable
		for ingestion as sqlType.
		"""
		sqlType = sqlType.lower()
		if sqlType=="raw":
			return self._identity
		if sqlType in self.simpleConverters:
			return self.simpleConverters[sqlType]
		if sqlType.startswith("numeric"):
			return float   # XXXX this may lose precision -- gmp?
		if (sqlType.startswith("varchar") or sqlType.startswith("character varying")
				or sqlType.startswith("character") or sqlType.startswith("char")
				or sqlType=="text"):
			return self._make_string
		mat = re.match(r"(.*)[[(](\d+|\*|)[])]", sqlType)
		if mat:
			conv = self._buildArrayParser(mat.group(1), mat.group(2))
			if conv:
				return conv
		logger.warning("Conversion to unknown type %s requested.  Returning"
			" identity."%sqlType)
		return self._identity

	def makePythonVal(self, literal, sqlType, literalForm=None):
		"""returns a python value suitable for later ingestion as sqlType.

		If literalForm is given, the literal may be preprocessed -- this
		may be necessary for, e.g. crazy date formats or angles as time.

		We let the NULL value (None) pass through.
		"""
		if literal is None:
			return None
		if literalForm=="do not touch":
			return literal
		try:
			literal = self.literalMogrifiers[literalForm](literal)
		except KeyError, msg:
			raise gavo.Error("Invalid or unknown literal form %s (%s)"%(
				literalForm, msg))
		return self._computeConverter(sqlType)(literal)
	
	def getLiteralDocs(self, underliner):
		return utils.formatDocs([(literalForm, method.__doc__)
			for literalForm, method in self.literalMogrifiers.iteritems()
				if literalForm],
			underliner)


asciiLiteralParser = LiteralParser(encoding="utf-8")


if __name__=="__main__":
	import sys
	if len(sys.argv)>1 and sys.argv[1]=="docs":
		underliner = "."
		if len(sys.argv)>2:
			underliner = sys.argv[2]
		print asciiLiteralParser.getLiteralDocs(underliner)
