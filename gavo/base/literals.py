"""
Functions taking strings and returning python values.

All of them accept None and return None for Nullvalue processing.

All of them leave values alone if they already have the right type.

This is usually used in conjunction with 
base.typesystems.ToPythonCodeConverter.
"""


import datetime
import re
import time

from gavo.base import excs
from gavo.base import texttricks


def parseInt(literal):
	if literal is None or (isinstance(literal, basestring) and not literal.strip()):
		return
	return int(literal)

def parseFloat(literal):
	if (literal is None or 
			(isinstance(literal, basestring) and not literal.strip())):
		return
	return float(literal)

_trueLiterals = set(["true", "yes", "t", "on", "enabled", "1"])
_falseLiterals = set(["false", "no", "f", "off", "disabled", "0"])
def parseBooleanLiteral(literal):
	"""returns a python boolean from some string.

	Boolean literals are strings like True, false, on, Off, yes, No in
	some capitalization.
	"""
	if literal is None or isinstance(literal, bool):
		return literal
	literal = literal.lower()
	if literal in _trueLiterals:
		return True
	elif literal in _falseLiterals:
		return False
	else:
		raise excs.LiteralParseError(
			"'%s' is no recognized boolean literal."%literal)


def parseUnicode(literal):
	if literal is None:
		return
	return unicode(literal)


def parseDefaultDate(literal):
	if literal is None or isinstance(literal, datetime.date):
		return literal
	return datetime.date(*time.strptime(literal, '%Y-%m-%d')[:3])


def parseDefaultDatetime(literal):
	if literal is None or isinstance(literal, datetime.datetime):
		return literal
	return datetime.datetime(
		*time.strptime(literal, '%Y-%m-%dT%H:%M:%S')[:6])


def parseDefaultTime(literal):
	if literal is None or isinstance(literal, datetime.time):
		return literal
	return datetime.time(*time.strptime(literal, '%H:%M:%S')[3:6])


def parseCooPair(soup):
	"""returns a pair of RA, DEC floats if they can be made out in soup
	or raises a value error.

	No range checking is done (yet), i.e., as long as two numbers can be
	made out, the function is happy.

	>>> parseCooPair("23 12")
	(23.0, 12.0)
	>>> parseCooPair("3.75 -12.125")
	(3.75, -12.125)
	>>> parseCooPair("3 25,-12 30")
	(51.25, -12.5)
	>>> map(str, parseCooPair("12 15 30.5 +52 18 27.5"))
	['183.877083333', '52.3076388889']
	>>> parseCooPair("3.39 -12 39")
	Traceback (most recent call last):
	ValueError: Invalid time with sepchar ' ': '3.39'
	>>> parseCooPair("12 15 30.5 +52 18 27.5e")
	Traceback (most recent call last):
	ValueError: 12 15 30.5 +52 18 27.5e has no discernible position in it
	>>> parseCooPair("QSO2230+44.3")
	Traceback (most recent call last):
	ValueError: QSO2230+44.3 has no discernible position in it
	"""
	soup = soup.strip()

	def parseFloatPair(soup):
		mat = re.match("(%s)\s*[\s,/]\s*(%s)$"%(texttricks.floatRE, 
			texttricks.floatRE), soup)
		if mat:
			return float(mat.group(1)), float(mat.group(2))

	def parseTimeangleDms(soup):
		timeangleRE = r"(?:\d+\s+)?(?:\d+\s+)?\d+(?:\.\d*)?"
		dmsRE = "[+-]?\s*(?:\d+\s+)?(?:\d+\s+)?\d+(?:\.\d*)?"
		mat = re.match("(%s)\s*[\s,/]?\s*(%s)$"%(timeangleRE, dmsRE), soup)
		if mat:
			try:
				return texttricks.timeangleToDeg(mat.group(1)), texttricks.dmsToDeg(
					mat.group(2))
			except excs.Error, msg:
				raise ValueError(str(msg))

	for func in [parseFloatPair, parseTimeangleDms]:
		res = func(soup)
		if res:
			return res
	raise ValueError("%s has no discernible position in it"%soup)


def _test():
	import doctest, literals
	doctest.testmod(literals)


if __name__=="__main__":
	_test()


__all__ = ["parseInt", "parseFloat", "parseBooleanLiteral", "parseUnicode",
	"parseDefaultDate", "parseDefaultTime", "parseDefaultDatetime",
	"parseCooPair"]
