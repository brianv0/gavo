"""
This module contains code to parse SQL templates for the querulator

The fragment of SQL we understand is still quite small.

Externally, you probably only want to see Query.

Otherwise, all relevant parts of the query are parsed into classes that embed
one another and have asSql and asHtml methods.  Their constructors
always take token lists generated from pyparsing, usually flattened into
argument lists (i.e., *args).  Thus, their constructors are used as
parseActions for pyparsing (with a trivial lambda wrapper).

TODO: We need a test suite badly, since grammars are always tricky...
"""

import sys
from pyparsing import Word, Literal, Optional, alphas, CaselessKeyword,\
	ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,\
	Suppress, Keyword, Forward, QuotedString, Group, printables
import pyparsing

from gavo.web import querulator
from gavo.web.querulator import htmlgenfuncs


def _joinChildren(s, loc, toks):
	"""is a parse action that joins all elements of the ParseResult toks.
	"""
	return "".join(toks)

def _joinChildrenBlank(s, loc, toks):
	"""is a parse action that joins all elements of the ParseResult toks with
	blanks.
	"""
	return " ".join(toks)


# SQL literals
literalSelect = CaselessKeyword("SELECT")
literalWhere = CaselessKeyword("WHERE")
literalFrom = CaselessKeyword("FROM")

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
	| Literal("=") | CaselessKeyword("in") | CaselessKeyword("like"))
between = CaselessKeyword("BETWEEN")
eqTest = sqlId + relation + pythonCode
betweenTest = sqlId + between + pythonCode
conditionDescription=condTitle + Suppress("|") + (eqTest | betweenTest)
processedCondition = (Suppress(fieldStart) + conditionDescription + 
	Suppress(fieldEnd))

# we should probably be a bit more careful parsing sql expressions
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

# production for parsing literal SQL conditions (those are just copied
# over)
sqlAtom = sqlId | QuotedString(quoteChar='"', escChar="\\",
	unquoteResults=False) | QuotedString(quoteChar="'", escChar="\\",
	unquoteResults=False)
literalCondition = sqlAtom + relation + sqlAtom

# productions leading up to clauses (which matches anything after a WHERE)
condition = processedCondition | literalCondition
whereExpr = Forward()
exprTail = ( CaselessKeyword("AND") | CaselessKeyword("OR")) + whereExpr 
binaryExpr = condition + exprTail
whereExpr << ( binaryExpr | condition )

# toplevel productions
dbName = sqlId
simpleSql = (Suppress(literalSelect) + selectItems + Suppress(literalFrom) + 
	dbName + Suppress(literalWhere) + whereExpr + StringEnd())


# Cosmetics for debugging purposes
condition.setName("Condition")
whereExpr.setName("WHERE expression")
exprTail.setName("Expression tail")
literalCondition.setName("Literal condition")
sqlId.setName("Sql identifier")


if False:
	whereExpr.setDebug(True)
	exprTail.setDebug(True)
	condition.setDebug(True)
	simpleSql.setDebug(True)



class ParseNode:
	"""is an abstract base class for nodes in the SQL parse tree.

	The common interface all parse nodes have to support is:
	 * __repr__
	 * asHtml -- returns a string containing HTML for use in a form
	   to set variables within the node
	 * asSql -- returns a string containing an SQL query fragment
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


class CondTest(ParseNode):
	"""is a base class for a row tests.

	It already implements everything you need for "simple" tests
	requiring just one input.

	To make this work when multiple CondTests for the same column are
	in one form, you can (and should) set the fieldBase.  Within
	Querulator, Condition does this.
	"""
	relationsOnSets = set(["in"])

	def __init__(self, colName, relation, generationCode):
		self.colName, self.relation, self.generationCode = \
			colName, relation, generationCode
		self.fieldBase = colName
		self.children = [self.colName, self.relation, self.generationCode]
		self.wantsSet = self.relation.lower() in self.relationsOnSets

	def __repr__(self):
		return "%s %s %s"%(self.colName, self.relation, 
			self.generationCode)

	def setFieldBase(self, fieldBase):
		self.fieldBase = fieldBase

	def asHtml(self):
		import sys
		return eval(self.generationCode, htmlgenfuncs.__dict__)%{
			"fieldName": self.fieldBase
		}

	def getQueryInfo(self):
		if self.wantsSet:
			return {self.fieldBase: ('l',)}
		else:
			return {self.fieldBase: ('a',)}

	def asSql(self, availableKeys):
		if self.fieldBase in availableKeys:
			return "%s %s %%(%s)s"%(self.colName, self.relation, self.fieldBase)
		return ""

eqTest.setParseAction(lambda s, loc, toks: CondTest(*toks))


class TwoFieldTest(CondTest):
	"""is a test for operators requiring two input fields.

	This typically is a BETWEEN or something like that.  We require
	user cooperation to make that work, in that the htmlgen function
	needs to produce xxx-lower and xxx-upper keys; the XXXrange functions
	do this, and only they should be used with tests like this.

	Maybe we should to a decorator based sanity checking here.
	"""
	def asSql(self, availableKeys):
		lowerKey, upperKey = "%s-lower"%self.fieldBase, "%s-upper"%self.fieldBase
		if lowerKey in availableKeys and upperKey in availableKeys:
			return "%s BETWEEN %%(%s-lower)s AND %%(%s-upper)s"%(
				self.colName, self.fieldBase, self.fieldBase)
		elif lowerKey in availableKeys:
			return "%s >= %%(%s-lower)s"%(self.colName, self.fieldBase)
		elif upperKey in availableKeys:
			return "%s <= %%(%s-upper)s"%(self.colName, self.fieldBase)
		return ""

	def getQueryInfo(self):
		return {"%s-lower"%self.fieldBase: ('a',),
			"%s-upper"%self.fieldBase: ('a',)}

betweenTest.setParseAction(lambda s, loc, toks: TwoFieldTest(*toks))


class Condition(ParseNode):
	"""is a single condition for the query, consisting of a test and
	a description.
	"""
	def __init__(self, description, condTest):
		self.description, self.condTest = description, condTest
		self.condTest.setFieldBase(self.description.encode("hex"))
		self.children = [self.description, self.condTest]

	def __repr__(self):
		return "<Condition '%s', %s>"%(self.description, repr(self.condTest))
	
	def asHtml(self):
		return ('<div class="condition"><div class="Clabel">%s</div> '
			'<div class="quwidget">%s</div></div>')%(
			self.description,
			self.condTest.asHtml())

	def asSql(self, availableKeys):
		return self.condTest.asSql(availableKeys)
	

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
	
	def asHtml(self):
		return ""
	
	def asSql(self, availableKeys):
		return self.name+self.relation+self.value

literalCondition.setParseAction(lambda s, loc, toks: LiteralCondition(*toks))


class BinaryExpression(ParseNode):
	"""is a binary expression
	"""
	def __init__(self, left, junctor, right):
		self.left, self.right = left, right
		self.junctor = junctor
		self.children = [self.left, self.junctor, self.right]
	
	def __repr__(self):
		return "<%s %s %s>"%(repr(self.left), self.junctor, repr(self.right))
	
	def _buildExpConditional(self, left, right, op):
		"""returns the "short-circuit" form of left op right.

		Plainly, it builds an expression such that empty elements vanish,
		and, in the presence of empty elements, op vanishes as well.
		"""
		if left and right:
			op = " %s "%op
		else:
			op = ""
		return "%s%s%s"%(left, op, right)

	def asHtml(self):
		leftHtml, rightHtml = self.left.asHtml(), self.right.asHtml()
		return '<div class="binaryQ">%s</div>'%(
			self._buildExpConditional(leftHtml, rightHtml,
				'<span class="junctor">%s</span>'%self.junctor))


	def asSql(self, aks):
		leftSql, rightSql = self.left.asSql(aks), self.right.asSql(aks)
		return self._buildExpConditional(leftSql, rightSql, self.junctor)

binaryExpr.setParseAction(lambda s, loc, toks: BinaryExpression(*toks))


class SelectItems(ParseNode):
	"""is a container for items in a select list.
	"""
	def __init__(self, *items):
		self.children = items
	
	def __repr__(self):
		return "<Items: %s>"%(", ".join([repr(item) for item in self.children]))
	
	def asHtml(self):
		return ""
	
	def asSql(self):
		return ", ".join([item.asSql() for item in self.children])

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
		return self.columnName

	def asHtml(self):
		return ""
	
	def asSql(self):
		return self.columnName

	def getDef(self):
		return {
			"name": self.columnName,
			"title": self.columnTitle,
			"hint": self.displayHint,
		}

selectItem.setParseAction(lambda s, loc, toks: SelectItem(*toks))


class Query(ParseNode):
	"""is a container for all information pertaining to an SQL query.
	"""
	def __init__(self, qColumns, defaultTable, tests):
		self.qColumns, self.defaultTable, self.tests = \
			qColumns, defaultTable, tests
		self.children = [self.qColumns, self.defaultTable, self.tests]

	def __repr__(self):
		return "<Query for %s, %s -- %s>"%(self.defaultTable, self.qColumns,
			repr(self.tests))

	def asHtml(self):
		return self.tests.asHtml()

	def asSql(self, availableKeys):
		return "SELECT %s FROM %s WHERE %s"%(self.qColumns.asSql(),
			self.defaultTable, self.tests.asSql(availableKeys))
	
	def getItemdefs(self):
		return [col.getDef() for col in self.qColumns.getItems()]

	def getDefaultTable(self):
		"""returns the default table for resolving column names.
		"""
		return self.defaultTable
	
	def getConditions(self):
		return self.tests


simpleSql.setParseAction(lambda s, loc, toks: Query(*toks))


if __name__=="__main__":
	simpleSql.validate()
	p = simpleSql.parseString("""
SELECT 
	{{dec \|\| " " \|\| ra|Observation date|date}}, 
	{{filename|File name|string}},
	{{dataurl|Image|url}}
FROM maidanak_raw WHERE 
{{Observation after|date>date()}}  AND
{{Observation before|date<date()}}  AND
"type"='FLAT'""")[0]
	print p.asHtml()
	print p.asSql({})
