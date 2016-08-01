"""
Tests for ADQL parsing and reasoning about query results.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os
import re
import unittest
from pprint import pprint

from gavo.helpers import testhelpers

from gavo import adql
from gavo import base
from gavo import stc
from gavo import rsc
from gavo import rscdef
from gavo import utils
from gavo.adql import annotations
from gavo.adql import morphpg
from gavo.adql import nodes
from gavo.adql import tree
from gavo.imp import pyparsing
from gavo.protocols import adqlglue
from gavo.protocols import tap
from gavo.stc import tapstc

import tresc

MS = base.makeStruct

class Error(Exception):
	pass


# The resources below are used elsewhere (e.g., taptest).
class _ADQLQuerier(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]

	def make(self, deps):
		return base.UnmanagedQuerier(deps["conn"])
	
	def cleanup(self, deps):
		deps["conn"].rollback()

adqlQuerier = _ADQLQuerier()


class _ADQLTestTable(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]

	def make(self, deps):
		self.rd = testhelpers.getTestRD()
		ds = rsc.makeData(self.rd.getById("ADQLTest"),
				connection=deps["conn"])
		tap.publishToTAP(self.rd, deps["conn"])
		return ds
	
	def clean(self, ds):
		ds.tables.values()[0].connection.rollback()
		ds.dropTables(rsc.parseNonValidating)
		ds.commitAll().closeAll()
adqlTestTable = _ADQLTestTable()


class SymbolsParseTest(testhelpers.VerboseTest):
	"""tests for plain parsing on individual productions.
	"""
	def setUp(self):
		self.symbols, _ = adql.getRawGrammar()

	def _assertParses(self, symbol, literal):
		try:
			(self.symbols[symbol]+pyparsing.StringEnd()).parseString(literal)
		except adql.ParseException:
			raise AssertionError("%s doesn't parse %s but should."%(symbol,
				repr(literal)))

	def _assertDoesntParse(self, symbol, literal):
		try:
			(self.symbols[symbol]+pyparsing.StringEnd()).parseString(literal)
		except (adql.ParseException, adql.ParseSyntaxException):
			pass
		else:
			raise AssertionError("%s parses %s but shouldn't."%(symbol,
				repr(literal)))

	def testGeometries(self):
		self._assertParses("point", "pOint('ICRS', x,y)")
		self._assertParses("circle", "circle('ICRS', x,y, r)")
		self._assertParses("circle", "CIRCLE('ICRS', 1,2, 4)")
		self._assertParses("geometryExpression", "CIRCLE('ICRS', 1,2, 4)")
		self._assertParses("predicateGeometryFunction", 
			"Contains(pOint('ICRS', x,y),CIRCLE('ICRS', 1,2, 4))")

	def testBadGeometries(self):
		self._assertDoesntParse("point", "POINT(x,y)")
		self._assertDoesntParse("circle", "circle('ICRS', x,y)")
		self._assertDoesntParse("geometryExpression", "circle('ICRS', x,y)")

	def testStringExprs(self):
		self._assertParses("stringValueExpression", "'abc'")
		self._assertParses("stringValueExpression", "'abc' || 'def'")
		self._assertParses("stringValueExpression", "'abc' || 'def' || '78%%'")

	def testComparisons(self):
		self._assertParses("comparisonPredicate", "a<b")
		self._assertParses("comparisonPredicate", "'a'<'b'")
		self._assertParses("comparisonPredicate", "'a'<'b' || 'foo'")
		self._assertParses("comparisonPredicate", "5+9<'b' || 'foo'")

	def testConditions(self):
		self._assertParses("searchCondition", "5+9<'b' || 'foo'")
	
	def testDelId(self):
		self._assertParses("delimitedIdentifier", '"a"')
		self._assertParses("delimitedIdentifier", '"a""b"')
		self._assertParses("comparisonPredicate", '"ja ja"<"Umph"')


class _ADQLParsesTest(testhelpers.VerboseTest):
	"""an abstract base for tests checking whether ADQL expressions parse.
	"""
	def setUp(self):
		_, self.grammar = adql.getRawGrammar()
		testhelpers.VerboseTest.setUp(self)

	def _assertGoodADQL(self, statement):
		try:
			self.grammar.parseString(statement)
		except (adql.ParseException, adql.ParseSyntaxException):
			raise AssertionError("%s doesn't parse but should."%statement)
		except RuntimeError:
			raise Error("%s causes an infinite recursion"%statement)

	def _assertBadADQL(self, statement):
			try:
				self.assertRaisesVerbose(
					(adql.ParseException,adql.ParseSyntaxException), 
					self.grammar.parseString, (statement,), 
					"Parses but shouldn't: %s"%statement)
			except RuntimeError:
				raise Error("%s causes an infinite recursion"%statement)


class NakedParseTest(_ADQLParsesTest):
	"""tests for plain parsing (without tree building).
	"""
	def _assertParse(self, correctStatements):
		for stmt in correctStatements:
			self._assertGoodADQL(stmt)

	def _assertDontParse(self, badStatements):
		for stmt in badStatements:
			self._assertBadADQL(stmt)

	def testPlainSelects(self):
		"""tests for non-errors on some elementary select expressions parse.
		"""
		self._assertParse([
				"SELECT x FROM y",
				"SELECT x FROM y WHERE z=0",
				"SELECT x, v FROM y WHERE z=0 AND v>2",
				"SELECT 89 FROM X",
			])

	def testDelimited(self):
		self._assertParse([
			'SELECT "f-bar", "c""ho" FROM "nons-ak" WHERE "ja ja"<"Umph"'])

	def testSimpleSyntaxErrors(self):
		"""tests for rejection of gross syntactic errors.
		"""
		self._assertDontParse([
				"W00T",
				"SELECT A",
				"SELECT A FROM",
				"SELECT A FROM B WHERE",
				"SELECT FROM",
				"SELECT 89x FROM z",
			])

	def testCaseInsensitivity(self):
		"""tests for case being ignored in SQL keywords.
		"""
		self._assertParse([
				"select z as U From n",
				"seLect z AS U FROM n",
			])

	def testJoins(self):
		"""tests for JOIN syntax.
		"""
		self._assertParse([
			"select x from t1, t2",
			"select x from t1, t2, t3",
			"select x from t1, t2, t3 WHERE t1.x=t2.y",
			"select x from t1 JOIN t2",
			"select x from t1 NATURAL JOIN t2",
			"select x from t1 LEFT OUTER JOIN t2",
			"select x from t1 RIGHT OUTER JOIN t2",
			"select x from t1 FULL OUTER JOIN t2",
			"select x from t1 FULL OUTER JOIN t2 ON (x=y)",
			"select x from t1 FULL OUTER JOIN t2 USING (x,y)",
			"select x from t1 INNER JOIN (t2 JOIN t3)",
			"select x from (t1 JOIN t4) FULL OUTER JOIN (t2 JOIN t3)",
			"select x from t1 NATURAL JOIN t2, t3",
		])

	def testBadJoins(self):
		"""tests for syntax error detection in JOINs.
		"""
		self._assertDontParse([
			"select x from t1 JOIN",
			"select x from JOIN t1",
			"select x from t1 quatsch JOIN t1",
			"select x from t1 NATURAL JOIN t2, t3 OUTER",
			"select x from t1 NATURAL JOIN t2, t3 ON",
			"select x from t1, t2, t3 ON",
		])

	def testDetritus(self):
		"""tests for ORDER BY and friends.
		"""
		self._assertParse([
			"select x from t1 order by z",
			"select x from t1 order by z desc",
			"select x from t1 order by z desc, x asc",
			"select x from t1 group by z",
			"select x from t1 group by z, s",
			"select x from t1 having x=z AND 7<u",
		])

	def testBadDetritus(self):
		"""tests for syntax errors in ORDER BY and friends.
		"""
		self._assertDontParse([
			"select x from t1 having y",
		])

	def testBooleanTerms(self):
		p = "select x from y where "
		self._assertParse([p+"z BETWEEN 8 AND 9",
			p+"z BETWEEN 'a' AND 'b'",
			p+"z BEtWEEN x+8 AnD x*8",
			p+"z NOT BETWEEN x+8 AND x*8",
			p+"z iN (a)",
			p+"z NoT In (a)",
			p+"z NOT IN (a, 4, 'xy')",
			p+"z IN (select x from foo)",
#			p+"(5, 6) IN (select x from foo)",
			p+"u LIKE '%'",
			p+"u NoT LiKE '%'",
			p+"u || 'foo' NOT LIKE '%'",
			p+"u NOT LIKE '%' || 'xy'",
			p+"k IS NULL",
			p+"k IS NOT NULL",
		])

	def testBadBooleanTerms(self):
		p = "select x from y where "
		self._assertDontParse([
			p+"z BETWEEN",
			p+"z BETWEEN AND",
			p+"z BETWEEN AND 5",
			p+"z 7 BETWEEN 5 AND ",
			p+"x IN",
			p+"x IN 5",
			p+"x IN (23, 3,)",
			p+"x Is None",
		])
	
	def testGeometry(self):
		"""tests for parsing of ADQL geometry primitives.
		"""
		p = "select x from y where "
		self._assertParse([
			p+"Point(NULL, 2, 3)=x",
			p+"Point('fk5', 2, 3)=x",
			p+"CIRCLE('fk5', 2, 3, 3)=x",
			p+"box('fk5', 2, 3, 3, 0)=x",
			p+"POLYGON('fk5', 2, 3, 3, 0, 23, 0, 45, 34)=x",
			p+"REGION('mainfranken')=x",
			p+"CENTROID(CIRCLE('fk4', 2, 3, 3))=x",
		])
	
	def testBadGeometry(self):
		"""tests for rejection of bad geometry primitives.
		"""
		p = "select x from y where "
		self._assertDontParse([
			p+"Point('fk5',2,3)",
			p+"Point(2,3)=x",
			p+"CIRCLE('fk5', 2, 3)=x",
			p+"POLYGON('fk5', 2, 3, 3, 0, 23, 0, 45)=x",
			p+"CENTROID(3)=x",
			p+"CENTROID(COUNT(*))=x",
		])

	def testsBadFunctions(self):
		"""tests for rejection of bad function calls.
		"""
		p = "select x from y where "
		self._assertDontParse([
			p+"ABS()<3",
			p+"ABS(y,z)<3",
			p+"ATAN2(x)<3",
			p+"PI==3",
		])
	
	def testFunkyIds(self):
		"""tests for parsing quoted identifiers.
		"""
		p = "select x from y where "
		self._assertParse([
			p+'"some weird column">0',
			p+'"some even ""weirder"" column">0',
			p+'"SELECT">0',
		])

	def testMiscGood(self):
		"""tests for parsing of various legal statements.
		"""
		self._assertParse([
			"select a, b from (select * from x) AS q",
		])

	def testMiscBad(self):
		"""tests for rejection of various bad statements.
		"""
		self._assertDontParse([
			"select a, b from (select * from x) q",
			"select a, b from (select * from x)",
			"select x.y.z.a.b from a",
			"select x from a.b.c.d",
		])

	def testStringExpressionSelect(self):
		self._assertParse([
			"select m || 'ab' from q",])


class FunctionsParseTest(_ADQLParsesTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self._assertGoodADQL("select x from y where "+sample)

	samples = [
		"ABS(-3)<3",
		"ABS(-3.0)<3",
		"ABS(-3.0E4)<3",
		"ABS(-3.0e-4)<3",
		"ABS(x)<3",
		"ATAN2(-3.0e-4, 4.5)=x",
		"RAND(4)=x",
		"RAND()=x",
		"ROUND(23)=x",
		"ROUND(23,2)=x",
		"ROUND(PI(),2)=3.14",
		"POWER(x,10)=3.14",
		"POWER(10,x)=3.14",
		"1=CROSSMATCH(ra1, dec1, ra2, dec2, 0.001)"
	]


class SetExpressionsTest(_ADQLParsesTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		self._assertGoodADQL(sample)
	
	samples = [
		"select x from t1 union select x from t2",
		"select x from t1 intersect select x from t2",
		"select x from t1 except select x from t2",
		"select x from t1 where x>2 union select x from t2",
		"select * from t1 union select x from t2 intersect select x from t3"
			" except select x from t4",
# 5
		"select * from (select * from t1 except select * from t2) as q union"
			" select * from  t3",
		"select * from t1 union select foo from (select * from t2 except select * from t1) as q",
	]


class AsTreeTest(testhelpers.VerboseTest):
	"""tests for asTree()
	"""
	def testSimple(self):
		t = adql.parseToTree("SELECT * FROM t WHERE 1=CONTAINS("
			"CIRCLE('ICRS', 4, 4, 2), POINT('', ra, dec))").asTree()
		self.assertEqual(t[1][1][1][0], 'possiblyAliasedTable')
		self.assertEqual(t[1][3][0], 'whereClause')
		self.assertEqual(t[1][3][1][2][1][0], 'circle')


class TreeParseTest(testhelpers.VerboseTest):
	"""tests for parsing into ADQL trees.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()
	
	def testSelectList(self):
		for q, e in [
			("select a from z", ["a"]),
			("select x.a from z", ["a"]),
			("select x.a, b from z", ["a", "b"]),
			('select "one weird name", b from z', 
				[utils.QuotedName('one weird name'), "b"]),
		]:
			res = [c.name for c in self.grammar.parseString(q)[0].getSelectFields()]
			self.assertEqual(res, e, 
				"Select list from %s: expected %s, got %s"%(q, e, res))

	def testSourceTables(self):
		for q, e in [
			("select * from z", ["z"]),
			("select * from z.x", ["z.x"]),
			("select * from z.x.y", ["z.x.y"]),
			("select * from z.x.y, a", ["z.x.y", "a"]),
			("select * from (select * from z) as q, a", ["q", "a"]),
		]:
			res = list(self.grammar.parseString(q)[0].getAllNames())
			self.assertEqual(res, e, 
				"Source tables from %s: expected %s, got %s"%(q, e, res))

	def testSourceTablesJoin(self):
		for q, e in [
			("select * from z join x", ["z", "x"]),
			("select * from (select * from a,b, (select * from c,d) as q) as r join"
				"(select * from x,y) as p", ["r", "p"]),
		]:
			res = list(self.grammar.parseString(q)[0].getAllNames())
			self.assertEqual(res, e, 
				"Source tables from %s: expected %s, got %s"%(q, e, res))

	def testContributingTables(self):
		q = ("select * from (select * from urks.a,b,"
			" (select * from c,monk.d) as q) as r join"
			" (select * from x,y) as p")
		self.grammar.parseString(q)[0].getContributingNames()
		self.assertEqual(self.grammar.parseString(q)[0].getContributingNames(),
			set(['c', 'b', 'urks.a', 'q', 'p', 'r', 'y', 'x', 'monk.d']))

	def testAliasedColumn(self):
		q = "select foo+2 as fp2 from x"
		res = self.grammar.parseString(q)[0]
		field = list(res.getSelectFields())[0]
		self.assertEqual(field.name, "fp2")
	
	def testTainting(self):
		for q, (exName, exTaint) in [
			("select x from z", ("x", False)),
			("select x as u from z", ("u", False)),
			("select x+2 from z", (None, True)),
			('select x+2 as "99 Monkeys" from z', (utils.QuotedName("99 Monkeys"), 
				True)),
			('select x+2 as " ""cute"" Monkeys" from z', 
				(utils.QuotedName(' "cute" Monkeys'), True)),
		]:
			res = list(self.grammar.parseString(q)[0].getSelectFields())[0]
			self.assertEqual(res.tainted, exTaint, "Field taintedness wrong in %s"%
				q)
			if exName:
				self.assertEqual(res.name, exName)

	def testValueExpressionColl(self):
		t = adql.parseToTree("select x from z where 5+9>'gaga'||'bla'")
		compPred = t.whereClause.children[1]
		self.assertEqual(compPred.op1.type, "numericValueExpression")
		self.assertEqual(compPred.opr, ">")
		self.assertEqual(compPred.op2.type, "stringValueExpression")

	def testQualifiedStar(self):
		t = adql.parseToTree("select t1.*, s1.t2.* from t1, s1.t2, s2.t3")
		self.assertEqual(t.selectList.selectFields[0].type, "qualifiedStar")
		self.assertEqual(t.selectList.selectFields[0].sourceTable.qName,
			"t1")
		self.assertEqual(t.selectList.selectFields[1].sourceTable.qName,
			"s1.t2")

	def testBadSystem(self):
		self.assertRaises(adql.ParseSyntaxException, 
			self.grammar.parseString, "select point('QUARK', 1, 2) from spatial")

	def testQuotedTableName(self):
		t = adql.parseToTree('select "abc-g".* from "abc-g" JOIN "select"')
		self.assertEqual(t.selectList.selectFields[0].sourceTable.name, "abc-g")
		self.assertEqual(t.selectList.selectFields[0].sourceTable.qName, '"abc-g"')

	def testQuotedSchemaName(self):
		t = adql.parseToTree('select * from "Murks Schema"."Murks Tabelle"')
		table = t.fromClause.tableReference
		self.assertEqual(table.tableName.name,
			utils.QuotedName("Murks Tabelle"))
		self.assertEqual(table.tableName.schema,
			utils.QuotedName("Murks Schema"))
	
	def testSetLimitInherited(self):
		t = adql.parseToTree('select top 3 * from t1 union'
			' select top 4 * from t2 except select * from t3')
		self.assertEqual(t.setLimit, 4)
	
	def testSetLimitDeep(self):
		t = adql.parseToTree(
			'select top 7 * from t1 union'
			' (select top 4 * from t2 except select * from t3)'
			' except (select top 30 x from t4 except select top 3 y from t5)')
		self.assertEqual(t.setLimit, 30)


class ParseErrorTest(testhelpers.VerboseTest):
	"""tests for sensible error messages.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		query, msgFragment = sample
		try:
			res = adql.getGrammar().parseString(query, parseAll=True)
		except (adql.ParseException, adql.ParseSyntaxException), ex:
			msg = unicode(ex)
			self.failUnless(msgFragment in msg,
				"'%s' does not contain '%s'"%(msg, msgFragment))
		else:
			self.fail("'%s' parses but should not"%query)

	samples = [
		("", 'Expected "SELECT" (at char 0)'),
		("select mag from %s", 'Expected identifier (at char 16)'),
		("SELECT TOP foo FROM x", 'Expected unsigned integer (at char 11)'),
		("SELECT FROM x", 'Expected "*" (at char 7)'),
		("SELECT x, FROM y", 'Reserved word not allowed here (at char 10)'),
#5
		("SELECT * FROM distinct", 'Reserved word not allowed here (at char 14)'),
		("SELECT DISTINCT FROM y", 'Expected "*" (at char 16)'),
		("SELECT *", 'Expected "FROM" (at char 8)'),
		("SELECT * FROM y WHERE", 'Expected boolean expression (at char 21)'),
		("SELECT * FROM y WHERE y u 2", 
			'Expected comparison operator (at char 24)'),
# 10
		("SELECT * FROM y WHERE y < 2 AND", 
			'Expected boolean expression (at char 31)'),
		("SELECT * FROM y WHERE y < 2 OR", 
			'Expected boolean expression (at char 30)'),
		("SELECT * FROM y WHERE y IS 3", 'Expected "NULL" (at char 27)'),
		("SELECT * FROM y WHERE CONTAINS(a,b)", 
			'Expected comparison operator (at char 35)'),
		("SELECT * FROM y WHERE 1=CONTAINS(POINT('ICRS',x,'sy')"
			" ,CIRCLE('ICRS',x,y,z))", 
			'Expected numeric expression (at char 48)'),
# 15
		("SELECT * FROM (SELECT * FROM x)", 'Expected "AS" (at char 31)'),
		("SELECT * FROM x WHERE EXISTS z", 'Expected subquery (at char 29)'),
		("SELECT POINT(3,4) FROM z", 
			'Expected coordinate system literal (ICRS, GALACTIC,...) (at char 13)'),
		("SELECT POINT('junk', 3,4) FROM z",
			"xpected coordinate system literal (ICRS, GALACTIC,...) (at char 13)"),
		("SELECT * from a join b on foo",
			"Expected comparison operator (at char 29"),
# 20
		("SELECT * from a OFFSET 20 join b on foo",
			"Expected end of text (at char 26)"),
		("SELECT * from a natural join b OFFSET banana",
			"Expected unsigned integer (at char 38)"),
	]


class JoinTypeTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	sym = adql.getSymbols()["joinedTable"]

	def _collectJoinTypes(self, joinedNode):
		res = []
		if hasattr(joinedNode.leftOperand, "leftOperand"):
			res.extend(self._collectJoinTypes(joinedNode.leftOperand))
		res.append(joinedNode.getJoinType())
		if hasattr(joinedNode.rightOperand, "leftOperand"):
			res.extend(self._collectJoinTypes(joinedNode.rightOperand))
		return res

	def _runTest(self, sample):
		query, joinType = sample
		self.assertEqual(
			self._collectJoinTypes(self.sym.parseString(query)[0]), joinType)
	
	samples = [
		("a,b", ["CROSS"]),
		("a join b", ["NATURAL"]),
		("a join b using (x)", ["USING"]),
		("a,b,c", ["CROSS", "CROSS"]),
		("a,b join c", ["CROSS", "NATURAL"]),
#5
		("a join b, c", ["NATURAL", "CROSS"]),
		("a join b on (x=y), c", ["CROSS", "CROSS"]),
		("a join b using (x,y) join c", ["USING", "NATURAL"]),
		("a join b using (x,y) join c using (z,v)", ["USING", "USING"]),
		("(a join b using (x,y)) join c using (z,v)", ["USING", "USING"]),
# 10
		("(a join b) cross join (c join d)", ["NATURAL", "CROSS", "NATURAL"]),
	]


spatialFields = [
	MS(rscdef.Column, name="dist", ucd="phys.distance", unit="m"),
	MS(rscdef.Column, name="width", ucd="phys.dim", unit="m"),
	MS(rscdef.Column, name="height", ucd="phys.dim", unit="km"),
	MS(rscdef.Column, name="ra1", ucd="pos.eq.ra", unit="deg"),
	MS(rscdef.Column, name="ra2", ucd="pos.eq.ra", unit="rad"),]
spatial2Fields = [
	MS(rscdef.Column, name="ra1", ucd="pos.eq.ra;meta.main", unit="deg"),
	MS(rscdef.Column, name="dec", ucd="pos.eq.dec;meta.main", unit="deg"),
	MS(rscdef.Column, name="dist", ucd="phys.distance", unit="m"),]
miscFields = [
	MS(rscdef.Column, name="mass", ucd="phys.mass", unit="kg"),
	MS(rscdef.Column, name="mag", ucd="phot.mag", unit="mag"),
	MS(rscdef.Column, name="speed", ucd="phys.veloc", unit="km/s")]
quotedFields = [
	MS(rscdef.Column, name=utils.QuotedName("left-right"), ucd="mess", 
		unit="bg"),
	MS(rscdef.Column, name=utils.QuotedName('inch"ing'), ucd="imperial.mess",
		unit="fin"),
	MS(rscdef.Column, name=utils.QuotedName('plAin'), ucd="boring.stuff",
		unit="pc"),
	MS(rscdef.Column, name=utils.QuotedName('alllower'), ucd="simple.case",
		unit="km"),]
crazyFields = [
	MS(rscdef.Column, name="ct", type="integer"),
	MS(rscdef.Column, name="wot", type="bigint", 
		values=MS(rscdef.Values, nullLiteral="-1")),
	MS(rscdef.Column, name="wotb", type="bytea", 
		values=MS(rscdef.Values, nullLiteral="254")),
	MS(rscdef.Column, name="mass", ucd="event;using.incense"),
	MS(rscdef.Column, name="name", type="unicode"),
	MS(rscdef.Column, name="version", type="text"),
	MS(rscdef.Column, name="flag", type="char"),]
geoFields = [
	MS(rscdef.Column, name="pt", type="spoint"),
]

def _addSpatialSTC(sf, sf2):
	ast1 = stc.parseQSTCS('Position ICRS "ra1" "dec" Size "width" "height"')
	ast2 = stc.parseQSTCS('Position FK4 SPHER3 "ra2" "dec" "dist"')
	# XXX TODO: get utypes from ASTs
	sf[0].stc, sf[0].stcUtype = ast2, None
	sf[1].stc, sf[1].stcUtype = ast1, None
	sf[2].stc, sf[2].stcUtype = ast1, None
	sf[3].stc, sf[3].stcUtype = ast1, None
	sf[4].stc, sf[4].stcUtype = ast2, None
	sf2[0].stc, sf2[0].stcUtype = ast1, None
	sf2[1].stc, sf2[0].stcUtype = ast1, None
	sf2[2].stc, sf2[0].stcUtype = ast2, None
_addSpatialSTC(spatialFields, spatial2Fields)


@utils.memoized
def _sampleFieldInfoGetter(tableName):
	if tableName=='spatial':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in spatialFields]
	elif tableName=='spatial2':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in spatial2Fields]
	elif tableName=='misc':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in miscFields]
	elif tableName=='quoted':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in quotedFields]
	elif tableName=='crazy':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in crazyFields]
	elif tableName=='geo':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in geoFields]


def parseWithArtificialTable(query):
	parsedTree = adql.getGrammar().parseString(query)[0]
	ctx = adql.annotate(parsedTree, _sampleFieldInfoGetter)
	return parsedTree


class TypecalcTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		inTypes, result = sample
		self.assertEqual(adql.getSubsumingType(inTypes), result)
	
	samples = [
		(["double precision", "integer", "bigint"], 'double precision'),
		(["date", "timestamp", "timestamp"], 'timestamp'),
		(["date", "boolean", "smallint"], 'text'),
		(["box", "raw"], 'raw'),
		(["date", "time"], 'timestamp'),
# 5
		(["char(3)", "integer"], "text"),
		(["double precision", "char(3)"], "text"),
		(["integer[3]", "bigint"], "bigint[]"),
		(["integer", "smallint", "double precision[]"], "double precision[]"),
		(["integer[][]", "smallint", "double precision[]"], "double precision[]"),
# 10
		# I would give you the next is plain wrong, but I'm relying on postgres
		# to reject such nonsence in the first place.
		(["double precision[340]", "char(3)"], "text"),
		(["boolean", "boolean"], "boolean"),
		(["boolean", "smallint"], "smallint"),
		(["sbox", "spoint"], "text"),
		(["sbox", "spoly"], "spoly"),
		(["sbox", "whacko"], "raw"),
	]


class ColumnTest(testhelpers.VerboseTest):
	def setUp(self):
		self.fieldInfoGetter = _sampleFieldInfoGetter
		self.grammar = adql.getGrammar()

	def _getColSeqAndCtx(self, query):
		t = self.grammar.parseString(query)[0]
		ctx = adql.annotate(t, self.fieldInfoGetter)
		return t.fieldInfos.seq, ctx

	def _getColSeq(self, query):
		return self._getColSeqAndCtx(query)[0]

	def _assertColumns(self, resultColumns, assertProperties):
		self.assertEqual(len(resultColumns), len(assertProperties))
		for index, ((name, col), (type, unit, ucd, taint)) in enumerate(zip(
				resultColumns, assertProperties)):
			if type is not None:
				self.assertEqual(col.type, type, "Type %d: %r != %r"%
					(index, col.type, type))
			if unit is not None:
				self.assertEqual(col.unit, unit, "Unit %d: %r != %r"%
					(index, col.unit, unit))
			if ucd is not None:
				self.assertEqual(col.ucd, ucd, "UCD %d: %r != %r"%
					(index, col.ucd, ucd))
			if taint is not None:
				self.assertEqual(col.tainted, taint, "Taint %d: should be %s"%
					(index, taint))


class SelectClauseTest(ColumnTest):
	def testConstantSelect(self):
		cols = self._getColSeq("select 1, 'const' from spatial")
		self._assertColumns(cols, [
			("smallint", "", "", False),
			("text", "", "", False),])

	def testConstantExprSelect(self):
		cols = self._getColSeq("select 1+0.1, 'const'||'ab' from spatial")
		self._assertColumns(cols, [
			("double precision", "", "", True),
			("text", "", "", True),])

	def testConstantSelectWithAs(self):
		cols = self._getColSeq("select 1+0.1 as x from spatial")
		self._assertColumns(cols, [
			("double precision", "", "", True),])

	def testSimpleColumn(self):
		cols = self._getColSeq("select mass from misc")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False),])

	def testBadRefRaises(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq, 
			"select x, foo.* from spatial, misc")

	def testQualifiedStarSingle(self):
		cols = self._getColSeq("select misc.* from misc")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False),
			("real", "mag", "phot.mag", False),
			("real", "km/s", "phys.veloc", False),])

	def testQualifiedStar(self):
		cols = self._getColSeq("select misc.* from spatial, misc")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False),
			("real", "mag", "phot.mag", False),
			("real", "km/s", "phys.veloc", False),])

	def testMixedQualifiedStar(self):
		cols = self._getColSeq("select misc.*, dist, round(mass/10)"
			" from spatial, misc")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False),
			("real", "mag", "phot.mag", False),
			("real", "km/s", "phys.veloc", False),
			("real", "m", "phys.distance", False),
			("double precision", "kg", "phys.mass", True),])

	def testAliasedStar(self):
		cols = self._getColSeq("select misc.* from spatial join misc as foo"
			" on (spatial.dist=foo.mass)")
		self.assertEqual(len(cols), 3)

	def testFancyRounding(self):
		cols = self._getColSeq("select round(dist, 2) from spatial")
		self._assertColumns(cols, [
			("double precision", "m", "phys.distance", True)])


class ColResTest(ColumnTest):
	"""tests for resolution of output columns from various expressions.
	"""
	def testSimpleSelect(self):
		cols = self._getColSeq("select width, height from spatial")
		self.assertEqual(cols[0][0], 'width')
		self.assertEqual(cols[1][0], 'height')
		wInfo = cols[0][1]
		self.assertEqual(wInfo.unit, "m")
		self.assertEqual(wInfo.ucd, "phys.dim")
		self.assert_(wInfo.userData[0] is spatialFields[1])

	def testIgnoreCase(self):
		cols = self._getColSeq("select Width, hEiGHT from spatial")
		self._assertColumns(cols, [
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),])

	def testStarSelect(self):
		cols = self._getColSeq("select * from spatial")
		self._assertColumns(cols, [
			("real", "m", "phys.distance", False),
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),
			("real", "deg", "pos.eq.ra", False),
			("real", "rad", "pos.eq.ra", False), ])

	def testStarSelectJoined(self):
		cols = self._getColSeq("select * from spatial, misc")
		self._assertColumns(cols, [
			("real", "m", "phys.distance", False),
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),
			("real", "deg", "pos.eq.ra", False),
			("real", "rad", "pos.eq.ra", False),
			("real", "kg", "phys.mass", False),
			("real", "mag", "phot.mag", False),
			("real", "km/s", "phys.veloc", False)])

	def testDimlessSelect(self):
		cols = self._getColSeq("select 3+4 from spatial")
		self.assertEqual(cols[0][1].type, "smallint")
		self.assertEqual(cols[0][1].unit, "")
		self.assertEqual(cols[0][1].ucd, "")

	def testSimpleScalarExpression(self):
		cols = self._getColSeq("select 2+width, 2*height, height*2"
			" from spatial")
		self._assertColumns(cols, [
			("real", "", "", True),
			("real", "km", "phys.dim", True),
			("real", "km", "phys.dim", True),])
		self.assert_(cols[1][1].userData[0] is spatialFields[2])

	def testFieldOperandExpression(self):
		cols = self._getColSeq("select width*height, width/speed, "
			"3*mag*height, mag+height, height+height from spatial, misc")
		self._assertColumns(cols, [
			("real", "m*km", "", True),
			("real", "m/(km/s)", "", True),
			("real", "mag*km", "", True),
			("real", "", "", True),
			("real", "km", "phys.dim", True)])

	def testMiscOperands(self):
		cols = self._getColSeq("select -3*mag from misc")
		self._assertColumns(cols, [
			("real", "mag", "phot.mag", True)])

	def testSetFunctions(self):
		cols = self._getColSeq("select AVG(mag), mAx(mag), max(2*mag),"
			" Min(Mag), sum(mag), count(mag), avg(3), count(*) from misc")
		self._assertColumns(cols, [
			("double precision", "mag", "stat.mean;phot.mag", False),
			("real", "mag", "stat.max;phot.mag", False),
			("real", "mag", "stat.max;phot.mag", True),
			("real", "mag", "stat.min;phot.mag", False),
			("real", "mag", "phot.mag", False),
			("integer", "", "meta.number;phot.mag", False),
			("double precision", "", "stat.mean", False),
			("integer", "", "meta.number", False)])

	def testNumericFunctions(self):
		cols = self._getColSeq("select acos(ra2), degrees(ra2), RadianS(ra1),"
			" PI(), ABS(width), Ceiling(Width), Truncate(height*2)"
			" from spatial")
		self._assertColumns(cols, [
			("double precision", "rad", "", True),
			("double precision", "deg", "pos.eq.ra", True),
			("double precision", "rad", "pos.eq.ra", True),
			("double precision", "", "", True),
			("double precision", "m", "phys.dim", True),
			("double precision", "m", "phys.dim", True),
			("double precision", "km", "phys.dim", True)])

	def testAggFunctions(self):
		cols = self._getColSeq("select max(ra1), min(ra1) from spatial")
		self._assertColumns(cols, [
			("real", "deg", "stat.max;pos.eq.ra", False),
			("real", "deg", "stat.min;pos.eq.ra", False)])

	def testPoint(self):
		cols = self._getColSeq("select point('ICRS', ra1, ra2) from spatial")
		self._assertColumns(cols, [
			("spoint", 'deg,rad', '', False)])
		self.assert_(cols[0][1].userData[0] is spatialFields[3])

	def testDistance(self):
		cols = self._getColSeq("select distance(point('galactic', 2, 3),"
			" point('ICRS', ra1, ra2)) from spatial")
		self._assertColumns(cols, [
			("double precision", 'deg', 'pos.angDistance', False)])

	def testCentroid(self):
		cols = self._getColSeq("select centroid(circle('galactic', ra1, ra2, 0.5))"
			" from spatial")
		self._assertColumns(cols, [
			("spoint", '', '', False)])

	def testParenExprs(self):
		cols = self._getColSeq("select (width+width)*height from spatial")
		self._assertColumns(cols, [
			("real", "m*km", "", True)])

	def testSubquery(self):
		cols = self._getColSeq("select q.p from (select ra2 as p from"
			" spatial) as q")
		self._assertColumns(cols, [
			("real", 'rad', 'pos.eq.ra', False)])

	def testJoin(self):
		cols = self._getColSeq("select dist, speed, 2*mass*height"
			" from spatial join misc on (mass>height)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km/s', 'phys.veloc', False),
			("real", 'kg*km', '', True),])

	def testWhereResolutionPlain(self):
		cols = self._getColSeq("select dist from spatial where exists"
			" (select * from misc where dist=misc.mass)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False)])

	def testWhereResolutionWithAlias(self):
		cols = self._getColSeq("select dist from spatial as q where exists"
			" (select * from misc where q.dist=misc.mass)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False)])

	def testErrorReporting(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			"select gnurks from spatial")

	def testExpressionWithUnicode(self):
		cols = self._getColSeq("select crazy.name||geo.pt from crazy, geo")
		self._assertColumns(cols, [
			("unicode", '', '', True)])

	def testIdenticalNames(self):
		cols = self._getColSeq("SELECT u.ra1 FROM spatial AS mine"
  		" LEFT OUTER JOIN spatial2 as u"
  		" ON (1=CONTAINS(POINT('', mine.ra1, mine.ra2),"
  		"   CIRCLE('', u.ra1, u.dec, 1)))")
		self._assertColumns(cols, [
			("real", 'deg', 'pos.eq.ra;meta.main', False)])

	def testAliasedColumn(self):
		cols = self._getColSeq("SELECT foo, ra1 FROM ("
			"SELECT ra1 as foO, ra1 FROM spatial) as q")
		self._assertColumns(cols, [
			("real", 'deg', 'pos.eq.ra', False),
			("real", 'deg', 'pos.eq.ra', False)])

	def testAliasedGrouping(self):
		cols = self._getColSeq("SELECT count(*) as ct, round(ra1/10) as band"
			" FROM spatial GROUP BY band")
		self._assertColumns(cols, [
			('integer', '', 'meta.number', False), 
			('double precision', 'deg', 'pos.eq.ra', True)])

	def testStringFunction(self):
		cols = self._getColSeq("SELECT LOWER('foo'), LOWER(version)"
			" from crazy")
		self._assertColumns(cols, [
			('text', '', '', False), 
			('text', '', '', False)])


class ExprColTest(ColumnTest):
	def testCharConcat(self):
		cols = self._getColSeq("select flag||'ab' as cat from crazy")
		self._assertColumns(cols, [
			("text", '', "", True),])

	def testTextConcat(self):
		cols = self._getColSeq("select version||'ab' as cat from crazy")
		self._assertColumns(cols, [
			("text", '', "", True),])

	def testUnicodeConcat(self):
		cols = self._getColSeq("select name||'ab' as cat from crazy")
		self._assertColumns(cols, [
			("unicode", '', "", True),])

	def testUCDColSimple(self):
		cols = self._getColSeq("select UCDCOL('phys.mass') from misc")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False)])

	def testUCDColPattern(self):
		cols = self._getColSeq("select UCDCOL('phys.mass'), UCDCOL('phys.dist*')"
			" from misc join spatial on (dist=mass)")
		self._assertColumns(cols, [
			("real", "kg", "phys.mass", False),
			("real", "m", "phys.distance", False)
			])

	def testUCDColFails(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"column matching ucd 'phys.mass' could not be located in from clause",
			self._getColSeq,
			("select UCDCOL('phys.mass') from spatial",))
	
	def testInUnit(self):
		cols = self._getColSeq("select IN_UNIT(height, 'm') from spatial")
		self._assertColumns(cols, [
			("real", "m", "phys.dim", False),])
	
	def testInUnitFailsIncompatibleUnit(self):
		self.assertRaisesWithMsg(adql.Error,
			"in_unit error: km and rad do not have the same SI base",
			self._getColSeq,
			("select IN_UNIT(height, 'rad') from spatial",))


class DelimitedColResTest(ColumnTest):
	"""tests for column resolution with delimited identifiers.
	"""
	def testCaseSensitive(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			'select "Inch""ing" from quoted')

	def testMixedCase(self):
		cols = self._getColSeq('select "plAin" from quoted')
		self.assertEqual(cols[0][0], utils.QuotedName("plAin"))

	def testNoFoldToRegular(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			'select plain from quoted')

	def testDelimitedMatchesRegular(self):
		cols = self._getColSeq('select "mass" from misc')
		self.assertEqual(cols[0][0], "mass")

	def testConstantSelectWithAs(self):
		cols = self._getColSeq('select 1+0.1 as "x" from spatial')
		self.assertEqual(cols[0][0], "x")

	def testRegularMatchesDelmitied(self):
		cols = self._getColSeq('select alllower from quoted')
		self.assertEqual(cols[0][0], "alllower")

	def testSimpleStar(self):
		cols = self._getColSeq("select * from quoted")
		self._assertColumns(cols, [
			("real", 'bg', "mess", False),
			("real", 'fin', "imperial.mess", False),
			("real", 'pc', "boring.stuff", False),
			("real", 'km', "simple.case", False),])
	
	def testSimpleJoin(self):
		cols = self._getColSeq('select "inch""ing", "mass" from misc join'
			' quoted on ("left-right"=speed)')
		self._assertColumns(cols, [
			("real", 'fin', "imperial.mess", False),
			("real", 'kg', 'phys.mass', False)])

	def testPlainAndSubselect(self):
		cols = self._getColSeq('select "inch""ing", alllower from ('
			'select TOP 5 * from quoted where alllower<"inch""ing") as q')
		self._assertColumns(cols, [
			("real", 'fin', "imperial.mess", False),
			("real", 'km', "simple.case", False),])
	
	def testQuotedExpressions(self):
		cols = self._getColSeq('select 4*alllower*"inch""ing" from quoted')
		self._assertColumns(cols, [
			("real", 'km*fin', None, True)])

	def testReferencingRegulars(self):
		cols = self._getColSeq('select "ra1" from spatial')
		self._assertColumns(cols, [
			("real", 'deg', "pos.eq.ra", False)])


class JoinColResTest(ColumnTest):
	def testJoin(self):
		cols = self._getColSeq("select dist, speed, 2*mass*height"
			" from spatial join misc on (mass>height)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km/s', 'phys.veloc', False),
			("real", 'kg*km', '', True),])

	def testJoinStar(self):
		cols = self._getColSeq("select * from spatial as q join misc as p on"
			" (1=contains(point('ICRS', q.dist, q.width), circle('ICRS',"
			" p.mass, p.mag, 0.02)))")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'm', 'phys.dim', False),
			("real", 'km', 'phys.dim', False),
			("real", 'deg', 'pos.eq.ra', False),
			("real", 'rad', 'pos.eq.ra', False),
			("real", 'kg', 'phys.mass', False),
			("real", 'mag', 'phot.mag', False),
			("real", 'km/s', 'phys.veloc', False),
			])

	def testSubqueryJoin(self):
		cols = self._getColSeq("SELECT * FROM ("
  		"SELECT ALL q.mass, spatial.ra1 FROM ("
    	"  SELECT TOP 100 mass, mag FROM misc"
      "    WHERE speed BETWEEN 0 AND 1) AS q JOIN"
    	"  spatial ON (mass=width)) AS f")
		self._assertColumns(cols, [
			("real", 'kg', 'phys.mass', False),
			("real", 'deg', 'pos.eq.ra', False)])

	def testAutoJoin(self):
		cols = self._getColSeq("SELECT * FROM misc JOIN"
			" (SELECT TOP 3 * FROM crazy) AS q ON (mag=q.ct)")
		physMass = cols[0]
		self.assertEqual(physMass[0], "mass")
		self.assertEqual(physMass[1].ucd, "phys.mass")
		crazyMass = cols[6]
		self.assertEqual(crazyMass[0], "mass")
		self.assertEqual(crazyMass[1].ucd, "event;using.incense")

	def testSelfUsingJoin(self):
		cols = self._getColSeq("SELECT * FROM "
    	" misc JOIN misc AS u USING (mass)")
		self._assertColumns(cols, [
			("real", 'kg', 'phys.mass', False),
			("real", 'mag', 'phot.mag', False),
			("real", 'km/s', 'phys.veloc', False),
			("real", 'mag', 'phot.mag', False),
			("real", 'km/s', 'phys.veloc', False) ])

	def testExReferenceBad(self):
		self.assertRaises(adql.TableNotFound, self._getColSeq,
			"select foo.dist from spatial join misc on (mass>height)")

	def testExReference(self):
		cols = self._getColSeq("select a.dist, b.dist"
			" from spatial as a join spatial as b on (a.dist>b.dist)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'm', 'phys.distance', False)])

	def testExReferenceMixed(self):
		cols = self._getColSeq("select spatial.dist, b.speed"
			" from spatial as a join misc as b on (a.dist>b.speed)")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km/s', 'phys.veloc', False)])
	
	def testNaturalJoin(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2 WHERE dist<2")
		self._assertColumns(cols, [
			("real", "m", "phys.distance", False),
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),
			("real", "deg", "pos.eq.ra", False),
			("real", "rad", "pos.eq.ra", False),
			("real", "deg", "pos.eq.dec;meta.main", False)])

	def testUsingJoin1(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2 USING (ra1)")
		self._assertColumns(cols, [
			("real", "m", "phys.distance", False),
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),
			("real", "deg", "pos.eq.ra", False),
			("real", "rad", "pos.eq.ra", False),
			("real", "deg", "pos.eq.dec;meta.main", False),
			("real", "m", "phys.distance", False)])

	def testUsingJoin2(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2 USING (ra1, dist)")
		self._assertColumns(cols, [
			("real", "m", "phys.distance", False),
			("real", "m", "phys.dim", False),
			("real", "km", "phys.dim", False),
			("real", "deg", "pos.eq.ra", False),
			("real", "rad", "pos.eq.ra", False),
			("real", "deg", "pos.eq.dec;meta.main", False)])

	def testUsingJoin3(self):
		cols = self._getColSeq("SELECT ra1, dec, mass FROM"
			" spatial JOIN spatial2 USING (ra1, dist) JOIN misc ON (dist=mass)")
		self._assertColumns(cols, [
			("real", "deg", "pos.eq.ra", False),
			("real", "deg", "pos.eq.dec;meta.main", False),
			("real", "kg", "phys.mass", False),])

	def testUsingJoin4(self):
		cols = self._getColSeq("SELECT ra1, dec, mass FROM"
			" (SELECT * FROM spatial) as q JOIN spatial2"
			" USING (ra1, dist) JOIN misc ON (dist=mass)")
		self._assertColumns(cols, [
			("real", "deg", "pos.eq.ra", False),
			("real", "deg", "pos.eq.dec;meta.main", False),
			("real", "kg", "phys.mass", False),])
	
	def testCommaAll(self):
		cols = self._getColSeq("SELECT * from spatial, spatial, misc")
		self.assertEqual([c[1].userData[0].name for c in cols], [
			'dist', 'width', 'height', 'ra1', 'ra2', 'dist', 'width', 
			'height', 'ra1', 'ra2', 'mass', 'mag', 'speed'])

	def testHaving1(self):
		cols = self._getColSeq(
			"SELECT ct FROM crazy "
			"JOIN ("
			"  SELECT height FROM spatial"
			"  JOIN spatial2 ON (ra2=dist)"
			"  GROUP BY height"
			"  HAVING (height>avg(dist))) AS q "
			"ON (wot=height)")
		self._assertColumns(cols, [
			('integer', '', '', False)])


class SetColResTest(ColumnTest):
	def testSimple(self):
		cols = self._getColSeq("select dist, height from spatial"
			" union select dist, height from spatial")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km', 'phys.dim', False)])

	def testLengthFailure(self):
		self.assertRaisesWithMsg(adql.IncompatibleTables,
			"Operands in set operation have differing result tuple lengths.",
			self._getColSeq,
			("select dist, width, height from spatial"
			" union select dist, height from spatial",))

	def testName(self):
		self.assertRaisesWithMsg(adql.IncompatibleTables,
			"Operands if set operation have differing names.  First differing name: width vs. dist",
			self._getColSeq,
			("select width, height from spatial"
			" union select dist, height from spatial",))

	def testAliasing(self):
		cols = self._getColSeq("select dist, height from spatial"
			" union select dist, ra1 as height from spatial2"
			" intersect select mass as dist, mag as height from misc"
			' except select "left-right" as dist, "plAin" as height from quoted')
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km', 'phys.dim', False)])

	def testNested(self):
		cols = self._getColSeq("select dist, height from spatial"
			" union select ra1 as dist, dec as height from ("
			"   select * from spatial2"
			"   except select mag as ra1, mass as dec, speed as dist from misc) as q"
			"  where dist>2")
		self._assertColumns(cols, [
			("real", 'm', 'phys.distance', False),
			("real", 'km', 'phys.dim', False)])


class UploadColResTest(ColumnTest):
	def setUp(self):
		ColumnTest.setUp(self)
		self.fieldInfoGetter = adqlglue.getFieldInfoGetter(tdsForUploads=[
			testhelpers.getTestTable("adql")])
	
	def testNormalResolution(self):
		cols = self._getColSeq("select alpha, rv from TAP_UPLOAD.adql")
		self._assertColumns(cols, [
			("real", 'deg', 'pos.eq.ra;meta.main', False),
			("double precision", 'km/s', 'phys.veloc;pos.heliocentric', False),])

	def testFailedResolutionCol(self):
		self.assertRaises(base.NotFoundError, self._getColSeq,
			'select alp, rv from TAP_UPLOAD.adql')
	
	def testFailedResolutionTable(self):
		self.assertRaises(base.NotFoundError, self._getColSeq,
			'select alpha, rv from TAP_UPLOAD.junk')


class STCTest(ColumnTest):
	"""tests for working STC inference in ADQL expressions.
	"""
	def testSimple(self):
		cs = self._getColSeq("select ra1, ra2 from spatial")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, 'ICRS')
		self.assertEqual(cs[1][1].stc.astroSystem.spaceFrame.refFrame, 'FK4')

	def testBroken(self):
		cs = self._getColSeq("select ra1+ra2 from spatial")
		self.failUnless(hasattr(cs[0][1].stc, "broken"))

	def testOKPoint(self):
		cs, ctx = self._getColSeqAndCtx(
			"select point('ICRS', ra1, 2) from spatial")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, 'ICRS')
		self.assertEqual(ctx.errors, [])

	def testEmptyCoosysInherits(self):
		cs, ctx = self._getColSeqAndCtx(
			"select point('', ra2, 2) from spatial")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, 'FK4')
		self.assertEqual(ctx.errors, [])

	def testEmptyCoosysBecomesNone(self):
		cs, ctx = self._getColSeqAndCtx(
			"select point('', mag, 2) from misc")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, None)
		self.assertEqual(ctx.errors, [])

	def testNULLCoosys(self):
		cs, ctx = self._getColSeqAndCtx(
			"select point(NULL, ra1, 2) from spatial")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, 'ICRS')
		self.assertEqual(ctx.errors, [])

	def testPointBadCoo(self):
		cs, ctx = self._getColSeqAndCtx(
			"select point('ICRS', ra2, 2) from spatial")
		self.assertEqual(cs[0][1].stc.astroSystem.spaceFrame.refFrame, 'ICRS')
		self.assertEqual(ctx.errors, ['When constructing point:'
			' Argument 1 has incompatible STC'])

	def testPointFunctionsSelect(self):
		cs, ctx = self._getColSeqAndCtx(
			"select coordsys(p), coord1(p), coord2(p) from"
			"	(select point('FK5', ra1, width) as p from spatial) as q")
		self._assertColumns(cs, [
			("text", '', 'meta.ref;pos.frame', False),
			("double precision", 'deg', None, False),
			("double precision", 'm', None, False)])

	def testBadSTCSRegion(self):
		self.assertRaisesWithMsg(adql.RegionError, 
			"Invalid argument to REGION: 'Time TT'.",
			self._getColSeqAndCtx, (
				"select * from spatial where 1=intersects("
				"region('Time TT'), circle('icrs', 1, 1, 0.1))",))

	def testRegionExpressionRaises(self):
		self.assertRaisesWithMsg(adql.RegionError, 
			"Invalid argument to REGION: ''Position'||alphaName||deltaName'.",
			self._getColSeqAndCtx, (
				"select * from spatial where 1=intersects("
				"region('Position' || alphaName || deltaName),"
				" circle('icrs', 1, 1, 0.1))",))

	def testSTCSRegion(self):
		cs, ctx = self._getColSeqAndCtx(
				"select region('Circle FK4 10 10 1')"
				" from spatial")
		self.assertEqual(cs[0][1].unit, "deg")


class FunctionNodeTest(unittest.TestCase):
	"""tests for nodes.FunctionMixin and friends.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()
	
	def testPlainArgparse(self):
		t = self.grammar.parseString("select POINT('ICRS', width,height)"
			" from spatial")[0]
		p = t.selectList.selectFields[0].expr
		self.assertEqual(p.cooSys, "ICRS")
		self.assertEqual(nodes.flatten(p.x), "width")
		self.assertEqual(nodes.flatten(p.y), "height")

	def testExprArgparse(self):
		t = self.grammar.parseString("select POINT('ICRS', "
			"5*width+height*LOG(width),height)"
			" from spatial")[0]
		p = t.selectList.selectFields[0].expr
		self.assertEqual(p.cooSys, "ICRS")
		self.assertEqual(nodes.flatten(p.x), "5 * width + height * LOG(width)")
		self.assertEqual(nodes.flatten(p.y), "height")


class ComplexExpressionTest(unittest.TestCase):
	"""quite random tests for correct processing of complex-ish search expressions.
	"""
	def testOne(self):
		t = adql.getGrammar().parseString("select top 5 * from"
			" lsw.plates where dateobs between 'J2416642 ' and 'J2416643'")[0]
		self.assertEqual(t.whereClause.children[1].name, "dateobs")
		self.assertEqual(adql.flatten(t.whereClause.children[-1]), "'J2416643'")


class NameSuggestingTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		query, name = sample
		t = adql.getGrammar().parseString(query)[0]
		self.assertEqual(t.suggestAName(), name)

	samples = [
		("select * from plaintable", "plaintable"),
		('select * from "plaintable"', "_plaintable"),
		('select * from "useless & table"" name"', "_uselesstablename"),
		('select * from "3columns"', "_3columns"),
		('select * from t1 join t2', "t1_t2"),
# 5
		('select * from (select * from gnug) as booger', "booger"),
		('select * from (select * from gnug) as booger join boog', 
			"booger_boog"),]


class _FlatteningTest(testhelpers.VerboseTest):
	def _assertFlattensTo(self, rawADQL, flattenedADQL):
		self.assertEqual(adql.flatten(adql.parseToTree(rawADQL)),
			flattenedADQL)


class MiscFlatteningTest(_FlatteningTest):
	"""tests for flattening of plain ADQL trees.
	"""
	def testCircle(self):
		self._assertFlattensTo("select alphaFloat, deltaFloat from ppmx.data"
				" where contains(point('ICRS', alphaFloat, deltaFloat), "
				" circle('ICRS', 23, 24, 0.2))=1",
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" CONTAINS(POINT(alphaFloat, deltaFloat), CIRCLE(23, 24, 0.2)) = 1")

	def testFunctions(self):
		self._assertFlattensTo(
			"select round(x,2)as a, truncate(x,-2) as b from foo",
			"SELECT ROUND(x, 2) AS a, TRUNCATE(x, - 2) AS b FROM foo")

	def testJoin(self):
		self._assertFlattensTo(
			"SELECT ra1, dec, mass FROM\n"
			" (SELECT * FROM spatial) as q LEFT OUTER JOIN spatial2\n"
			" USING (ra1, dist) JOIN misc ON (dist=mass)",
			"SELECT ra1, dec, mass FROM (SELECT * FROM spatial) AS q"
			" LEFT OUTER JOIN spatial2 USING ( ra1 , dist ) JOIN misc"
			" ON ( dist = mass )")

	def testCommaJoin(self):
		self._assertFlattensTo(
			"SELECT ra1, dec, mass FROM\n spatial, spatial2, misc",
			"SELECT ra1, dec, mass FROM spatial , spatial2  , misc ")

	def testSubJoin(self):
		self._assertFlattensTo(
			"SELECT ra1, dec, mass FROM\n"
			" (spatial join spatial2 using (ra1)), misc",
			"SELECT ra1, dec, mass FROM"
			" (spatial JOIN spatial2 USING ( ra1 )) , misc ")

	def testConcat(self):
		self._assertFlattensTo(
			"select 'ivo://' ||  name || '%' as pat from crazy",
			"SELECT 'ivo://' || name || '%' AS pat FROM crazy")
	
	def testAliasExpr(self):
		self._assertFlattensTo(
			"select a+b/(8+x) as num from crazy",
			"SELECT a + b / ( 8 + x ) AS num FROM crazy")


class CommentTest(_FlatteningTest):
	def testTopComment(self):
		self._assertFlattensTo("-- opening remarks;\n"
		"-- quite a few of them, actually.\nselect * from foo",
			"SELECT * FROM foo")
	
	def testEmbeddedComments(self):
		self._assertFlattensTo("select -- comment\n"
			"bar, --comment\n"
			"quux --comment\n"
			"from -- comment\n"
			"foo --comment",
			"SELECT bar, quux FROM foo")

	def testStringJoining(self):
		self._assertFlattensTo("select * from bar where a='qua' -- cmt\n'tsch'",
			"SELECT * FROM bar WHERE a = 'quatsch'")
	
	def testLeadingWhitespaceCleanup(self):
		self._assertFlattensTo("select * from--comment\n   bar",
			"SELECT * FROM bar")
	
	def testEquivalentToWhitespace(self):
		self._assertFlattensTo("select * from--comment\nbar",
			"SELECT * FROM bar")


class Q3CMorphTest(unittest.TestCase):
	"""tests the Q3C morphing of queries.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()
	
	def testCircleIn(self):
		s, t = morphpg.morphPG(
			adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where contains(point('ICRS', alphaFloat, deltaFloat), "
				" circle('ICRS', 23, 24, 0.2))=1"))
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" q3c_join_symmetric(23, 24, alphaFloat, deltaFloat, 0.2)")
	
	def testCircleOut(self):
		s, t = morphpg.morphPG(
			adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where 0=contains(point('ICRS', alphaFloat, deltaFloat),"
				" circle('ICRS', 23, 24, 0.2))"))
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" NOT q3c_join_symmetric(23, 24, alphaFloat, deltaFloat, 0.2)")

	def testConstantsFirst(self):
		s, t = morphpg.morphPG(
			adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where 0=contains(point('ICRS', 23, 24),"
				" circle('ICRS', alphaFloat, deltaFloat, 0.2))"))
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" NOT q3c_join_symmetric(23, 24, alphaFloat, deltaFloat, 0.2)")

	def _parseAnnotating(self, query):
		return adql.parseAnnotating(query, _sampleFieldInfoGetter)[1]

	def testCircleAnnotated(self):
		s, t = morphpg.morphPG(
			self._parseAnnotating("SELECT TOP 10 * FROM spatial"
			" WHERE 1=CONTAINS(POINT('ICRS', ra1, ra2),"
			"  CIRCLE('ICRS', 10, 10, 0.5))"))
		self.assertEqual(adql.flatten(t),
			"SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2 FROM spatial WHERE q3c_join_symmetric(10, 10, ra1, ra2, 0.5) LIMIT 10")

	def testMogrifiedIntersect(self):
		s, t = morphpg.morphPG(
			self._parseAnnotating("SELECT TOP 10 * FROM spatial"
			" WHERE 1=INTERSECTS(CIRCLE('ICRS', 10, 10, 0.5),"
				"POINT('ICRS', ra1, ra2))"))
		self.assertEqual(adql.flatten(t),
			"SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2 FROM spatial WHERE q3c_join_symmetric(10, 10, ra1, ra2, 0.5) LIMIT 10")


class PQMorphTest(testhelpers.VerboseTest):
	"""tests for morphing to non-geometry ADQL syntax to postgres.
	"""
	def _testMorph(self, stIn, stOut, fieldInfoGetter=None):
		tree = adql.parseToTree(stIn)
		if fieldInfoGetter:
			ctx = adql.annotate(tree, fieldInfoGetter)
		status, t = adql.morphPG(tree)
		flattened = nodes.flatten(t)
		self.assertEqualIgnoringAliases(nodes.flatten(t), stOut)

	def testSyntax(self):
		self._testMorph("select distinct top 10 x, y from foo offset 3", 
			'SELECT DISTINCT x, y FROM foo  LIMIT 10 OFFSET 3')

	def testWhitespace(self):
		self._testMorph("select\t distinct top\n\r\n    10 x, y from foo", 
			'SELECT DISTINCT x, y FROM foo LIMIT 10')
	
	def testGroupby(self):
		self._testMorph("select count(*), inc from ("
			" select round(x) as inc from foo) as q group by inc",
			"SELECT COUNT ( * ) ASWHATEVER, inc FROM"
			" (SELECT ROUND(x) AS inc FROM foo) AS q"
			" GROUP BY inc")

	def testTwoArgRound(self):
		self._testMorph(
			"select round(x, 2) as a, truncate(x, -2) as b from foo",
			'SELECT ROUND((x)*10^(2)) / 10^(2) AS a, TRUNC((x)*'
				'10^(- 2)) / 10^(- 2) AS b FROM foo')
	
	def testExprArgs(self):
		self._testMorph(
			"select truncate(round((x*2)+y, 4)) from foo",
			'SELECT TRUNC(ROUND((( x * 2 ) + y)*10^(4)) / 10^(4)) ASWHATEVER FROM foo')

	def testPointFunctionWithFieldInfo(self):
		t = adql.parseToTree("select coordsys(q.p) from "
			"(select point('ICRS', ra1, ra2) as p from spatial) as q")
		ctx = adql.annotate(t, _sampleFieldInfoGetter)
		self.assertEqual(ctx.errors[0], 
			'When constructing point: Argument 2 has incompatible STC')
		status, t = adql.morphPG(t)
		self.assertEqualIgnoringAliases(nodes.flatten(t), 
			"SELECT 'ICRS' ASWHATEVER FROM (SELECT spoint"
			"(RADIANS(ra1), RADIANS(ra2)) AS p FROM spatial) AS q")

	def testStringReplacedNumerics(self):
		self._testMorph("select square(x+x) from foo",
			"SELECT (x + x)^2 ASWHATEVER FROM foo")

	def testNumerics(self):
		self._testMorph("select log10(x), log(x), rand(), rand(5), "
			" TRUNCATE(x), TRUNCATE(x,3) from foo", 
			'SELECT LOG(x) ASWHATEVER, LN(x) ASWHATEVER, random() ASWHATEVER,'
				' random() ASWHATEVER, TRUNC('
				'x) ASWHATEVER, TRUNC((x)*10^(3)) / 10^(3) ASWHATEVER FROM foo')

	def testHarmless(self):
		self._testMorph("select delta*2, alpha*mag, alpha+delta"
			" from something where mag<-10",
			'SELECT delta * 2 ASWHATEVER, alpha * mag ASWHATEVER, alpha + delta ASWHATEVER FROM something'
			' WHERE mag < - 10')

	def testUnaryLogic(self):
		self._testMorph("select x from something where y not in (1,2)",
			'SELECT x FROM something WHERE y NOT IN ( 1 , 2 )')

	def testOrder(self):
		self._testMorph("select top 100 * from spatial where dist>10"
			" order by dist, height", 
			'SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2 FROM spatial WHERE dist > 10 ORDER BY dist , height LIMIT 100',
			_sampleFieldInfoGetter)

	def testUploadKilled(self):
		self._testMorph("select * from TAP_UPLOAD.abc",
			"SELECT * FROM abc")

	def testAliasedUploadKilled(self):
		self._testMorph("select * from TAP_UPLOAD.abc as o",
			"SELECT * FROM abc AS o")

	def testUploadColRef(self):
		self._testMorph("select TAP_UPLOAD.abc.c from TAP_UPLOAD.abc",
			"SELECT abc.c FROM abc")
	
	def testUploadColRefInGeom(self):
		self._testMorph("select POINT('', TAP_UPLOAD.abc.b, TAP_UPLOAD.abc.c)"
			" from TAP_UPLOAD.abc",
			"SELECT spoint(RADIANS(abc.b), RADIANS(abc.c)) ASWHATEVER FROM abc")

	def testUploadColRefInGeomContains(self):
		self._testMorph("SELECT TAP_UPLOAD.user_table.ra FROM"
			" TAP_UPLOAD.user_table WHERE (1=CONTAINS(POINT('ICRS',"
			" usnob.data.raj2000, usnob.data.dej2000), CIRCLE('ICRS',"
			" TAP_UPLOAD.user_table.ra2000, a.dec2000, 0.016666666666666666)))",
			'SELECT user_table.ra FROM user_table WHERE ( q3c_join_symmetric('
			"user_table.ra2000, a.dec2000, usnob.data.raj2000,"
			" usnob.data.dej2000, 0.016666666666666666) )")

	def testSTCSSingle(self):
		self._testMorph(
			"select * from foo where 1=CONTAINS(REGION('Position ICRS 1 2'), x)",
			"SELECT * FROM foo WHERE"
			" ((spoint '(0.0174532925,0.0349065850)') @ (x))")

	def testSTCSExpr(self):
		self._testMorph(
			"select * from foo where 1=CONTAINS("
				"REGION('Union ICRS (Position 1 2 Intersection"
				" (circle  1 2 3 box 1 2 3 4 circle 30 40 2))'),"
				" REGION('circle GALACTIC 1 2 3'))",
				"SELECT * FROM foo WHERE ((spoint '(0.0174532925,0.0349065850)' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771)))) OR (((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771)))) AND ((spoly '{(-0.0087266463,0.0000000000),(-0.0087266463,0.0698131701),(0.0436332313,0.0698131701),(0.0436332313,0.0000000000)}' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771)))) AND ((scircle '< (0.5235987756, 0.6981317008), 0.0349065850 >' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771)))))")
# TODO: Have a long, close look at this

	def testSTCSNotRegion(self):
		self._testMorph(
			"select * from foo where 1=INTERSECTS(REGION('NOT (circle  1 2 3)'), x)",
			"SELECT * FROM foo WHERE NOT ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >' && (x)))")

	def testIsNotNull(self):
		self._testMorph(
			"select * from foo where x is not null",
			"SELECT * FROM foo WHERE x IS NOT NULL")

	def testIsNull(self):
		self._testMorph(
			"select * from foo where x is null",
			"SELECT * FROM foo WHERE x IS NULL")

	def testMultiJoin(self):
		self._testMorph(
			"select * from spatial natural join spatial2 join misc on (dist=speed)",
			"SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2, spatial2.ra1, spatial2.dec, spatial2.dist, misc.mass, misc.mag, misc.speed FROM spatial NATURAL JOIN spatial2  JOIN misc ON ( dist = speed )",
			_sampleFieldInfoGetter)

	def testQualifiedStar(self):
		self._testMorph(
			"select spatial.*, misc.* from spatial natural join spatial2"
				" join misc on (dist=speed)",
			"SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2, misc.mass, misc.mag, misc.speed FROM spatial NATURAL JOIN spatial2  JOIN misc ON ( dist = speed )",
			_sampleFieldInfoGetter)
	
	def testStarWithAlias(self):
		self._testMorph("select * from spatial as b",
			"SELECT b.dist, b.width, b.height, b.ra1, b.ra2 FROM spatial AS b",
			_sampleFieldInfoGetter)

	def testStarWithJoin(self):
		self._testMorph("select * from spatial join spatial2 on (width=dec)",
			"SELECT spatial.dist, spatial.width, spatial.height,"
			" spatial.ra1, spatial.ra2, spatial2.ra1, spatial2.dec,"
			" spatial2.dist FROM spatial JOIN spatial2 ON ( width = dec )",
			_sampleFieldInfoGetter)

	def testStarWithSubquery(self):
		tree = adql.parseToTree("select * from spatial join "
			" (select ra1+dec, dist-2 as foo, dec from spatial2 offset 0) as q"
			" ON ( width = dec )")
		adql.annotate(tree, _sampleFieldInfoGetter)
		status, t = adql.morphPG(tree)
		flattened = nodes.flatten(t)
		self.assertTrue(re.match(r'SELECT spatial.dist, spatial.width, spatial.height, spatial.ra1, spatial.ra2, q.([a-z]*), q.foo, q.dec FROM spatial JOIN \(SELECT ra1 \+ dec AS \1, dist - 2 AS foo, dec FROM spatial2  OFFSET 0\) AS q ON \( width = dec \)$', flattened))

	def testSetLimitIntegrated(self):
		self._testMorph("select top 3 * from x union (select top 40 a from y"
			" except select * from z)", 
			"SELECT * FROM x UNION ( SELECT a FROM y EXCEPT SELECT * FROM z ) LIMIT 40")
	
	def testDeepSetLimitProtected(self):
		self._testMorph("select * from (select TOP 30 * from x) as q union"
			" select TOP 4 * from u", 
			"SELECT * FROM (SELECT * FROM x LIMIT 30) AS q UNION SELECT * FROM u LIMIT 4")

	def testUCDCOL(self):
		# non postgres-specific, but we need the annotation
		self._testMorph("select UCDCOL('pos.eq.dec*'), UCDCOL('phys.dim')"
			" from spatial natural join spatial2",
			"SELECT dec, width FROM spatial NATURAL JOIN spatial2 ",
			_sampleFieldInfoGetter)

	def testInUnit(self):
		# non postgres-specific, but we need the annotation
		self._testMorph("select in_unit("
				"in_unit(ra1, 'deg')/in_unit(height, 'pc')+"
				"in_unit(ra2, 'deg')/in_unit(width, 'pc'), 'rad/pc') as fantasy"
				" from spatial",
			"SELECT (((ra1 * 1) / (height * 3.24075574424e-14) + (ra2 * 57.2957795131) / (width * 3.24075574424e-17)) * 0.0174532925199) AS fantasy FROM spatial",
			_sampleFieldInfoGetter)

	
class PGSMorphTest(testhelpers.VerboseTest):
	"""tests for some pgSphere morphing.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		query, morphed = sample
		tree = adql.parseToTree(query)
		#pprint(tree.asTree())
		status, t = adql.morphPG(tree)
		self.assertEqualIgnoringAliases(nodes.flatten(t), morphed)

	samples = [
		("select AREA(circle('ICRS', COORD1(p1), coord2(p1), 2)),"
				" DISTANCE(p1,p2), centroid(circle('ICRS', coord1(p1), coord2(p1),"
				" 3)) from (select point('ICRS', ra1, dec1) as p1,"
				"   point('ICRS', ra2, dec2) as p2 from foo) as q", 
			'SELECT 3282.806350011744*AREA(scircle(spoint(RADIANS(long(p1)), RADIANS(lat(p1))), RADIANS(2))) ASWHATEVER, DEGREES((p1) <-> (p2)) ASWHATEVER, @@(scircle(spoint(RADIANS(long(p1)), RADIANS(lat(p1))), RADIANS(3))) ASWHATEVER FROM (SELECT spoint(RADIANS(ra1), RADIANS(dec1)) AS p1, spoint(RADIANS(ra2), RADIANS(dec2)) AS p2 FROM foo) AS q'),
		("select coord1(p) from foo", 'SELECT long(p) ASWHATEVER FROM foo'),
		("select coord2(p) from foo", 'SELECT lat(p) ASWHATEVER FROM foo'),
		# Ahem -- the following could resolve the coordsys, but intra-query 
		# communication is through field infos; the trees here are not annotated,
		# though.  See above, testPointFunctinWithFieldInfo
		("select coordsys(q.p) from (select point('ICRS', x, y)"
			" as p from foo) as q", 
			"SELECT 'UNKNOWN' ASWHATEVER FROM (SELECT spoint(RADIANS(x), RADIANS(y)) AS p FROM foo) AS q"),
		("select alpha from foo where"
				" Intersects(circle('ICRS', alpha, delta,"
				" margin*margin), polygon('ICRS', 1, 12, 3, 4, 5, 6, 7, 8))=0",
				"SELECT alpha FROM foo WHERE NOT ((scircle(spoint(RADIANS(alpha), RADIANS(delta)), RADIANS(margin * margin))) && ((SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(1), RADIANS(12))), (1, spoint(RADIANS(3), RADIANS(4))), (2, spoint(RADIANS(5), RADIANS(6))), (3, spoint(RADIANS(7), RADIANS(8))) ORDER BY column1) as q(ind,p))))"),

# 5
		("select alpha from foo where"
				" contains(circle('ICRS', alpha, delta,"
				" margin*margin), box('ICRS', lf, up, ri, lo))=0",
			"SELECT alpha FROM foo WHERE NOT ((scircle(spoint(RADIANS(alpha), RADIANS(delta)), RADIANS(margin * margin))) @ ((SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(lf)-RADIANS(ri)/2, RADIANS(up)-RADIANS(lo)/2)), (1, spoint(RADIANS(lf)-RADIANS(ri)/2, RADIANS(up)+RADIANS(lo)/2)), (2, spoint(RADIANS(lf)+RADIANS(ri)/2, RADIANS(up)+RADIANS(lo)/2)), (3, spoint(RADIANS(lf)+RADIANS(ri)/2, RADIANS(up)-RADIANS(lo)/2)) ORDER BY column1) as q(ind,p))))"),
		("select point('ICRS', cos(a)*sin(b), cos(a)*sin(b)),"
				" circle('ICRS', raj2000, dej2000, 25-mag*mag) from foo",
			'SELECT spoint(RADIANS(COS(a) * SIN(b)), RADIANS(COS(a) * SIN(b))) ASWHATEVER, scircle(spoint(RADIANS(raj2000), RADIANS(dej2000)), RADIANS(25 - mag * mag)) ASWHATEVER FROM foo'),
		("select POiNT('ICRS', 1, 2), CIRCLE('ICRS', 2, 3, 4),"
				" bOx('ICRS', 2 ,3, 4, 5), polygon('ICRS', 2, 3, 4, 5, 6, 7)"
				" from foo",
			'SELECT spoint(RADIANS(1), RADIANS(2)) ASWHATEVER,'
			' scircle(spoint(RADIANS(2), RADIANS(3)), RADIANS(4)) ASWHATEVER,'
			' (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(2)-RADIANS(4)/2, RADIANS(3)-RADIANS(5)/2)), (1, spoint(RADIANS(2)-RADIANS(4)/2, RADIANS(3)+RADIANS(5)/2)), (2, spoint(RADIANS(2)+RADIANS(4)/2, RADIANS(3)+RADIANS(5)/2)), (3, spoint(RADIANS(2)+RADIANS(4)/2, RADIANS(3)-RADIANS(5)/2)) ORDER BY column1) as q(ind,p)) ASWHATEVER,'
			' (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(2), RADIANS(3))), (1, spoint(RADIANS(4), RADIANS(5))), (2, spoint(RADIANS(6), RADIANS(7))) ORDER BY column1) as q(ind,p)) ASWHATEVER FROM foo'),
		("select Box('ICRS',alphaFloat,deltaFloat,pmra*100,pmde*100)"
			"	from ppmx.data where pmra!=0 and pmde!=0", 
			"SELECT (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(alphaFloat)-RADIANS(pmra * 100)/2, RADIANS(deltaFloat)-RADIANS(pmde * 100)/2)), (1, spoint(RADIANS(alphaFloat)-RADIANS(pmra * 100)/2, RADIANS(deltaFloat)+RADIANS(pmde * 100)/2)), (2, spoint(RADIANS(alphaFloat)+RADIANS(pmra * 100)/2, RADIANS(deltaFloat)+RADIANS(pmde * 100)/2)), (3, spoint(RADIANS(alphaFloat)+RADIANS(pmra * 100)/2, RADIANS(deltaFloat)-RADIANS(pmde * 100)/2)) ORDER BY column1) as q(ind,p)) ASWHATEVER FROM ppmx.data WHERE pmra != 0 AND pmde != 0"),
		("select * from data where 1=contains(point('fk4', 1,2),"
			" circle('Galactic',2,3,4))",
			'SELECT * FROM data WHERE (((spoint(RADIANS(1), RADIANS(2)))-strans(1.565186,-0.004859,-1.576368)+strans(1.346356,-1.097319,0.574771)) @ (scircle(spoint(RADIANS(2), RADIANS(3)), RADIANS(4))))'),	
# 10
		("select * from data where 1=contains(point('UNKNOWN', ra,de),"
			" circle('Galactic',2,3,4))", 
			"SELECT * FROM data WHERE q3c_join_symmetric(2, 3, ra, de, 4)"),
		("select * from data where 1=intersects(coverage,"
			"circle('icrs', 10, 10, 1))",
			"SELECT * FROM data WHERE ((coverage) && (scircle(spoint(RADIANS(10), RADIANS(10)), RADIANS(1))))"),
		("select * from data where 1=intersects(\"coVerage\","
			"circle('icrs', 10, 10, 1))",
			"SELECT * FROM data WHERE ((\"coVerage\") && (scircle(spoint(RADIANS(10), RADIANS(10)), RADIANS(1))))"),
		("select contains(coverage, circle('', 10, 10, 1)) from data",
			"SELECT CONTAINS(coverage, scircle(spoint(RADIANS(10), RADIANS(10)), RADIANS(1))) ASWHATEVER FROM data"),
			]


class PGSNoMorphTest(testhelpers.VerboseTest):
	def testPolygonNoCentroid(self):
		tree = adql.parseToTree(
			"select centroid(polygon('ICRS', 12, 13, 14, 15, 15, 17)) from foo")
		self.assertRaisesWithMsg(adql.MorphError,
			"Can only compute centroids of circles and points yet."
			"  Complain to make us implement other geometries faster.",
			adql.morphPG,
			(tree,))

	def testReferencedBoxNoCentroid(self):
		tree = parseWithArtificialTable(
			"select centroid(b) from (select"
				" box('', 1, 1, 2, 2) as b from spatial) as q")
		self.assertRaisesWithMsg(adql.MorphError,
			"Can only compute centroids of circles and points yet."
			"  Complain to make us implement other geometries faster.",
			adql.morphPG,
			(tree,))


class GlueTest(testhelpers.VerboseTest):
# Tests for some aspects of adqlglue
	def testAutoNull(self):
		td = adqlglue._getTableDescForOutput(
			parseWithArtificialTable("select * from crazy"))
		self.assertEqual(td.getColumnByName("ct").values.nullLiteral, "-2147483648")

	def testSpecifiedNull(self):
		td = adqlglue._getTableDescForOutput(
			parseWithArtificialTable("select * from crazy"))
		self.assertEqual(td.getColumnByName("wot").values.nullLiteral, "-1")

	def testSpecifiedNullOverridden(self):
		td = adqlglue._getTableDescForOutput(
			parseWithArtificialTable("select 2+wot from crazy"))
		self.assertEqual(td.columns[0].values.nullLiteral, '-9223372036854775808')

	def testPureByteaNotPromoted(self):
		td = adqlglue._getTableDescForOutput(
			parseWithArtificialTable("select wotb from crazy"))
		self.assertEqual(td.columns[0].values.nullLiteral, '254')
		self.assertEqual(td.columns[0].type, 'bytea')

	def testByteaInMultiplication(self):
# This probably behaviour that doesn't work with postgres anyway. 
# Fix the whole unsignedByte mess by not linking it to bytea.
		td = adqlglue._getTableDescForOutput(
			parseWithArtificialTable("select 2*wotb from crazy"))
		self.assertEqual(td.columns[0].type, 'smallint')
		self.assertEqual(td.columns[0].values.nullLiteral, "-32768")


class QueryTest(testhelpers.VerboseTest):
	"""performs some actual queries to test the whole thing.
	"""
	resources = [("ds",  adqlTestTable), ("querier", adqlQuerier)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.tableName = self.ds.tables["adql"].tableDef.getQName()

	def _assertFieldProperties(self, dataField, expected):
		for label, value in expected:
			self.assertEqual(getattr(dataField, label, None), value, 
				"Data field %s:"
				" Expected %s for %s, found %s"%(dataField.name, repr(value), 
					label, repr(getattr(dataField, label, None))))

	def runQuery(self, query, **kwargs):
		return adqlglue.query(self.querier, query, **kwargs)

	def testPlainSelect(self):
		res = self.runQuery(
			"select alpha, delta from %s where mag<0"%
			self.tableName)
		self.assertEqual(res.tableDef.id, self.tableName.split(".")[-1])
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 2)
		self.assertEqual(res.rows[0]["alpha"], 290.125)
		raField, deField = res.tableDef.columns
		self._assertFieldProperties(raField, [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])
		self._assertFieldProperties(deField, [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec'), ("unit", 'deg'), 
			("tablehead", None)])

	def testStarSelect(self):
		res = self.runQuery("select * from %s where mag<0"%
			self.tableName)
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 5)
		fields = res.tableDef.columns
		self._assertFieldProperties(fields[0], [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])
		self._assertFieldProperties(fields[1], [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec'), ("unit", 'deg'), 
			("tablehead", None)])
		self._assertFieldProperties(fields[3], [
			("ucd", 'phys.veloc;pos.heliocentric'),
			("description", 'A sample radial velocity'), ("unit", 'km/s')])
		self._assertFieldProperties(fields[4], [
			("ucd", ''), ("description", ''), ("unit", '')])

	def testQualifiedStarSelect(self):
		res = self.runQuery("select %s.* from %s join %s as q1"
			" using (mag) where q1.mag<0"%(
			self.tableName, self.tableName, self.tableName))
		self.assertEqual(res.tableDef.id, "adql_q1")
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 5)
		fields = res.tableDef.columns
		self._assertFieldProperties(fields[0], [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])

	def testNoCase(self):
		# will just raise an Exception if things are broken.
		self.runQuery("select ALPHA, DeLtA, MaG from %s"%self.tableName)

	def testTainting(self):
		res = self.runQuery("select delta*2, alpha*mag, alpha+delta"
			" from %s where mag<-10"% self.tableName)
		f1, f2, f3 = res.tableDef.columns
		self._assertFieldProperties(f1, [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec -- *TAINTED*: the value was operated'
				' on in a way that unit and ucd may be severely wrong'),
			("unit", 'deg')])
		self._assertFieldProperties(f2, [("ucd", ''),
			("description", 'This field has traces of: A sample RA;'
				' A sample magnitude -- *TAINTED*: the value was operated'
				' on in a way that unit and ucd may be severely wrong'),
			("unit", 'deg*mag')])
		self._assertFieldProperties(f3, [("ucd", ''),
			("description", 'This field has traces of: A sample RA; A sample Dec'
				' -- *TAINTED*: the value was operated on in a way that unit and'
				' ucd may be severely wrong'),
			("unit", 'deg')])

	def testTransformation(self):
		res = self.runQuery("select mag from %s where"
			" 1=contains(point('icrs', alpha, delta),"
			"   circle('galactic', 107,-47, 1))"%self.tableName)
		self.assertEqual(list(res)[0]["mag"], 10.25)
	
	def testGeometryInSelect(self):
		res = self.runQuery(
			"select rv, point('icrs', alpha, delta) as p, mag, alpha, delta,"
			" contains(point('', alpha, delta), circle('', 3, 15, 1)) as c,"
			" contains(point('', alpha, delta), circle('', 3, 15, 2)) as c1,"
			" intersects(point('', alpha, delta), circle('', 3, 15, 2)) as i1,"
			" intersects(circle('', alpha, delta, 1.5), circle('', 3, 15, 1.5)) as i2,"
			" intersects(circle('', alpha, delta, 0.5), circle('', 3, 15, 0.5)) as i3,"
			" circle('icrs', alpha, delta, 10) as ci"
			" from %s where mag>5"%self.tableName)
		rows = list(res)

		self.assertEqual(rows[0]["p"], 
			'Position ICRS 2. 14.')
		self.assertEqual(rows[0]["rv"], -23.75)
		self.assertEqual(rows[0]["c"], 0)
		self.assertEqual(rows[0]["c1"], 1)
		self.assertEqual(rows[0]["i1"], 1)
		self.assertEqual(rows[0]["i2"], 1)
		self.assertEqual(rows[0]["i3"], 0)
		self.assertEqual(rows[0]["ci"], 
			'Circle ICRS 2. 14. 10.')
		self.assertEqual(res.tableDef.getColumnByName("p").xtype,
			"adql:POINT")
		self.assertEqual(res.tableDef.getColumnByName("ci").xtype,
			"adql:REGION")

	def testCrossmatch(self):
		res = self.runQuery(
			"select alpha, delta from %s" 
			" WHERE 1=CROSSMATCH(3, 15, alpha, delta, 2)"%self.tableName)
		self.assertEqual(list(res), [{'alpha': 2.0, 'delta': 14.0}])

	def testQuotedIdentifier(self):
		res = self.runQuery(
			'select "rv", rV from %s where delta=89'%self.tableName)
		self.assertEqual(res.rows, [{"rv": 28., "rv_": 28.}])

	def testDistanceDegrees(self):
		res = self.runQuery(
			"select DISTANCE(POINT('ICRS', 22, -3), POINT('ICRS', 183, 50)) as d"
			" from %s"%self.tableName)
		self.assertAlmostEqual(res.rows[0]["d"], 130.31777623681)

	def testWithUDF(self):
		res = self.runQuery(
			"SELECT mag FROM %s WHERE 1=CONTAINS(REGION('simbad M1'),"
			" CIRCLE('ICRS', alpha, delta, 68))"%self.tableName)
		self.assertEqual(res.rows, [{u'mag': 1.25}])

	def testApplyPM(self):
		res = self.runQuery(
			"SELECT ivo_apply_pm(alpha, delta, 0.002, -0.001, -55) as moved"
			" FROM %s where alpha between 20 and 26"%self.tableName)
		self.assertEqual(list(base.SerManager(res).getMappedValues()),
			[{'moved': 'Position UNKNOWNFrame 25.0031114477 -13.945'}])
	
	def testStringFunctions(self):
		res = self.runQuery(
			"SELECT UPPer(table_name) as tn, lower(description) as td"
				" from tap_schema.columns where column_name ='delta'")
		self.assertEqual(res.rows, [{'tn': 'TEST.ADQL', 'td': 'a sample dec'}])


class SimpleSTCSTest(testhelpers.VerboseTest):
	def setUp(self):
		self.parse = tapstc.getSimpleSTCSParser()

	def testPosParses(self):
		res = self.parse("Position 10 20 ")
		self.assertEqual(res.pgType, "spoint")
		self.assertAlmostEqual(res.x, 0.174532925199432)
		self.assertEqual(res.cooSys, "UNKNOWN")
	
	def testCircleParses(self):
		res = self.parse(" Circle ICRS 10 20 1e0")
		self.assertEqual(res.pgType, "scircle")
		self.assertEqual(res.cooSys, "ICRS")

	def testBadCircleRaises(self):
		self.assertRaisesWithMsg(stc.STCSParseError,
			'STC-S circles want three numbers.',
			self.parse,
			("Circle 2 1",))

	def testBoxParses(self):
		res = self.parse("box TOPOCENTER SPHERICAL2 -10  20 2.1 5.4")
		self.assertEqual(res.pgType, "spoly")
	
	def testPolyParses(self):
		res = self.parse("PolyGon FK4 TOPOCENTER SPHERICAL2 -10  20 2.1 5.4 1 3")
		self.assertEqual(res.pgType, "spoly")

	def testNotParses(self):
		res = self.parse("NOT  (Box ICRS 1 2 3 4)")
		self.failUnless(isinstance(res, tapstc.GeomExpr))
		self.assertEqual(len(res.operands), 1)
		self.assertAlmostEqual(res.operands[0].points[0].x, -0.00872664626)
		self.assertEqual(res.cooSys, "UNKNOWN")
	
	def testSimpleOpParses(self):
		res = self.parse("UNiON (Box ICRS 1 2 3 4 Circle 1 2 3)")
		self.failUnless(isinstance(res, tapstc.GeomExpr))
		self.assertEqual(res.operator, "UNION")
		self.assertEqual(len(res.operands), 2)
		self.assertEqual(res.operands[0].pgType, "spoly")
		self.assertEqual(res.operands[1].pgType, "scircle")
		self.assertEqual(res.cooSys, "UNKNOWN")
	
	def testComplexOpParses(self):
		res = self.parse("INtersection FK4 ("
			"UNiON BARYCENTER (Box ICRS 1 2 3 4 Circle 1 2 3)"
			" Polygon ICRS GEOCENTER 2 3 4 5 6 7"
			" Circle Fk4 spherical2 3 4 5)")
		self.assertEqual(res.operands[0].operator, "UNION")
		self.assertEqual(res.operands[1].cooSys, "ICRS")
		self.assertEqual(res.cooSys, "FK4")

	def testCartesianRaises(self):
		self.assertRaisesWithMsg(stc.STCSParseError, 
			'Only SPHERICAL2 STC-S supported here',
			self.parse,
			("Position CARTESIAN3 1 2 3",))


class IntersectsFallbackTest(testhelpers.VerboseTest):
# Does INTERSECT fall back to CONTAINS?
	def testArg1(self):
		ctx, tree = adql.parseAnnotating(
			"SELECT pt from geo where intersects(pt, circle('ICRS', 2, 2, 1))=1",
			_sampleFieldInfoGetter)
		funNode = tree.whereClause.children[1].op1
		self.assertEqual(funNode.funName, "CONTAINS")
		self.assertEqual(funNode.args[0].type, "columnReference")
		self.assertEqual(funNode.args[1].type, "circle")

	def testArg2(self):
		ctx, tree = adql.parseAnnotating(
			"SELECT pt from geo where intersects(circle('ICRS', 2, 2, 1), pt)=1",
			_sampleFieldInfoGetter)
		funNode = tree.whereClause.children[1].op1
		self.assertEqual(funNode.funName, "CONTAINS")
		self.assertEqual(funNode.args[0].type, "columnReference")
		self.assertEqual(funNode.args[1].type, "circle")

	def testExpr(self):
		ctx, tree = adql.parseAnnotating(
			"SELECT pt from geo where intersects("
			"point('ICRS', 2, 2), circle('ICRS', 2, 2, 1))=1",
			_sampleFieldInfoGetter)
		funNode = tree.whereClause.children[1].op1
		self.assertEqual(funNode.funName, "CONTAINS")
		self.assertEqual(funNode.args[0].type, "point")
	
	def testNotouch(self):
		ctx, tree = adql.parseAnnotating(
			"SELECT pt from geo where intersects("
			"box('ICRS', 2, 2, 3, 3), circle('ICRS', 2, 2, 1))=1",
			_sampleFieldInfoGetter)
		funNode = tree.whereClause.children[1].op1
		self.assertEqual(funNode.funName, "INTERSECTS")

	def testJoinCond(self):
		ctx, tree = adql.parseAnnotating(
			"SELECT * from geo as a join geo as b on (intersects("
			"circle('ICRS', coord1(b.pt), coord2(b.pt), 1), a.pt)=1)",
			_sampleFieldInfoGetter)
		funNode = tree.fromClause.tableReference.joinSpecification.children[2].op1
		self.assertEqual(funNode.funName, "CONTAINS")
		self.assertEqual(funNode.args[0].fieldInfo.type, "spoint")


if __name__=="__main__":
	testhelpers.main(STCTest)
