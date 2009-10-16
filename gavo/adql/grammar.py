"""
A parser for ADQL.

The grammar follows the official BNF grammar quite closely, except where
pyparsing makes a different approach desirable; the names should mostly
match except for the obious underscore to camel case map.
"""

"""
The grammar given in the spec has some nasty rules when you're parsing
without backtracking and by recursive descent (which is what pyparsing
does).  I need some reformulations.  The more interesting of those 
include:

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

(2) statement

I can't have StringEnd appended to querySpecification since it's used
in subqueries, but I need to have it to keep pyparsing from just matching
parts of the input.  Thus, the top-level production is for "statement".

(3) trig_function, math_function, system_defined_function

I think it's a bit funny to have the arity of functions in the syntax, but
there you go.  Anyway, I don't want to have the function names in separate
symbols since they are expensive but go for a Regex (trig1ArgFunctionName).
The only exception is ATAN since it has a different arity from the rest of the
lot.

Similarly, for math_function I group symbols by arity.

The system defined functions are also regrouped to keep the number of
symbols reasonable.

(4) column_reference and below

Here the lack of backtracking hurts badly, since once, say, schema name
is matched with a dot that's it, even if the dot should really have separated
schema and table.

Hence, we don't assign semantic labels in the grammar but leave that to
whatever interprets the tokens.

The important rules here are

<column_name> ::= <identifier>
<correlation_name> ::= <identifier>
<catalog_name> ::= <identifier>
<unqualified_schema name> ::= <identifier>
<schema_name> ::= [ <catalog_name> <period> ] <unqualified_schema name>
<table_name> ::= [ <schema_name> <period> ] <identifier>
<qualifier> ::= <table_name> | <correlation_name>
<column_reference> ::= [ <qualifier> <period> ] <column_name>

By substitution, one has

<schema_name> ::= [ <identifier> <period> ] <identifier>

hence,

<table_name> ::= [[ <identifier> <period> ] <identifier> <period> ] 
	<identifier>

hence,

<qualifier> ::= [[ <identifier> <period> ] <identifier> <period> ] 
	<identifier>

(which matches both table_name and correlation_name) and thus

<column_reference> ::= [[[ <identifier> <period> ] <identifier> <period> ] 
	<identifier> <period> ] <identifier>

We need the table_name, qualifier, and column_reference productions.

(5) One point I'm deviating from the published grammar is that I disallow
generalLiterals in unsignedLiterals.  Allowing them would let pyparsing
match a string literal as a numericValueLiteral, which messes up
string expressions.  I'm not sure why generalLiterals are allowed
in there anyway.  If this bites at some point, we'll face a major rewrite
of the grammar (or we need to dump pyparsing).

To make the whole thing work, I added the generalLiteral to the 
characterPrimary production.
"""


from pyparsing import Word, Literal, Optional, alphas, CaselessKeyword,\
	ZeroOrMore, OneOrMore, SkipTo, srange, StringEnd, Or, MatchFirst,\
	Suppress, Keyword, Forward, QuotedString, Group, printables, nums,\
	CaselessLiteral, ParseException, Regex, sglQuotedString, alphanums,\
	dblQuotedString, ParserElement, White

adqlReservedWords = set([ "ABS", "ACOS", "AREA", "ASIN", "ATAN", "ATAN2",
	"CEILING", "CENTROID", "CIRCLE", "CONTAINS", "COS", "DEGREES", "DISTANCE",
	"EXP", "FLOOR", "INTERSECTS", "LATITUDE", "LOG", "LOG10", "COORD1",
	"COORD2", "COORDSYS",
	"MOD", "PI", "POINT", "POLYGON", "POWER", "RADIANS", "RECTANGLE", "REGION",
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


# Prefix for user defined functions
userFunctionPrefix = "gavo_"


def _failOnReservedWord(s, pos, toks):
	"""raises a ParseException if toks[0] is a reserved word.

	This is a parse action on identifiers and, given SQL's crazy grammar,
	all-important for parsing.
	"""
	if toks and toks[0].upper() in allReservedWords:
		raise ParseException(s, pos, "Reserved word not allowed here")


def getADQLGrammarCopy():
	"""returns a pair symbols, selectSymbol for a grammar parsing ADQL.

	You should only use this if you actually require a fresh copy
	of the ADQL grammar.  Otherwise, use getADQLGrammar or a wrapper
	function defined by a client module.
	"""
# WARNING: Changing global state here temporarily.  This will be trouble in
# threads.  This stuff is reset below to the default from base.__init__
	ParserElement.setDefaultWhitespaceChars("\n\t\r ")
# Be careful when using setResultsName here.  The handlers are bound
# at a later point, and names cause copies of the pyparsing objects,
# so that elements named in rules will not be bound later.  Rather
# name elements on their construction.
	sqlComment = Literal("--") + SkipTo("\n" | StringEnd())
	whitespace = Word(" \t\n")   # sometimes necessary to avoid sticking 
		# together numbers and identifiers
	separator = Optional( sqlComment ) + Optional(Word(" \t\n\r"))

	unsignedInteger = Word(nums)
	_exactNumericRE = r"\d+(\.(\d+)?)?|\.\d+"
	exactNumericLiteral = Regex(_exactNumericRE)
	approximateNumericLiteral = Regex(r"(?i)(%s)E[+-]?\d+"%_exactNumericRE)
	unsignedNumericLiteral = ( approximateNumericLiteral | exactNumericLiteral )
	characterStringLiteral = sglQuotedString + ZeroOrMore(
		separator + sglQuotedString)
	generalLiteral = characterStringLiteral.copy()
	unsignedLiteral = unsignedNumericLiteral # !!! DEVIATION | generalLiteral
	sign = Literal("+") | "-"
	signedInteger = Optional( sign ) + unsignedInteger
	multOperator = Literal("*") | "/"
	notKeyword = CaselessKeyword("NOT")

	regularIdentifier = Word(alphas, alphanums+"_").addParseAction(
		_failOnReservedWord)
	delimitedIdentifier = QuotedString(quoteChar='"', escQuote='"',
		unquoteResults=False)
	identifier = regularIdentifier | delimitedIdentifier

# Operators
	compOp = Regex("=|!=|<=|>=|<|>")

# Column names and such
	columnName = identifier.copy()
	correlationName = identifier.copy()
	qualifier = (identifier 
		+ Optional( "." + identifier )
		+ Optional( "." + identifier ))
	tableName = qualifier("tableName")
	columnReference = (identifier 
		+ Optional( "." + identifier )
		+ Optional( "." + identifier )
		+ Optional( "." + identifier ))
	asClause = ( CaselessKeyword("AS") | whitespace ) + columnName

	valueExpression = Forward()

# set functions
	setFunctionType = Regex("(?i)AVG|MAX|MIN|SUM|COUNT")
	setQuantifier = Regex("(?i)DISTINCT|ALL")
	generalSetFunction = (setFunctionType + '(' + Optional( setQuantifier ) +
		valueExpression + ')')
	countAll = CaselessLiteral("COUNT") + '(' + '*' + ')'
	setFunctionSpecification = (countAll | generalSetFunction)

# value expressions
	valueExpressionPrimary = ( unsignedLiteral |
		columnReference | setFunctionSpecification |
		'(' + valueExpression + ')')

# string literal stuff
	characterPrimary = Forward() 
	characterFactor = characterPrimary
	characterValueExpression = ( characterFactor + 
		ZeroOrMore( "||" + characterFactor ))
	stringValueExpression = characterValueExpression

# numeric expressions/terms
	numericValueExpression = Forward()
	numericValueFunction = Forward()
	numericExpressionPrimary = ( unsignedLiteral | columnReference
		| setFunctionSpecification | '(' + valueExpression + ')')
	numericPrimary = numericValueFunction | valueExpressionPrimary 
	factor = Optional( sign ) + numericPrimary
	term = Forward()
	term << (factor + ZeroOrMore( multOperator + factor ))
	numericValueExpression << (term + ZeroOrMore( ( Literal("+") | "-" ) + term ))

# geometry types and expressions
	coordSys = stringValueExpression
	coordinates = numericValueExpression + ',' + numericValueExpression
	point = (CaselessKeyword("POINT") + '(' + coordSys + ',' + 
		coordinates + ')')
	circle = (CaselessKeyword("CIRCLE") + '(' + coordSys + ',' +
		coordinates + ',' + numericValueExpression + ')')
	rectangle = (CaselessKeyword("RECTANGLE") +  '(' + coordSys + ',' +
		coordinates + ',' + coordinates + ')')
	polygon = (CaselessKeyword("POLYGON") + '(' + coordSys + ',' +
		coordinates + OneOrMore( ',' + coordinates ) + ')')
	region = (CaselessKeyword("REGION") + '(' + stringValueExpression + ')')
	geometryExpression = point | circle | rectangle | polygon | region
	geometryValue = columnReference.copy()
	coordValue = point | columnReference
	centroid = CaselessKeyword("CENTROID") + '(' + geometryExpression + ')'
	geometryValueExpression = geometryExpression | geometryValue | centroid

# geometry functions
	distanceFunction = (CaselessKeyword("DISTANCE") + '(' + coordValue + ',' +
		coordValue + ')')
	pointFunction = (Regex("(?i)COORD[12]|COORDSYS") + '(' +
		coordValue + ')')
	area = CaselessKeyword("AREA") + '(' + geometryValueExpression + ')'
	nonPredicateGeometryFunction = (distanceFunction | pointFunction | area)
	predicateGeoFunctionName = Regex("(?i)CONTAINS|INTERSECTS")
	predicateGeometryFunction = (predicateGeoFunctionName + '(' + 
		geometryValueExpression + ',' + geometryValueExpression + ')')
	numericGeometryFunction = (predicateGeometryFunction | 
		nonPredicateGeometryFunction)


# numeric, system, user defined functions
	trig1ArgFunctionName = Regex("(?i)ACOS|ASIN|ATAN|COS|COT|SIN|TAN")
	trigFunction = (trig1ArgFunctionName + '(' + numericValueExpression + ')' |
		CaselessKeyword("ATAN2") + '(' + numericValueExpression + ',' + 
			numericValueExpression + ')')
	math0ArgFunctionName = Regex("(?i)PI")
	optIntFunctionName = Regex("(?i)RAND")
	math1ArgFunctionName = Regex("(?i)ABS|CEILING|DEGREES|EXP|FLOOR|LOG10|"
		"LOG|RADIANS|SQUARE|SQRT")
	optPrecArgFunctionName = Regex("(?i)ROUND|TRUNCATE")
	math2ArgFunctionName = Regex("(?i)POWER")
	mathFunction = (math0ArgFunctionName + '(' + ')' |
		optIntFunctionName + '(' + Optional( unsignedInteger ) + ')' |
		math1ArgFunctionName + '(' + numericValueExpression + ')' |
		optPrecArgFunctionName + '(' + numericValueExpression +
			Optional( ',' + signedInteger ) + ')' |
		math2ArgFunctionName + '(' + numericValueExpression + ',' +
			unsignedInteger + ')')
	userDefinedFunctionParam = valueExpression
	userDefinedFunctionName = Regex(userFunctionPrefix+"[A-Za-z_]+")
	userDefinedFunction = ( userDefinedFunctionName + '(' +
		userDefinedFunctionParam + ZeroOrMore( "," + userDefinedFunctionParam ) 
			+ ')')
	numericValueFunction << (trigFunction | mathFunction | userDefinedFunction |
		numericGeometryFunction)

	characterPrimary << (generalLiteral | valueExpressionPrimary | 
		userDefinedFunction)

# toplevel value expression
	valueExpression << (numericValueExpression | stringValueExpression |
		geometryValueExpression)
	derivedColumn = valueExpression + Optional( asClause )

# parts of select clauses
	setQuantifier = (CaselessKeyword( "DISTINCT" ) 
		| CaselessKeyword( "ALL" ))("setQuantifier")
	setLimit = CaselessKeyword( "TOP" ) + unsignedInteger("setLimit")
	selectSublist = derivedColumn | qualifier + "." + "*"
	selectList = ("*" 
		| selectSublist + ZeroOrMore( "," + selectSublist ))("selectList")

# boolean terms
	subquery = Forward()
	searchCondition = Forward()
	comparisonPredicate = valueExpression + compOp + valueExpression
	betweenPredicate = (valueExpression + Optional( notKeyword ) + 
		CaselessKeyword("BETWEEN") + valueExpression + 
		CaselessKeyword("AND") + valueExpression)
	inValueList = valueExpression + ZeroOrMore( ',' + valueExpression )
	inPredicateValue = subquery | ( "(" + inValueList + ")" )
	inPredicate = (valueExpression + Optional( notKeyword ) + 
		CaselessKeyword("IN") + inPredicateValue)
	existsPredicate = CaselessKeyword("EXISTS") + subquery
	likePredicate = (characterValueExpression + Optional( notKeyword ) + 
		CaselessKeyword("LIKE") + characterValueExpression)
	nullPredicate = (columnReference + CaselessKeyword("IS") +
		Optional( notKeyword ) + CaselessKeyword("NULL"))
	predicate = (comparisonPredicate | betweenPredicate | inPredicate | 
		likePredicate | nullPredicate | existsPredicate)
	booleanPrimary = '(' + searchCondition + ')' | predicate
	booleanFactor = Optional( notKeyword ) + booleanPrimary
	booleanTerm = ( booleanFactor + 
		ZeroOrMore( CaselessKeyword("AND") + booleanFactor ))

# WHERE clauses and such
	searchCondition << ( booleanTerm + 
		ZeroOrMore( CaselessKeyword("OR") + booleanTerm ))
	whereClause = (CaselessKeyword("WHERE") + searchCondition)("whereClause")

# Referencing tables
	queryExpression = Forward()
	correlationSpecification = (( CaselessKeyword("AS") | whitespace
		) + correlationName("alias"))("corrSpec")
	subquery << ('(' + queryExpression + ')')
	derivedTable = subquery.copy() + correlationSpecification
	joinedTable = Forward()
	possiblyAliasedTable = tableName + Optional( correlationSpecification)
	nojoinTableReference =  possiblyAliasedTable | derivedTable
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
	groupByClause = (CaselessKeyword( "GROUP" ) + CaselessKeyword( "BY" ) 
		+ columnReference 
		+ ZeroOrMore( ',' + columnReference ))("groupby")
	havingClause = (CaselessKeyword( "HAVING" ) 
		+ searchCondition)("having")
	orderingSpecification = (CaselessKeyword( "ASC") 
		| CaselessKeyword("DESC"))
	sortKey = columnName | unsignedInteger
	sortSpecification = sortKey + Optional( orderingSpecification )
	orderByClause = (CaselessKeyword("ORDER") 
		+ CaselessKeyword("BY") + sortSpecification 
		+ ZeroOrMore( ',' + sortSpecification ))("orderBy")

# FROM fragments and such
	fromClause = ( CaselessKeyword("FROM") 
		+ tableReference 
		+ ZeroOrMore( ',' + tableReference ))("fromClause")
	tableExpression = (fromClause + Optional( whereClause ) 
		+ Optional( groupByClause )  + Optional( havingClause ) 
		+ Optional( orderByClause ))

# toplevel select clause
	querySpecification = Forward()
	queryExpression << ( querySpecification |  joinedTable )
	querySpecification << ( CaselessKeyword("SELECT") 
		+ Optional( setQuantifier )
		+ Optional( setLimit ) 
		+ selectList + tableExpression )
	statement = querySpecification + Optional( White() ) + StringEnd()
	ParserElement.setDefaultWhitespaceChars("\t ")
	return dict((k, v) for k, v in locals().iteritems()
		if isinstance(v, ParserElement)), statement


_grammarCache = None

def enableDebug(syms, debugNames=None):
	if not debugNames:
		debugNames = syms
	for name in debugNames:
		ob = syms[name]
		if not ob.debug:
			ob.setDebug(True)
			ob.setName(name)


def enableTree(syms):
	def makeAction(name):
		def action(s, pos, toks):
			return [name, toks]
		return action
	for name in syms:
		ob = syms[name]
		if not ob.debug:
			ob.setDebug(True)
			ob.setName(name)
			ob.addParseAction(makeAction(name))


def getADQLGrammar():
	"""returns a pair of (symbols, root) for an ADQL grammar.

	This probably is mainly useful for testing.  At least you should not set
	names or parseActions on whatever you are returned unless you are
	testing.
	"""
	global _grammarCache
	if not _grammarCache:
		_grammarCache = getADQLGrammarCopy()
	return _grammarCache


if __name__=="__main__":
	def printCs(s, pos, toks):
		print ">>>>>>>>>>>>>>>", toks
	import pprint, sys
	syms, grammar = getADQLGrammar()
	enableTree(syms)
	lit = sglQuotedString + Optional(syms["separator"] + sglQuotedString)
	res = syms["statement"].parseString("select * from\r\n browndwarfs.cat\r\n"
			,parseAll=True)
	pprint.pprint(res.asList(), stream=sys.stderr)
