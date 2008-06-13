"""
A parser for ADQL.

The grammar follows the official BNF grammar quite closely, except where
pyparsing makes a different approach desirable; the names should mostly
match except for the obious underscore to camel case map.
"""

"""
The grammar given in the spec has some nasty blocks for recursive
descent parsers (which is what pyparsing generates).  Here are some
reformulations.

(1) TableReference

Trouble is the naked joined_table.  Important rules here:

  <table_reference> ::=
     <table_name> [ <correlation_specification> ]
   | <derived_table> <correlation_specification>
   | <joined_table>

  <joined_table> ::=
      <qualified_join>
    | <left_paren> <joined_table> <right_paren>

  <qualified_join> ::=
      <table_reference> [ NATURAL ] [ <join_type> ] JOIN
      <table_reference> [ <join_specification> ]

Now, it's clear that the first element of a join is either a name
or has to start with an opening paren, in which we are in the second
disjunction of <joined_table>.

So, we can rewrite the above rules as:

  <nojoin_table_reference> ::=
     <table_name> [ <correlation_specification> ]
   | <derived_table> <correlation_specification>
	
	<table_reference> ::=
    <joined_table>
		| <nojoin_table_reference>

  <joined_table> ::=
      <left_paren> <joined_table> <right_paren> {<join_tail>}
    | <nojoin_table_reference> <join_tail> {<join_tail>}

	<join_tail> ::= [ NATURAL ] [ <join_type> ] JOIN
      <table_reference> [ <join_specification> ]

-- this is what's implemented below.
"""

from pyparsing import Word, Literal, Optional, alphas, CaselessKeyword,\
	ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,\
	Suppress, Keyword, Forward, QuotedString, Group, printables, nums,\
	CaselessLiteral, ParseException, Regex, sglQuotedString, alphanums,\
	dblQuotedString, ParserElement, White

adqlReservedWords = set([ "ABS", "ACOS", "AREA", "ASIN", "ATAN", "ATAN2",
	"CEILING", "CENTROID", "CIRCLE", "CONTAINS", "COS", "DEGREES", "DISTANCE",
	"EXP", "FLOOR", "INTERSECTS", "LATITUDE", "LOG", "LOG10", "LONGITUDE",
	"MODE", "PI", "POINT", "POLYGON", "POWER", "RADIANS", "RECTANGLE", "REGION",
	"RAND", "ROUND", "SIN", "SQUARE", "SQRT", "TOP", "TAN", "TRUNCATE",])

sqlReservedWords = set([
	"ABSOLUTE", "ACTION", "ADD", "ALL", "ALLOCATE", "ALTER", "AND", "ANY",
	"ARE", "AS", "ASC", "ASSERTION", "AT", "AUTHORIZATION", "AVG", "BEGIN",
	"BETWEEN", "BIT", "BIT_LENGTH", "BOTH", "BY", "CASCADE", "CASCADED",
	"CASE", "CAST", "CATALOG", "CHAR", "CHARACTER", "CHAR_LENGTH",
	"CHARACTER_LENGTH", "CHECK", "CLOSE", "COALESCE", "COLLATE",
	"COLLATION", "COLUMN", "COMMIT", "CONNECT", "CONNECTION", "CONSTRAINT",
	"CONSTRAINTS", "CONTINUE", "CONVERT", "CORRESPONDING", "COUNT",
	"CREATE", "CROSS", "CURRENT", "CURRENT_DATE", "CURRENT_TIME",
	"CURRENT_TIMESTAMP", "CURRENT_USER", "CURSOR", "DATE", "DAY",
	"DEALLOCATE", "DECIMAL", "DECLARE", "DEFAULT", "DEFERRABLE", "DEFERRED",
	"DELETE", "DESC", "DESCRIBE", "DESCRIPTOR", "DIAGNOSTICS", "DISCONNECT",
	"DISTINCT", "DOMAIN", "DOUBLE", "DROP", "ELSE", "END", "END-EXEC",
	"ESCAPE", "EXCEPT", "EXCEPTION", "EXEC", "EXECUTE", "EXISTS",
	"EXTERNAL", "EXTRACT", "FALSE", "FETCH", "FIRST", "FLOAT", "FOR",
	"FOREIGN", "FOUND", "FROM", "FULL", "GET", "GLOBAL", "GO", "GOTO",
	"GRANT", "GROUP", "HAVING", "HOUR", "IDENTITY", "IMMEDIATE", "IN",
	"INDICATOR", "INITIALLY", "INNER", "INPUT", "INSENSITIVE", "INSERT",
	"INT", "INTEGER", "INTERSECT", "INTERVAL", "INTO", "IS", "ISOLATION",
	"JOIN", "KEY", "LANGUAGE", "LAST", "LEADING", "LEFT", "LEVEL", "LIKE",
	"LOCAL", "LOWER", "MATCH", "MAX", "MIN", "MINUTE", "MODULE", "MONTH",
	"NAMES", "NATIONAL", "NATURAL", "NCHAR", "NEXT", "NO", "NOT", "NULL",
	"NULLIF", "NUMERIC", "OCTET_LENGTH", "OF", "ON", "ONLY", "OPEN",
	"OPTION", "OR", "ORDER", "OUTER", "OUTPUT", "OVERLAPS", "PAD",
	"PARTIAL", "POSITION", "PRECISION", "PREPARE", "PRESERVE", "PRIMARY",
	"PRIOR", "PRIVILEGES", "PROCEDURE", "PUBLIC", "READ", "REAL",
	"REFERENCES", "RELATIVE", "RESTRICT", "REVOKE", "RIGHT", "ROLLBACK",
	"ROWS", "SCHEMA", "SCROLL", "SECOND", "SECTION", "SELECT", "SESSION",
	"SESSION_USER", "SET", "SIZE", "SMALLINT", "SOME", "SPACE", "SQL",
	"SQLCODE", "SQLERROR", "SQLSTATE", "SUBSTRING", "SUM", "SYSTEM_USER",
	"TABLE", "TEMPORARY", "THEN", "TIME", "TIMESTAMP", "TIMEZONE_HOUR",
	"TIMEZONE_MINUTE", "TO", "TRAILING", "TRANSACTION", "TRANSLATE",
	"TRANSLATION", "TRIM", "TRUE", "UNION", "UNIQUE", "UNKNOWN", "UPDATE",
	"UPPER", "USAGE", "USER", "USING", "VALUE", "VALUES", "VARCHAR",
	"VARYING", "VIEW", "WHEN", "WHENEVER", "WHERE", "WITH", "WORK", "WRITE",
	"YEAR", "ZONE"])

allReservedWords = adqlReservedWords | sqlReservedWords


def _failOnReservedWord(s, pos, toks):
	"""raises a ParseException if toks[0] is a reserved word.

	This is a parse action on identifiers and, given SQL's crazy grammar,
	all-importnat for parsing.
	"""
	if toks and toks[0].upper() in allReservedWords:
		raise ParseException(s, pos, "Reserved word not allowed here")

def _getADQLGrammar(defaultFunctionPrefix="udf_"):
	"""returns a pair symbols, selectSymbol for a grammar parsing ADQL.

	This is for internal use only.  Use getADQLGrammar.
	"""
	ParserElement.enablePackrat() # XXX Do we want to do this?  We should
# create a ParserElement of our own, I guess, to avoid messing up other
# grammars.
	comment = "--" + SkipTo("\n" | StringEnd())
	separator = Optional( comment )  # Whitespace handled by pyparsing
	whitespace = Word(" \t")   # sometimes necessary to avoid sticking together
		# numbers and identifiers

	unsignedInteger = Word(nums)
	_exactNumericRE = r"\d+(\.(\d+)?)?|\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	approximateNumericLiteral = Regex(r"(?i)%sE[+-]?\d+")
	unsignedNumericLiteral = ( exactNumericLiteral |
		approximateNumericLiteral )
	characterStringLiteral = sglQuotedString + ZeroOrMore(
		separator + sglQuotedString)
	generalLiteral = characterStringLiteral
	unsignedLiteral = unsignedNumericLiteral | generalLiteral
	sign = Literal("+") | "-"
	multOperator = Literal("*") | "/"

	adqlReservedWord = Regex("(?i)"+"|".join(adqlReservedWords))
	sqlReservedWord = Regex("(?i)"+"|".join(sqlReservedWords))

	regularIdentifier = Word(alphas, alphanums+"_").setParseAction(
		_failOnReservedWord)
	delimitedIdentifier = dblQuotedString
	identifier = regularIdentifier | delimitedIdentifier

# Operators
	compOp = Regex("=|!=|<=|>=|<|>")

# Column names and such
	columnName = identifier
	catalogName = identifier
	unqualifiedSchemaName = identifier
	correlationName = identifier
	schemaName = Optional( catalogName + "." ) + unqualifiedSchemaName
	tableName = Optional( schemaName + "." ) + identifier
	qualifier = tableName | correlationName
	columnReference = Optional( qualifier + "." ) + columnName
	asClause = ( CaselessKeyword("AS") | whitespace ) + columnName

	setFunctionSpecification = Literal("XXX TODO")

	valueExpression = Forward()
	unsignedValueSpecification = unsignedLiteral
	valueExpressionPrimary = ( unsignedValueSpecification |
		columnReference | setFunctionSpecification |
		'(' + valueExpression + ')')

	userDefinedFunctionParam = valueExpression
	userDefinedFunctionName = defaultFunctionPrefix + regularIdentifier
	userDefinedFunction = ( userDefinedFunctionName + '(' +
		userDefinedFunctionParam + ZeroOrMore( "," + userDefinedFunctionParam ) 
			+ ')')

	# XXX TODO: make below right.
	numericValueFunction = userDefinedFunction

# string literal stuff
	characterPrimary = valueExpressionPrimary # | userDefinedFunction
	characterFactor = characterPrimary
	characterValueExpression = ( characterFactor + 
		ZeroOrMore( "||" + characterFactor ))
	stringValueExpression = characterValueExpression

# numeric expressions/terms
	numericValueExpression = Forward()
	numericExpressionPrimary = ( unsignedValueSpecification | columnReference
		| setFunctionSpecification | '(' + valueExpression + ')')
	numericPrimary = valueExpressionPrimary | numericValueFunction
	factor = Optional( sign ) + numericPrimary
	term = Forward()
	term << (factor + ZeroOrMore( multOperator + factor ))
	numericValueExpression << term # | numericValueExpression "+" term | numericValueExpression "-" term

# toplevel "value" expression
	valueExpression << (numericValueExpression |
		stringValueExpression) #| geometryValueExpression)
	derivedColumn = valueExpression + Optional( asClause )

# parts of select clauses
	setQuantifier = CaselessKeyword("DISTINCT") | CaselessKeyword("ALL")
	setLimit = CaselessKeyword("TOP") + unsignedInteger
	selectSublist = derivedColumn | qualifier + "." + ","
	selectList = "*" | selectSublist + ZeroOrMore(
		"," + selectSublist )

# boolean terms
	searchCondition = Forward()
	comparisonPredicate = valueExpression + compOp + valueExpression
	predicate = ( comparisonPredicate ) #| betweenPredicate | inPredicate | likePredicate | nullPredicate | existsPredicate)
	booleanPrimary = '(' + searchCondition + ')' | predicate
	booleanFactor = Optional( CaselessKeyword("NOT") ) + booleanPrimary
	booleanTerm = ( booleanFactor + 
		ZeroOrMore( CaselessKeyword("AND") + booleanFactor ))

# WHERE clauses and such
	searchCondition << ( booleanTerm + 
		ZeroOrMore( CaselessKeyword("OR") + booleanTerm ))
	whereClause = CaselessKeyword("WHERE") + searchCondition

# Referencing tables
	queryExpression = Forward()
	correlationSpecification = ( CaselessKeyword("AS") | whitespace
		) + correlationName
	subquery = '(' + queryExpression + ')'
	derivedTable = subquery
	joinedTable = Forward()
	nojoinTableReference = tableName + Optional( correlationSpecification) | (
		derivedTable + correlationSpecification )
	tableReference =  joinedTable | nojoinTableReference 

# JOINs
	columnNameList = columnName + ZeroOrMore( "," + columnName)
	namedColumnsJoin = (CaselessKeyword("USING") + '(' +
		columnNameList + ')')
	joinCondition = CaselessKeyword("ON") + searchCondition
	joinSpecification = joinCondition | namedColumnsJoin
	outerJoinType = CaselessKeyword("LEFT") | CaselessKeyword("RIGHT"
		) | CaselessKeyword("FULL")
	joinType = CaselessKeyword("INNER") | (
		outerJoinType + CaselessKeyword("OUTER"))
	joinTail = (Optional( CaselessKeyword("NATURAL") ) +
		Optional( joinType ) + 
		CaselessKeyword("JOIN") + 
		tableReference +
		Optional( joinSpecification ))
	joinedTable << ('(' + joinedTable + ')' + ZeroOrMore( joinTail )
		| nojoinTableReference + OneOrMore( joinTail ))

# Detritus in table expressions
	groupByClause = CaselessKeyword("GROUP") + CaselessKeyword("BY"
		) + columnReference + ZeroOrMore( ',' + columnReference)
	havingClause = CaselessKeyword("HAVING") + searchCondition
	orderingSpecification = CaselessKeyword("ASC"
		) | CaselessKeyword("DESC")
	sortKey = columnName | unsignedInteger
	sortSpecification = sortKey + Optional( orderingSpecification )
	orderByClause = CaselessKeyword("ORDER") + CaselessKeyword("BY"
		) + sortSpecification + ZeroOrMore( ',' + sortSpecification )

# FROM fragments and such
	fromClause = CaselessKeyword("FROM") + tableReference + ZeroOrMore(
		',' + tableReference)
	tableExpression = (fromClause + Optional( whereClause ) + 
		Optional( groupByClause )  + Optional( havingClause ) + 
		Optional( orderByClause ))

# toplevel select clause
	querySpecification = Forward()
	queryExpression << querySpecification # |  joinedTable
	querySpecification << ( CaselessKeyword("SELECT") + Optional( setQuantifier 
		) + Optional( setLimit ) +  selectList + tableExpression ) + StringEnd()
	return dict((k, v) for k, v in locals().iteritems()
		if isinstance(v, ParserElement)), querySpecification


_grammarCache = None

def enableDebug(syms, debugNames=None):
	if not debugNames:
		debugNames = syms
	for name in debugNames:
		ob = syms[name]
		if not ob.debug:
			ob.setDebug(True)
			ob.setName(name)


def getADQLGrammar():
	global _grammarCache
	if not _grammarCache:
		_grammarCache = _getADQLGrammar()
	return _grammarCache


if __name__=="__main__":
	syms, grammar = getADQLGrammar()
	enableDebug(syms)
	print ">>>>", grammar.parseString("select x from t1 JOIN t2")
