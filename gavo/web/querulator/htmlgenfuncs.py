"""
This module contains condition generator classes.

Instances of these classes know how to emit HTML for forms giving values
to them and how to emit SQL for queries in which they participate.

They will usually end up within the expression trees generated in
sqlparse.
"""

import gavo
from gavo import sqlsupport


class ArgumentError(gavo.Error):
	"""is raised when improper arguments are given to a CondGen constructor.
	"""


class CondGen:
	"""is a condition generator.

	Condition generators are instanciated with a varying number of arguments,
	mostly by the SQL parser.  It is the responsibility of the parser to
	make sure the arguments are "good".  
	
	The only argument strictly necessary is a "name".  This can be any string
	(including the empty string).  It is used to identify the arguments
	across a form->user->query cycle.  It is probably a good idea to keep
	these names uniqe within a query, but this is left to the user.  Classes
	that use these names directly should probably raise an Error on empty
	names.

	All classes derived from CondGen should add to the set expectedKeys
	so that it reflects what 
	"""
	def __init__(self, name):
		self.name = name
		self.expectedKeys = set()

	def _ensureNonEmptyName(self):
		if not self.name:
			raise ArgumentError("%s needs non-empty name"%self.__class__.__name__)

	def getExpectedKeys(self):
		return self.expectedKeys


class OperatorCondGen(CondGen):
	"""is a CondGen using some kind of operator.

	It is not useful in itself (it's abstract, if you will).

	This covers cases like foo in Bla, bar<Baz.

	Classes deriving from this need not implement an asSql method but
	just a _getSqlOperand method.  This should return a string for the
	second operand.
	"""
	def __init__(self, name, sqlExpr, operator):
		CondGen.__init__(self, name)
		self.sqlExpr = sqlExpr
		self.operator = operator

	def asSql(self, context):
		for key in self.expectedKeys:
			if not key in availableKeys:
				return ""
		return "%s %s %s"%(self.sqlExpr, self.operator, 
			self._getSqlOperand(context))

	def _getSqlOperand(self, context):
		return %%(%s)s"%self.name


class Choice(OperatorCondGen):
	"""returns a form element to choose from args.

	If the operator is one accepting sets (like IN), you will be able
	to select multiple items.

	Additional Arguments:
	
	* choices --a sequence of 2-tuples of (value, title), where value is 
	  what the form recipient gets and title is what the user sees.
	* size -- an int saying how many rows are visible.
	"""

	setOperators = set(["in"])

	def __init__(self, name, sqlExpr, operator, choices, size=1):
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
		self.choices, self.size = choices, size
		if self.operator in self.setOperators:
			self.allowMulti = True
		self._ensureNonEmptyName()
		self.expectedKeys.add(self.name)

	def asHtml(self):
		selOpt = " size='%d'"%size
		if self.allowMulti:
			selOpt += " multiple='yes'"
		return '<select name="%s" %s>\n%s\n</select>'%(
			self.name,
			selOpt,
			"\n".join(["<option value=%s>%s</option>"%(repr(val), opt) 
				for opt, val in choices]))

	def _getSqlOperand(self, context):
		if self.allowMulti:
			return "(%%(%s)s)"%self.name
		else:
			return "%%(%s)s"%self.name


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
		' and <input type="text" size="10" name="%(fieldName)s-upper">'
		'<div class="legend">Leave any empty for open range.</div>')


def daterange(default=None):
	"""returns form code for a range of floats.

	The naming convention here is reproduced in sqlparse.TwoFieldTest.
	"""
	return ('<input type="text" size="10" name="%(fieldName)s-lower">'
		' and <input type="text" size="10" name="%(fieldName)s-upper">'
		'<div class="legend">Leave any empty for open range.  Use'
		' date format YYYY-MM-DD</div>')


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


class SexagConeSearch:
	"""Let's experiment a bit with making the html generator functions
	smarter -- in addition to spewing out html, why shouldn't they
	spit out the SQL as well?  Really, they know best what kind of
	SQL they should generate, no?  This one here is the prototype.
	"""
	def __call__(self):
		return ('<input type="text" size="5" name="SRminutes" value="1">'
			' arcminutes around<br>'
			'<input type="text" size="30" name="sexagMixedPos">'
			'<div class="legend">(Position sexagesimal RA and dec in source equinox'
			' with requried sign on dec, or simbad identifier)</div>')
	
	def asCondition(self, context):
		if context.checkArguments(["sexagMixedPos", "SRminutes"]):
			return "Position %s arcminutes around %s"%(context.getfirst("SRminutes"),
				context.getfirst("sexagMixedPos"))
		return ""
