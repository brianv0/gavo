"""
This module provides a function to convert strings into python types
that in turn are ingestable by common dbapi2 application for input into
SQL databases.  The types themselves are described through SQL types.

Basically, the idea is to control the conversion from some kind of
literal to whatever the database holds.
"""

from mx import DateTime
import re

import gavo
from gavo import logger

def _make_dateFromString(datestr, datePatterns=[
		re.compile("(?P<y>\d\d\d\d)-(?P<m>\d\d)-(?P<d>\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d\d\d)$"),
		re.compile("(?P<m>\d\d)/(?P<d>\d\d)/(?P<y>\d\d)$"),
		]):
	"""
	"""
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


def _make_dateTimeFromString(literal):
	"""returns a mx.DateTime object from an ISO timestamp.
	"""
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
			"spuriousBlanks": self._parse_spuriousBlanks,
		}

	def _parse_TrueFalse(self, literal):
		"""is a literalForm parser for boolean values.
		"""
		if literal.lower()=="true" or literal.lower()=="yes":
			return True
		elif literal.lower()=="false" or literal.lower()=="no":
			return False
		else:
			raise gavo.Error("%s is not a valid truefalse boolean literal")

	def _parse_spuriousBlanks(self, literal):
		"""is a literalForm parser for values with blanks that should be
		ignored.
		"""
		return literal.replace(" ", "")

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
		"boolean": bool,
		"date": _make_dateFromString,
		"timestamp": _make_dateTimeFromString,
	}

	def _make_string(self, literal):
		if self.encoding:
			return str(literal).decode(self.encoding)
		return str(literal)

	def _computeConverter(self, sqlType):
		"""returns a function converting a string into something suitable
		for ingestion as sqlType.
		"""
		sqlType = sqlType.lower()
		if sqlType in self.simpleConverters:
			return self.simpleConverters[sqlType]
		if sqlType.startswith("numeric"):
			return float   # XXXX this may lose precision -- gmp?
		if (sqlType.startswith("varchar") or sqlType.startswith("character varying")
				or sqlType.startswith("character") or sqlType.startswith("char")
				or sqlType=="text"):
			return self._make_string
		logger.warning("Conversion to unknown type %s requested.  Returning"
			" identity."%sqlType)
		return lambda a: a


	def makePythonVal(self, literal, sqlType, literalForm=None):
		"""returns a python value suitable for later ingestion as sqlType.

		If literalForm is given, the literal may be preprocessed -- this
		may be necessary for, e.g. crazy date formats or hour angles.

		We let the NULL value (None) pass through.
		"""
		if literal is None:
			return None
		if literalForm=="do not touch":
			return literal
		literal = self.literalMogrifiers[literalForm](literal)
		return self._computeConverter(sqlType)(literal)
