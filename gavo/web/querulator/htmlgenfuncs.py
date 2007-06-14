"""
This module contains html generator functions.

These functions generate the form items for HTML forms within the querulator.
They are called from qusqlparse.CondText.asHtml, which in turn gets
their names and arguments from {{...}}-fields within the query template.
"""

from gavo import sqlsupport


def choice(choices, allowMulti=False, size=1):
	"""returns a form element to choose from args.

	choice is a sequence of 2-tuples of (value, title), where value is what the
	form recipient gets and title is what the user sees.

	If allowMulti is True, 
	"""
	selOpt = " size='%d'"%size
	if allowMulti:
		selOpt += " multiple='yes'"
	return '<select name="%%(fieldName)s" %s>\n%s\n</select>'%(
		selOpt,
		"\n".join(["<option value=%s>%s</option>"%(repr(val), opt) 
			for opt, val in choices]))


def simpleChoice(*choices):
	return choice([(choice, choice) for choice in choices])


def date():
	return ('<input type="text" size="20" name="%(fieldName)s"> '
		'<div class="legend">(YYYY-MM-DD)</div>')


def stringfield(size=30):
	return '<input type="text" size="%d" name="%%(fieldName)s">'%size

def pattern(size=20):
	return stringfield(size)+('<div class="legend">(_ for any char, %% for'
			' any sequence of chars)</div>')

def intfield():
	return '<input type="text" size="5" name="%(fieldName)s">'


def floatfield(default=None):
	return '<input type="text" size="10" name="%(fieldName)s">'


def floatrange(default=None):
	"""returns form code for a range of floats.

	The naming convention here is reproduced in sqlparse.TwoFieldTest.
	"""
	return ('<input type="text" size="10" name="%(fieldName)s-lower">'
		' to <input type="text" size="10" name="%(fieldName)s-upper">')


def choiceFromDb(query, prependAny=False, allowMulti=False, size=1):
	querier = sqlsupport.SimpleQuerier()
	validOptions = [(opt[0], opt[0]) 
		for opt in querier.query(query).fetchall()]
	validOptions.sort()
	if prependAny:
		validOptions.insert(0, ("ANY", ""))
	return choice(validOptions, allowMulti=allowMulti, size=size)


def choiceFromDbWithAny(query):
	return choiceFromDb(query, prependAny=True)


def choiceFromDbMulti(query, size=3):
	return choiceFromDb(query, prependAny=False, allowMulti=True,
		size=size)+('<div class="legend">(Zero or more choices allowed; '
			'try shift-click, control-click)</div>')
