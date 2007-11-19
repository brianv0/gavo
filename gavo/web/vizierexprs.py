"""
Classes and methods to support vizier-type specifications on fields.
"""


from pyparsing import Word, Literal, Optional, Forward, Group,\
	ZeroOrMore, nums, Suppress, ParseException, StringEnd, Regex,\
	OneOrMore, Or, MatchFirst

import gavo
from gavo import typesystems
from gavo.parsing import contextgrammar
from gavo.parsing import typeconversion


class ParseNode(object):
	"""is a parse node, consisting of an operator and children.

	The parse trees returned by the various parse functions are built by
	these.
	"""
	def __init__(self, children, operator):
		self.children = children
		self.operator = operator
	
	def __str__(self):
		return "(%s %s)"%(self.operator, " ".join([str(c) for c in self.children]))

	__repr__ = __str__

	def _insertChild(self, index, key, sqlPars):
		"""inserts children[index] into sqlPars with a unique key and returns
		the key.

		children[index] must be atomic (i.e., no ParseNode).
		"""
		item = self.children[index]
		if item==None:
			return None
		assert not isinstance(item, ParseNode)
		return getSQLKey(key, item, sqlPars)

	def asSQL(self, key, sqlPars):
		if self.operator in self._standardOperators:
			return "%s %s %%(%s)s"%(key, self.operator, 
				self._insertChild(0, key, sqlPars))
		else:
			return self._sqlEmitters[self.operator](self, key, sqlPars)

	# the following methods are used at used at class construction time
	def _emitBinop(self, key, sqlPars):
		return joinOperatorExpr(self.operator,
			[c.asSQL(key, sqlPars) for c in self.children])
		
	def _emitUnop(self, key, sqlPars):
		operand = self.children[0].asSQL(key, sqlPars)
		if operand:
			return "%s (%s)"%(self.operator, operand)

	_standardOperators = set(["=", ">=", ">", "<=", "<"])
	_sqlEmitters = {
		'..': lambda self, key, sqlPars: "%s BETWEEN %%(%s)s AND %%(%s)s"%(key, 
			self._insertChild(0, key, sqlPars), self._insertChild(1, key, sqlPars)),
		'AND': _emitBinop,
		'OR': _emitBinop,
		'NOT': _emitUnop,
		',': lambda self, key, sqlPars: "%s IN (%s)"%(key, ", ".join([
					"%%(%s)s"%self._insertChild(i, key, sqlPars) 
				for i in range(len(self.children))])),
	}


def _getNodeFactory(op):
	def _(s, loc, toks):
		return ParseNode(toks, op)
	return _


def _makeNotNode(s, loc, toks):
	if len(toks)==1:
		return toks[0]
	elif len(toks)==2:
		return ParseNode(toks[1:], "NOT")
	else: # Can't happen :-)
		raise Exception("Busted by not")


def _makePmNode(s, loc, toks):
	return ParseNode([toks[0]-toks[1], toks[0]+toks[1]], "..")


def _makeDatePmNode(s, loc, toks):
	"""returns a +/- node for dates, i.e., toks[1] is a float in days.
	"""
	days = typeconversion.make_timeDelta(days=toks[1])
	return ParseNode([toks[0]-days, toks[0]+days], "..")


def _getBinopFactory(op):
	def _(s, loc, toks):
		if len(toks)==1:
			return toks[0]
		else:
			return ParseNode(toks, op)
	return _


def _makeSimpleExprNode(s, loc, toks):
	if len(toks)==1:
		return ParseNode(toks[0:], "=")
	else:
		return ParseNode(toks[1:], toks[0])


def getComplexGrammar(baseLiteral, pmBuilder, errorLiteral=None):
	"""returns the root element of a grammar parsing numeric vizier-like 
	expressions.

	This is used for both dates and floats, use baseLiteral to match the
	operand terminal.  The trouble with dates is that the +/- operator
	has a simple float as the second operand, and that's why you can
	pass in an errorLiteral and and pmBuilder.
	"""
	if errorLiteral==None:
		errorLiteral = baseLiteral

	preOp = Literal("=") |  Literal(">=") | Literal(">"
		) | Literal("<=") | Literal("<")
	rangeOp = Literal("..")
	pmOp = Literal("+/-") | Literal("\xb1".decode("iso-8859-1"))
	orOp = Literal("|")
	andOp = Literal("&")
	notOp = Literal("!")
	commaOp = Literal(",")

	preopExpr = Optional(preOp) + baseLiteral
	rangeExpr = baseLiteral + Suppress(rangeOp) + baseLiteral
	valList = baseLiteral + OneOrMore( Suppress(commaOp) + baseLiteral)
	pmExpr = baseLiteral + Suppress(pmOp) + errorLiteral
	simpleExpr = rangeExpr | pmExpr | valList | preopExpr

	expr = Forward()

	notExpr = Optional(notOp) +  simpleExpr
	andExpr = notExpr + ZeroOrMore( Suppress(andOp) + notExpr )
	orExpr = andExpr + ZeroOrMore( Suppress(orOp) + expr)
	expr << orExpr
	exprInString = expr + StringEnd()

	rangeExpr.setName("rangeEx")
	rangeOp.setName("rangeOp")
	notExpr.setName("notEx")
	andExpr.setName("andEx")
	andOp.setName("&")
	orExpr.setName("orEx")
	expr.setName("expr")
	simpleExpr.setName("simpleEx")

	preopExpr.setParseAction(_makeSimpleExprNode)
	rangeExpr.setParseAction(_getNodeFactory(".."))
	pmExpr.setParseAction(pmBuilder)
	valList.setParseAction(_getNodeFactory(","))
	notExpr.setParseAction(_makeNotNode)
	andExpr.setParseAction(_getBinopFactory("AND"))
	orExpr.setParseAction(_getBinopFactory("OR"))

	return exprInString


floatLiteral = Regex(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?").setParseAction(
			lambda s, pos, tok: float(tok[0]))
# XXX TODO: be a bit more lenient in what you accept as a date
dateLiteral = Regex(r"\d\d\d\d-\d\d-\d\d").setParseAction(
			lambda s, pos, tok: typeconversion.make_dateTimeFromString(tok[0]))


def parseNumericExpr(str, baseSymbol=getComplexGrammar(floatLiteral, 
		_makePmNode)):
	"""returns a parse tree for vizier-like expressions over floats.
	"""
	return baseSymbol.parseString(str)[0]


def parseDateExpr(str, baseSymbol=getComplexGrammar(dateLiteral,
		_makeDatePmNode, floatLiteral)):
	"""returns a parse tree for vizier-like expressions over ISO dates.

	Note that the semantic validity of the date (like, month<13) is not
	checked by the grammar.
	"""
	return baseSymbol.parseString(str)[0]


parsers = {
	"vexpr-float": parseNumericExpr,
	"vexpr-date": parseDateExpr,
}

def getParserForType(dbtype):
	return parsers.get(dbtype)


def getSQL(field, inPars, sqlPars):
	try:
		val = inPars[field.get_source()]
		if val!=None:
			return parsers[field.get_dbtype()](val).asSQL(
				field.get_dest(), sqlPars)
	except ParseException:
		raise gavo.ValidationError(
			"Invalid input (see help on search expressions)", field.get_source())


def joinOperatorExpr(operator, operands):
	"""filters empty operands and joins the rest using operator.

	The function returns an expression string or None for the empty expression.
	"""
	operands = filter(None, operands)
	if not operands:
		return None
	elif len(operands)==1:
		return operands[0]
	else:
		return operator.join([" (%s) "%op for op in operands]).strip()


class CondDesc(object):
	"""is a condition descriptor for DB based cores.

	CondDescs know what input to take from a dictionary (usually the
	docRec) and how to make SQL conditions out of them.

	inputFields should be a sequence of contextgrammar.InputKeys or
	datadef.DataFields.  If they're InputKeys, no validation will be done
	by formal.  This is probably what you want if you want vizier-like
	expressions, macros, or similar tricks.
	"""
	inputFields = []

	def __init__(self):
		pass
	
	def getInputFields(self):
		return self.inputFields

	def getQueryFrag(self, inPars, sqlPars, queryMeta):
		frags = []
		for field in self.inputFields:
			frags.append(getSQL(field, inPars, sqlPars))
		return joinOperatorExpr("AND", frags)


class ToVexprConverter(typesystems.FromSQLConverter):
	simpleMap = {
		"smallint": "vexpr-float",
		"integer": "vexpr-float",
		"int": "vexpr-float",
		"bigint": "vexpr-float",
		"real": "vexpr-float",
		"float": "vexpr-float",
		"double precision": "vexpr-float",
		"double": "vexpr-float",
		"text": "vexpr-string",
		"char": "vexpr-string",
		"date": "vexpr-date",
		"timestamp": "vexpr-date",
	}

	def mapComplex(self, sqlType, length):
		if sqlType=="char":
			return "vexpr-string"

getVexprFor = ToVexprConverter().convert


class FieldCondDesc(CondDesc):
	"""is a condition descriptor based on a datadef.DataField.
	"""
	def __init__(self, key, field):
		super(FieldCondDesc, self).__init__()
		self.field = contextgrammar.InputKey(initvals=field.dataStore)
		self.field.set_source(key)
		self.field.set_dbtype(getVexprFor(self.field.get_dbtype()))
		self.parseVExpr = getParserForType(self.field.get_dbtype())
		self.inputFields = [self.field]
	

def getAutoCondDesc(field):
	"""returns a FieldCondDesc for the DataField field if it can be handled
	automatically, None otherwise.
	"""
	if field.get_displayHint()=="suppress":
		return
	if not getParserForType(field.get_dbtype()):
		return
	return FieldCondDesc(field.get_dest(), field)


def getSQLKey(key, value, sqlPars):
	"""adds value to sqlPars and returns a key for inclusion in a SQL query.

	This function is used to build parameter dictionaries for SQL queries, 
	avoiding overwriting parameters with accidental name clashes.
	It works like this:

	>>> sqlPars = {}
	>>> getSQLKey("foo", 13, sqlPars)
	'foo0'
	>>> getSQLKey("foo", 14, sqlPars)
	'foo1'
	>>> getSQLKey("foo", 13, sqlPars)
	'foo0'
	>>> sqlPars["foo0"], sqlPars["foo1"]; sqlPars = {}
	(13, 14)
	>>> "WHERE foo<%%(%s)s OR foo>%%(%s)s"%(getSQLKey("foo", 1, sqlPars),
	...   getSQLKey("foo", 15, sqlPars))
	'WHERE foo<%(foo0)s OR foo>%(foo1)s'
	"""
	ct = 0
	while True:
		dataKey = "%s%d"%(key, ct)
		if not sqlPars.has_key(dataKey) or sqlPars[dataKey]==value:
			break
		ct += 1
	sqlPars[dataKey] = value
	return dataKey


def _test():
	import doctest, vizierexprs
	doctest.testmod(vizierexprs)


if __name__=="__main__":
	if True:
		_test()
	else:
		debug = True
		notExpr.setDebug(debug)
		andExpr.setDebug(debug)
		andOp.setDebug(debug)
		orExpr.setDebug(debug)
		simpleExpr.setDebug(debug)
		expr.setDebug(debug)
		print numericExpr.parseString("! 1 & 2 | < 0")
