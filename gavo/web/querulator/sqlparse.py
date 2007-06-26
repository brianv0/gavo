"""
This module contains code to parse SQL templates for the querulator

The fragment of SQL we understand is still quite small.

All relevant parts of the query are parsed into classes that embed
one another and have asSql and asHtml methods.  Their constructors
always take token lists generated from pyparsing, usually flattened into
argument lists (i.e., *args).  Thus, their constructors are used as
parseActions for pyparsing (with a trivial lambda wrapper).

Note that there is a test suite for that grammar -- expand it, and run
it each time you change something on the grammar.  It's easy to get this
stuff wrong.
"""

import sys
import operator
from pyparsing import Word, Literal, Optional, alphas, CaselessKeyword,\
	ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,\
	Suppress, Keyword, Forward, QuotedString, Group, printables, nums,\
	CaselessLiteral, ParseException

import pyparsing

from gavo import utils
from gavo.web import querulator
from gavo.web.querulator import condgens


def _joinChildren(s, loc, toks):
	"""is a parse action that joins all elements of the ParseResult toks.
	"""
	return "".join(toks)

def _joinChildrenBlank(s, loc, toks):
	"""is a parse action that joins all elements of the ParseResult toks with
	blanks.
	"""
	return " ".join(toks)


def debugConstructor(cons, *args):
	print ">>>>", cons.__name__, args
	return cons(*args)


# SQL literals
literalSelect = CaselessKeyword("SELECT")
literalWhere = CaselessKeyword("WHERE")
literalFrom = CaselessKeyword("FROM")
between = CaselessKeyword("BETWEEN")
inOp = CaselessKeyword("IN")
likeOp = CaselessKeyword("LIKE")
andOp = CaselessKeyword("AND")
orOp = CaselessKeyword("OR")

# Literals for templating
fieldStart = Literal("{{")
fieldEnd = Literal("}}")

# SQL names
sqlName = Word(srange("[a-zA-Z_]"), srange("[a-zA-Z0-9_]"))
qualifiedSqlName = sqlName + "." + sqlName
sqlId = qualifiedSqlName | sqlName
sqlId.setParseAction(_joinChildren)

# productions for parsing WHERE clauses -- leading up to processedCondition
# that describes a {{...}}-fragment in WHERE
condTitle = SkipTo("|")
pythonCode = SkipTo("}}")
relation = (Literal("<=") | Literal(">=") | Literal(">") | Literal("<") 
	| Literal("=") | likeOp | inOp | between )
sqlOpTest = sqlId + relation + pythonCode
predefinedTest = pythonCode.copy()
conditionDescription = condTitle + Suppress("|") + ( sqlOpTest 
	| predefinedTest )
processedCondition = (Suppress(fieldStart) + conditionDescription + 
	Suppress(fieldEnd))

# very simple minded SQL expressions within select lists
escapeSeq = Literal("\\") + Word(printables+" ", exact=1)
escapeSeq.setParseAction(lambda s, p, toks: toks[1])
noEscapeStuff = SkipTo( escapeSeq | "|")
sqlExpression = noEscapeStuff + ZeroOrMore(escapeSeq + noEscapeStuff)
sqlExpression.setParseAction(_joinChildren)

# productions for parsing select lists
selectItem = (sqlExpression + Suppress("|") + SkipTo("|") + Suppress("|")+
	sqlId)
selectItemField = Suppress(fieldStart)+selectItem+Suppress(fieldEnd)
selectItems = selectItemField + ZeroOrMore(Suppress(",") + selectItemField)

# productions for parsing literal SQL conditions (those are just copied
# over)
sqlNumber = Word(nums+".Ee")
sqlAtom = sqlId | QuotedString(quoteChar='"', escChar="\\",
	unquoteResults=False) | QuotedString(quoteChar="'", escChar="\\",
	unquoteResults=False) | sqlNumber
literalCondition = sqlAtom + relation + sqlAtom

# productions leading up to clauses (which matches anything after a WHERE)
clauses = Forward()
parenExpr = Suppress('(') + clauses + Suppress(')')
clause = ( processedCondition | literalCondition | parenExpr)

andExpr = clause + ZeroOrMore( andOp + clause ) 
clauses << andExpr + ZeroOrMore( orOp + andExpr )

whereClauses = clauses.copy()

# toplevel productions
dbName = sqlId
simpleSql = (Suppress(literalSelect) + selectItems + Suppress(literalFrom) + 
	dbName + Suppress(literalWhere) + whereClauses + StringEnd())


# Cosmetics for debugging purposes
clause.setName("Condition")
clauses.setName("WHERE expression")
andExpr.setName("AND expression")
literalCondition.setName("Literal condition")
processedCondition.setName("Processed condition")
sqlId.setName("Sql identifier")
simpleSql.setName("SQL statement")
parenExpr.setName("()")

if False:
	clauses.setDebug(True)
	parenExpr.setDebug(True)
	andExpr.setDebug(True)
	clause.setDebug(True)
	literalCondition.setDebug(True)
	processedCondition.setDebug(True)
	simpleSql.setDebug(True)
	andOp.setDebug(True)
	orOp.setDebug(True)


predefinedTest.setParseAction(lambda s, loc, toks:
	[("predefined", toks)])
sqlOpTest.setParseAction(lambda s, loc, toks:
	[("operator", toks)])


class ParseNode:
	"""is an abstract base class for nodes in the SQL parse tree.

	The common interface all parse nodes have to support is:
	 * __repr__
	 * asHtml -- returns a string containing HTML for use in a form
	   to set variables within the node
	 * asSql -- returns a string containing an SQL query fragment and a
	   dictionary with the values to fill in suitable for cursor.execute
	 * getChildren -- returns a list of all children (either ParseNodes or
	   string instances).
	
	You'll get getChildren for free when you define the children attribute.

	Nodes that expect input must also define getQueryInfo.  It should return
	a dictionary mapping query keys to tuples.  The first element of the tuple 
	must be either 'a' (atomic) or 'l' (list) depending on whether the SQL
	query expects a single or a compound value.  Further elements may be defined
	as necessary.
	"""
	def getChildren(self):
		return self.children
	
	def __iter__(self):
		"""implements a preorder traverse of the parse tree.
		"""
		for child in self.getChildren():
			yield child
			if not isinstance(child, basestring):
				for grandchild in child:
					yield grandchild

	def copy(self):
		"""returns a (typically shallow) copy of self.

		This default implementation tries to construct the copy with
		the children as arguments.  If that won't work because children
		is somehow computed, the deriving class must provide an implementation
		of its own.
		"""
		return self.__class__(*self.children)


class Condition(ParseNode):
	"""is a single condition for the query, consisting of a test and
	a description.
	"""
	def __init__(self, description, testDescr):
		cType, toks = testDescr
		self.description = description
		defaultBase = self.description.encode("hex")
		self.condTest = condgens.makeCondGen(defaultBase, cType, toks)
		self.children = [self.description, self.condTest]

	def __repr__(self):
		return "<Condition '%s', %s>"%(self.description, repr(self.condTest))
	
	def asHtml(self, context):
		return ('<div class="condition"><div class="clabel">%s</div> '
			'<div class="quwidget">%s</div></div>')%(
			self.description,
			self.condTest.asHtml(context))

	def asSql(self, context):
		return self.condTest.asSql(context)
	
processedCondition.setParseAction(lambda s, loc, toks: Condition(*toks))


class LiteralCondition(ParseNode):
	"""is a condition that is just passed through, i.e. no form element
	will be made for it.
	"""
	def __init__(self, name, relation, value):
		self.name, self.relation, self.value = name, relation, value
		self.children = [self.name, self.relation, self.value]
	
	def __repr__(self):
		return self.name+self.relation+self.value
	
	def asHtml(self, context):
		return ""
	
	def asSql(self, context):
		return self.name+self.relation+self.value, {}

literalCondition.setParseAction(lambda s, loc, toks: LiteralCondition(*toks))


class CExpression(ParseNode):
	"""is a homogenous expression with an operator and operands.

	Homogenous is meant to mean that all operands are joined
	with the same operator.  Also, we do not accept "degenerated" expression
	without an operator.
	"""
	def __init__(self, *args):
		try:
			self.operator = args[1]
			assert(reduce(operator.__and__, [args[i]==self.operator 
				for i in range(1, len(args), 2)]))
			self._expandOperands([args[i] for i in range(0, len(args), 2)])
			self.children = list(args)
		except Exception, msg: 
			# old pyparsing swallows the exception and behaves strangely.
			# and I want something strange out on the screen :-)
			print ">>>>>>>>>>>>>", msg, args
			raise

	def _expandOperands(self, rawOperands):
		"""folds in nested lists in the operands.
		"""
		self.operands = []
		for op in rawOperands:
			if isinstance(op, CExpression) and op.operator==self.operator:
				self.operands.extend(op.operands)
			else:
				self.operands.append(op)

	def __repr__(self):
		return "<%s>"%((" %s "%self.operator).join(
			[repr(operand) for operand in self.operands]))

	def _rebuildExpression(self, parts, joiner):
		if not parts:
			return ""
		else:
			return joiner.join(parts)

	def asHtml(self, context):
		parts = [o.asHtml(context) for o in self.operands]
		return '<div class="subExpr">%s</div>'%self._rebuildExpression(
			parts,'<span class="junctor">%s</span>'%self.operator)

	def _rebuildSQL(self, parts, joiner):
		allArgs = {}
		for args in [part[1] for part in parts]:
			allArgs.update(args)
		newExpr = self._rebuildExpression([part[0] for part in parts], joiner)
		if self.operator=="OR":
			newExpr = "(%s)"%newExpr
		return newExpr, allArgs

	def asSql(self, aks):
		parts = [part for part in [o.asSql(aks) for o in self.operands]
			if part[0]]
		return self._rebuildSQL(parts, " %s "%self.operator)


def buildExpression(args):
	if len(args)==1:
		return args[0]
	else:
		return CExpression(*args)

clauses.setParseAction(lambda s, loc, toks: buildExpression(toks))
andExpr.setParseAction(lambda s, loc, toks: buildExpression(toks))
parenExpr.setParseAction(lambda s, loc, toks: buildExpression(toks))
whereClauses.setParseAction(lambda s, loc, toks: buildExpression(toks))


class SelectItems(ParseNode):
	"""is a container for items in a select list.
	"""
	def __init__(self, *items):
		self.children = items
	
	def __repr__(self):
		return "<Items: %s>"%(", ".join([repr(item) for item in self.children]))
	
	def asHtml(self, context):
		return ""
	
	def asSql(self):
		return ", ".join([item.asSql()[0] for item in self.children]), {}

	def getItems(self):
		return self.children

selectItems.setParseAction(lambda s, loc, toks: SelectItems(*toks))


class SelectItem(ParseNode):
	"""is a model for an item in a select list.
	"""
	def __init__(self, columnName, columnTitle, displayHint):
		self.columnName, self.columnTitle, self.displayHint = \
			columnName, columnTitle, displayHint
		self.children = [self.columnName, self.columnTitle, self.displayHint]

	def __repr__(self):
		return '"%s"'%self.columnName

	def asHtml(self, context):
		return ""
	
	def asSql(self):
		return self.columnName, {}

	def getDef(self):
		return {
			"name": self.columnName,
			"title": self.columnTitle,
			"hint": self.displayHint,
		}

selectItem.setParseAction(lambda s, loc, toks: SelectItem(*toks))


class Query(ParseNode):
	"""is a parsed SQL statement.
	"""
	def __init__(self, qColumns, defaultTable, tests):
		self.qColumns, self.defaultTable, self.tests = \
			qColumns, defaultTable, tests
		self.children = [self.qColumns, self.defaultTable, self.tests]

	def __repr__(self):
		return "<Query for %s, %s -- %s>"%(self.defaultTable, self.qColumns,
			repr(self.tests))

	def asHtml(self, context):
		return self.tests.asHtml(context)

	def asSql(self, context):
		testSql, args = self.tests.asSql(context)
		return "SELECT %s FROM %s WHERE %s"%(self.qColumns.asSql()[0],
			self.defaultTable, testSql), args
	
	def getItemdefs(self):
		return [col.getDef() for col in self.qColumns.getItems()]

	def getDefaultTable(self):
		"""returns the default table for resolving column names.
		"""
		return self.defaultTable
	
	def getConditions(self):
		return self.tests
	
	def setSelectItems(self, items):
		"""replaces the current query columns with items.

		items may be a string that matches the selectItems production,
		or it may be an object that does what we want from seletItems.
		"""
		if isinstance(items, basestring):
			items = selectItems.parseString(items)[0]
		self.qColumns = items
		self.children[0] = self.qColumns

	def addConjunction(self, sqlCondition):
		"""adds the sql search condition as an AND clause to the current Query.

		sqlCondition may be a string that matches the clauses production 
		in sqlparse or ParseNode with asHtml and asSql methods returning
		output "good enough" for a where clause.
		"""
		if isinstance(sqlCondition, basestring):
			sqlCondition = clauses.parseString(sqlCondition)[0]
		self.tests = CExpression(self.tests, "AND", sqlCondition)
		self.children[2] = self.tests

	def copy(self):
		"""returns a semi-deep copy of the query.

		Semi-deep is supposed to mean that shallow copies of tests and
		qColumns are included; all other children are just references to
		the original.  The idea is that you probably want to add to tests
		and qColumns but leave the rest of the query as it is.
		"""
		return Query(self.qColumns.copy(), self.defaultTable, self.tests.copy())

simpleSql.setParseAction(lambda s, loc, toks: Query(*toks))


def parse(sqlStatement, production=simpleSql):
	try:
		return utils.silence(production.parseString, sqlStatement)[0]
	except ParseException, msg:
		raise querulator.Error("Parse error in SQL (line %s): %s"%(msg.line,
			msg))


if __name__=="__main__":
	termclauses = whereClauses+StringEnd()
	print parse("""
select select x from b where a=b""")
