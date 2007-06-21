"""
This module contains condition generator classes.

Instances of these classes know how to emit HTML for forms giving values
to them and how to emit SQL for queries in which they participate.

They will usually end up within the expression trees generated in
sqlparse.
"""

import re
import compiler
import compiler.ast
import compiler.pycodegen

import gavo
from gavo import sqlsupport
from gavo import coords
from gavo.web import querulator


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

	def asCondition(self, context):
		return ""

	def _contextMatches(self, context):
		return context.checkArguments(self.expectedKeys)

	def __iter__(self):
		"""stops any iteration.

		This is needed to let us live in parse trees without messing their
		traversal up.
		"""
		raise StopIteration


class OperatorCondGen(CondGen):
	"""is a CondGen using some kind of operator.

	It is not useful in itself (it's abstract, if you will).

	This covers cases like foo in Bla, bar<Baz.

	The default implementation assumes you only have one key called
	name.  If that is not true for your case, you need to override
	at least _getSqlOperand and asCondition.
	"""

	setOperators = set(["in"])

	def __init__(self, name, sqlExpr, operator):
		CondGen.__init__(self, name)
		self._ensureNonEmptyName()
		self.sqlExpr = sqlExpr
		self.operator = operator
		self.takesSets = self.operator.lower() in self.setOperators
		self.expectedKeys.add(self.name)

	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		secondOperand, args = self._getSqlOperand(context)
		return "%s %s %s"%(self.sqlExpr, self.operator, secondOperand
			), args

	def _getVal(self, context):
		if self.takesSets:
			return context.getlist(self.name)
		else:
			return context.getfirst(self.name)

	def asCondition(self, context):
		if not self._contextMatches(context):
			return ""
		return "%s %s %s"%(self.sqlExpr, self.operator.lower(), 
			self._getVal(context))

	def _getSqlOperand(self, context):
		return "%%(%s)s"%self.name, {self.name: self._getVal(context)}


class Choice(OperatorCondGen):
	"""returns a form element to choose from args.

	If the operator is one accepting sets (like IN), you will be able
	to select multiple items.

	Additional Arguments:
	
	* choices --a sequence of 2-tuples of (value, title), where value is 
	  what the form recipient gets and title is what the user sees.
	* size -- an int saying how many rows are visible.
	"""
	def __init__(self, name, sqlExpr, operator, choices, size=1):
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
		self.choices, self.size = choices, size
		self.expectedKeys.add(self.name)

	def asHtml(self):
		selOpt = " size='%d'"%self.size
		if self.takesSets:
			selOpt += " multiple='yes'"
		formItem = '<select name="%s" %s>\n%s\n</select>'%(
			self.name,
			selOpt,
			"\n".join(["<option value=%s>%s</option>"%(repr(val), opt) 
				for opt, val in self.choices]))
		doc = ""
		if self.takesSets:
			doc = ('<div class="legend">(Zero or more choices allowed; '
				'try shift-click, control-click)</div>')
		return formItem+doc


class SimpleChoice(Choice):
	def __init__(self, name, sqlExpr, operator, choices):
		Choice.__init__(self, name, sqlExpr, operator,
			[(choice, choice) for choice in choices])


class ChoiceFromDb(Choice):
	def __init__(self, name, sqlExpr, operator, query, 
			prependAny=False, size=1):
		Choice.__init__(self, name, sqlExpr, operator, self._buildChoices(
			query, prependAny), size=size)
		if self.takesSets and size==1:
			self.size=3
	
	def _buildChoices(self, query, prependAny):
		querier = sqlsupport.SimpleQuerier()
		validOptions = [(opt[0], opt[0]) 
			for opt in querier.query(query).fetchall()]
		validOptions.sort()
		if prependAny:
			validOptions.insert(0, ("ANY", ""))
		return validOptions


class Date(OperatorCondGen):
	def asHtml(self):
		return ('<input type="text" size="20" name="%s"> '
			'<div class="legend">(YYYY-MM-DD)</div>')%self.name


class StringField(OperatorCondGen):
	def __init__(self, name, sqlExpr, operator, size=30):
		self.size = size
		OperatorCondGen.__init__(self, name, sqlExpr, operator)

	def asHtml(self):
		return '<input type="text" size="%d" name="%s">'%(self.size, self.name)


class PatternField(StringField):
	def asHtml(self):
		return ('<input type="text" size="%d" name="%s">'
			'<div class="legend">(_ for any char, %% for'
			' any sequence of chars)</div>')%(self.size, self.name)


class IntField(OperatorCondGen):
	def asHtml(self):
		return '<input type="text" size="5" name="%s">'%self.name


class FloatField(OperatorCondGen):
	def __init__(self, name, sqlExpr, operator, default=""):
		self.default = default
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
	
	def asHtml(self):
		return '<input type="text" size="10" name="%s" value="%s">'%(
			self.name, self.default)


class BetweenCondGen(CondGen):
	"""is a base for CodeGens that generate upper and lower bounds.

	Both upper and lower bounds are optional, the queries will fall
	back to simple comparisons if one is empty.

	This class currently only supports the BETWEEN operator.

	This should work for any ranges of ints, floats, etc.
	"""
	def __init__(self, name, sqlExpr, operator):
		CondGen.__init__(self, name)
		self.sqlExpr, self.operator = sqlExpr, operator
		if self.operator.lower()!="between":
			raise "%s only make sense with the BETWEEN SQL operator"%(
				self.__class__.__name__)
		self.expectedKeys.add(self.name+"-lower")
		self.expectedKeys.add(self.name+"-upper")
	
	def asSql(self, context):
		lowerKey, upperKey = "%s-lower"%self.name, "%s-upper"%self.name
		qString = ""
		argDict = {}
		if lowerKey in context:
			argDict[lowerKey] = context.getfirst(lowerKey)
		if upperKey in context:
			argDict[upperKey] = context.getfirst(upperKey)
		if lowerKey in argDict and upperKey in argDict:
			qString = "%s BETWEEN %%(%s)s AND %%(%s)s"%(
				self.sqlExpr, lowerKey, upperKey)
		elif lowerKey in argDict:
			qString = "%s >= %%(%s)s"%(self.sqlExpr, lowerKey)
		elif upperKey in argDict:
			qString = "%s <= %%(%s)s"%(self.sqlExpr, upperKey)
		return qString, argDict

	def asHtml(self):
		return ('<input type="text" size="10" name="%s-lower">'
				' and <input type="text" size="10" name="%s-upper">'
				'<div class="legend">Leave any empty for open range.</div>'%(
			self.name, self.name))

	def asCondition(self, context):
		q, vals = self.asSql(context)
		return q%vals


class DateRange(BetweenCondGen):
	def asHtml(self):
		return ('<input type="text" size="10" name="%s-lower">'
			' and <input type="text" size="10" name="%s-upper">'
			'<div class="legend">Leave any empty for open range.  Use'
			' date format YYYY-MM-DD</div>')%(self.name, self.name)


def buildConeSearchQuery(prefix, ra, dec, sr):
	"""returns an SQL fragment for a cone search around the given
	coordinates.

	This assumes the table being queried satisfies the positions interface.

	This does not have any idea of equinoxes and the like.  That would
	have to be handled on a higher level.
	"""
	c_x, c_y, c_z = coords.computeUnitSphereCoords(float(ra), float(dec))
	return ("sqrt((%%(%sc_x)s-c_x)^2+(%%(%sc_y)s-c_y)^2+"
		"(%%(%sc_z)s-c_z)^2)"%(prefix, prefix, prefix)+
		"<= %%(%ssr)s"%prefix), {
			"%sc_x"%prefix: c_x,
			"%sc_y"%prefix: c_y,
			"%sc_z"%prefix: c_z,
			"%ssr"%prefix: sr}


class SexagConeSearch(CondGen):
	"""is a CondGen that does a cone search on sexagesimal coordinates.
	"""
	def __init__(self, name=""):
		CondGen.__init__(self, name)
		self.expectedKeys.add("%sSRminutes"%self.name)
		self.expectedKeys.add("%ssexagMixedPos"%self.name)

	def asHtml(self):
		return ('<input type="text" size="5" name="%sSRminutes" value="1">'
			' arcminutes around<br>'
			'<input type="text" size="30" name="%ssexagMixedPos">'
			'<div class="legend">(Position sexagesimal RA and dec in source equinox'
			' with requried sign on dec, or simbad identifier)</div>')%(
			self.name, self.name)
	
	def asCondition(self, context):
		if self._contextMatches(context):
			return "Position %s arcminutes around %s"%(
				context.getfirst("%sSRminutes"%self.name),
				context.getfirst("%ssexagMixedPos"%self.name))
		return ""
	
	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		pos = context.getfirst("%ssexagMixedPos"%self.name)
		mat = re.match("(.*)([+-].*)", pos)
		try:
			ra, dec = coords.hourangleToDeg(mat.group(1)), coords.dmsToDeg(
				mat.group(2))
		except (AttributeError, ValueError):
			try:
				from gavo import simbadinterface
				ra, dec = simbadinterface.getSimbadPositions(pos)
			except KeyError:
				raise querulator.Error("Sexagesimal mixed positions must"
					" have a format like hh mm ss[.ddd] [+-]dd mm ss[.mmm] (the"
					" sign is important).  %s does not appear to be of this format,"
					" and also cannot be resolved by Simbad."%repr(pos))
		try:
			sr = float(context.getfirst("%sSRminutes"%self.name))/60
		except ValueError:
			raise querulator.Error("Search radius must be given as arcminutes"
				" float. %s is invalid."%repr(context.getfirst("SRminutes")))
		return buildConeSearchQuery(self.name, ra, dec, sr)


def makeCondGen(name, cType, toks):
	"""generates a CondGen.

	name is the name stem for the arguments, cType is "operator" or "predefined",
	and toks a a list of tokens.

	If cType is "operator", then toks[0] is an sqlExpression, toks[1] an
	operator, and toks[2] a python expression.

	If cType is "predefined", then toks[0] contains the python expression
	to build the CondGen from.
	"""
	def findFuncNode(node):
		for child in node.getChildNodes():
			if isinstance(child, compiler.ast.CallFunc):
				return child
			funcNode = findFuncNode(child)
			if funcNode:
				return funcNode

	def getConstructionCode(pythonExpr, additionalArgs):
		pythonExpr = compiler.parse(toks[-1], "eval")
		funcNode = findFuncNode(pythonExpr)
		funcNode.args[0:0] = additionalArgs
		return pythonExpr
	
	if cType=="operator":
		ast = getConstructionCode(toks[-1], [compiler.ast.Const(value=name),
			compiler.ast.Const(value=toks[0]), compiler.ast.Const(value=toks[1])])
	else:
		ast = getConstructionCode(toks[-1], [compiler.ast.Const(name)])
	ast.filename = "<Generated>"  # Silly fix for gotcha in compiler
	gen = compiler.pycodegen.ExpressionCodeGenerator(ast)
	return eval(gen.getCode())


if __name__=="__main__":
	import operator
	print makeCondGen("foo", "operator", ['targName', 'in',
		'ChoiceFromDb("select distinct targName from sophie.data", size=6)'])

