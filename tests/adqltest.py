"""
Tests for ADQL parsing and reasoning about query results.
"""

import os
import unittest
from pprint import pprint

import pyparsing

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
from gavo.helpers import testhelpers
from gavo.protocols import adqlglue
from gavo.stc import tapstc


class Error(Exception):
	pass



# The resources below are used elsewhere (e.g., taptest).
class _ADQLQuerier(testhelpers.TestResource):
	def make(self, deps):
		return base.SimpleQuerier(useProfile="test")
	
	def clean(self, querier):
		querier.close()
adqlQuerier = _ADQLQuerier()


class _ADQLTestTable(testhelpers.TestResource):
	resources = [("adqlQuerier", adqlQuerier)]

	def make(self, deps):
		self.rd = testhelpers.getTestRD()
		ds = rsc.makeData(self.rd.getById("ADQLTest"),
				forceSource=[
				{"alpha": 22, "delta": 23, "mag": -27, "rv": 0},],
				connection=deps["adqlQuerier"].connection).commitAll()
		return ds
	
	def clean(self, ds):
		ds.dropTables()
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
			p+"CENTROID(CENTROID(POINT('fk4', 2, 3)))=x",
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
	"""tests for parsing of valid statements containing functions.
	"""
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
	]


class AsTreeTest(testhelpers.VerboseTest):
	"""tests for asTree()
	"""
# This is an example from the docs; this is why I'd like some separate test.
	def testSimple(self):
		t = adql.parseToTree("SELECT * FROM t WHERE 1=CONTAINS("
			"CIRCLE('ICRS', 4, 4, 2), POINT('', ra, dec))").asTree()
		self.assertEqual(t[1][1][0], 'possiblyAliasedTable')
		self.assertEqual(t[3][0], 'whereClause')
		self.assertEqual(t[3][1][2][1][0], 'circle')


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
		]:
			res = list(self.grammar.parseString(q)[0].getAllNames())
			self.assertEqual(res, e, 
				"Source tables from %s: expected %s, got %s"%(q, e, res))

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
		self.assertEqual(compPred.op2.type, "valueExpression")

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
		self.assertEqual(t.fromClause.tablesReferenced[0].tableName.name,
			"Murks Tabelle")
		self.assertEqual(t.fromClause.tablesReferenced[0].tableName.schema,
			"Murks Schema")


class ParseErrorTest(testhelpers.VerboseTest):
	"""tests for sensible error messages.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		query, msgFragment = sample
		try:
			adql.getGrammar().parseString(query)
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
		("SELECT * FROM distinct", 'Reserved word not allowed here (at char 14)'),
#5
		("SELECT DISTINCT FROM y", 'Expected "*" (at char 16)'),
		("SELECT *", 'Expected "FROM" (at char 8)'),
		("SELECT * FROM y WHERE", 'Expected boolean expression (at char 21)'),
		("SELECT * FROM y WHERE y u 2", 
			'Expected comparison operator (at char 24)'),
		("SELECT * FROM y WHERE y < 2 AND", 
			'Expected boolean expression (at char 31)'),
# 10
		("SELECT * FROM y WHERE y < 2 OR", 
			'Expected boolean expression (at char 30)'),
		("SELECT * FROM y WHERE y IS 3", 'Expected "NULL" (at char 27)'),
		("SELECT * FROM y WHERE CONTAINS(a,b)", 
			'Expected comparison operator (at char 35)'),
		("SELECT * FROM y WHERE 1=CONTAINS(POINT('ICRS',x,'sy')"
			" ,CIRCLE('ICRS',x,y,z))", 
			'Expected numeric expression (at char 48)'),
		("SELECT * FROM (SELECT * FROM x)", 'Expected "AS" (at char 31)'),
# 15
		("SELECT * FROM x WHERE EXISTS z", 'Expected subquery (at char 29)'),
		("SELECT POINT(3,4) FROM z", 
			'Expected coordinate system literal (ICRS, GALACTIC,...) (at char 13)'),
		("SELECT POINT('junk', 3,4) FROM z",
			"xpected coordinate system literal (ICRS, GALACTIC,...) (at char 13)"),
	]


spatialFields = [
	rscdef.Column(None, name="dist", ucd="phys.distance", unit="m"),
	rscdef.Column(None, name="width", ucd="phys.dim", unit="m"),
	rscdef.Column(None, name="height", ucd="phys.dim", unit="km"),
	rscdef.Column(None, name="ra1", ucd="pos.eq.ra;meta.main", unit="deg"),
	rscdef.Column(None, name="ra2", ucd="pos.eq.ra", unit="rad"),]
spatial2Fields = [
	rscdef.Column(None, name="ra1", ucd="pos.eq.ra;meta.main", unit="deg"),
	rscdef.Column(None, name="dec", ucd="pos.eq.dec;meta.main", unit="deg"),
	rscdef.Column(None, name="dist", ucd="phys.distance", unit="m"),]
miscFields = [
	rscdef.Column(None, name="mass", ucd="phys.mass", unit="kg"),
	rscdef.Column(None, name="mag", ucd="phot.mag", unit="mag"),
	rscdef.Column(None, name="speed", ucd="phys.veloc", unit="km/s")]
quotedFields = [
	rscdef.Column(None, name=utils.QuotedName("left-right"), ucd="mess", 
		unit="bg"),
	rscdef.Column(None, name=utils.QuotedName('inch"ing'), ucd="imperial.mess",
		unit="fin"),
	rscdef.Column(None, name=utils.QuotedName('plain'), ucd="boring.stuff",
		unit="pc"),]

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
		for index, ((name, col), (unit, ucd, taint)) in enumerate(zip(
				resultColumns, assertProperties)):
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
			("", "", False),
			("", "", False),])

	def testConstantExprSelect(self):
		cols = self._getColSeq("select 1+0.1, 'const'||'ab' from spatial")
		self._assertColumns(cols, [
			("", "", False),
			("", "", False),])

	def testConstantSelectWithAs(self):
		cols = self._getColSeq("select 1+0.1 as x from spatial")
		self._assertColumns(cols, [
			("", "", False),])

	def testBadRefRaises(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq, 
			"select x, foo.* from spatial, misc")

	def testQualifiedStar(self):
		cols = self._getColSeq("select misc.* from spatial, misc")
		self._assertColumns(cols, [
			("kg", "phys.mass", False),
			("mag", "phot.mag", False),
			("km/s", "phys.veloc", False),])

	def testMixedQualifiedStar(self):
		cols = self._getColSeq("select misc.*, dist, round(mass/10)"
			" from spatial, misc")
		self._assertColumns(cols, [
			("kg", "phys.mass", False),
			("mag", "phot.mag", False),
			("km/s", "phys.veloc", False),
			("m", "phys.distance", False),
			("kg", "phys.mass", True),])


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
			("m", "phys.dim", False),
			("km", "phys.dim", False),])

	def testStarSelect(self):
		cols = self._getColSeq("select * from spatial")
		self._assertColumns(cols, [
			("m", "phys.distance", False),
			("m", "phys.dim", False),
			("km", "phys.dim", False),
			("deg", "pos.eq.ra;meta.main", False),
			("rad", "pos.eq.ra", False), ])
		cols = self._getColSeq("select * from spatial, misc")
		self._assertColumns(cols, [
			("m", "phys.distance", False),
			("m", "phys.dim", False),
			("km", "phys.dim", False),
			("deg", "pos.eq.ra;meta.main", False),
			("rad", "pos.eq.ra", False),
			("kg", "phys.mass", False),
			("mag", "phot.mag", False),
			("km/s", "phys.veloc", False)])

	def testDimlessSelect(self):
		cols = self._getColSeq("select 3+4 from spatial")
		self.assert_(cols[0][0], adql.dimlessFieldInfo)

	def testSimpleScalarExpression(self):
		cols = self._getColSeq("select 2+width, 2*height, height*2"
			" from spatial")
		self._assertColumns(cols, [
			("", "", True),
			("km", "phys.dim", True),
			("km", "phys.dim", True),])
		self.assert_(cols[1][1].userData[0] is spatialFields[2])

	def testFieldOperandExpression(self):
		cols = self._getColSeq("select width*height, width/speed, "
			"3*mag*height, mag+height, height+height from spatial, misc")
		self._assertColumns(cols, [
			("m*km", "", False),
			("m/(km/s)", "", False),
			("mag*km", "", True),
			("", "", True),
			("km", "phys.dim", False)])

	def testMiscOperands(self):
		cols = self._getColSeq("select -3*mag from misc")
		self._assertColumns(cols, [
			("mag", "phot.mag", True)])

	def testSetFunctions(self):
		cols = self._getColSeq("select AVG(mag), mAx(mag), max(2*mag),"
			" Min(Mag), sum(mag), count(mag), avg(3), count(*) from misc")
		self._assertColumns(cols, [
			("mag", "stat.mean;phot.mag", False),
			("mag", "stat.max;phot.mag", False),
			("mag", "stat.max;phot.mag", True),
			("mag", "stat.min;phot.mag", False),
			("mag", "phot.mag", False),
			("", "meta.number;phot.mag", False),
			("", "", False),
			("", "meta.number", False)])

	def testNumericFunctions(self):
		cols = self._getColSeq("select acos(ra2), degrees(ra2), RadianS(ra1),"
			" PI(), ABS(width), Ceiling(Width), Truncate(height*2)"
			" from spatial")
		self._assertColumns(cols, [
			("rad", "", True),
			("deg", "pos.eq.ra", True),
			("rad", "pos.eq.ra;meta.main", True),
			("", "", True),
			("m", "phys.dim", True),
			("m", "phys.dim", True),
			("km", "phys.dim", True)])

	def testAggFunctions(self):
		cols = self._getColSeq("select max(ra1), min(ra1) from spatial")
		self._assertColumns(cols, [
			("deg", "stat.max;pos.eq.ra;meta.main", False),
			("deg", "stat.min;pos.eq.ra;meta.main", False)])

	def testPoint(self):
		cols = self._getColSeq("select point('ICRS', ra1, ra2) from spatial")
		self._assertColumns(cols, [
			('deg,rad', '', False)])
		self.assert_(cols[0][1].userData[0] is spatialFields[3])

	def testParenExprs(self):
		cols = self._getColSeq("select (width+width)*height from spatial")
		self._assertColumns(cols, [
			("m*km", "", False)])

	def testSubquery(self):
		cols = self._getColSeq("select q.p from (select ra2 as p from"
			" spatial) as q")
		self._assertColumns(cols, [
			('rad', 'pos.eq.ra', False)])

	def testJoin(self):
		cols = self._getColSeq("select dist, speed, 2*mass*height"
			" from spatial join misc on (mass>height)")
		self._assertColumns(cols, [
			('m', 'phys.distance', False),
			('km/s', 'phys.veloc', False),
			('kg*km', '', True),])

	def testUnderscore(self):
		cols = self._getColSeq("select _dist"
			" from (select dist as _dist from spatial) as q")
		self._assertColumns(cols, [
			('m', 'phys.distance', False)])

	def testErrorReporting(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			"select gnurks from spatial")


class QuotedColResTest(ColumnTest):
	"""tests for column resolution with delimited identifiers.
	"""
	def testSimpleStar(self):
		cols = self._getColSeq("select * from quoted")
		self._assertColumns(cols, [
			('bg', "mess", False),
			('fin', "imperial.mess", False),
			('pc', "boring.stuff", False),])
	
	def testSimpleJoin(self):
		cols = self._getColSeq('select "inch""ing", "mass" from misc join'
			' quoted on ("left-right"=speed)')
		self._assertColumns(cols, [
			('fin', "imperial.mess", False),
			('kg', 'phys.mass', False)])

	def testPlainAndSubselect(self):
		cols = self._getColSeq('select "inch""ing", plain from ('
			'select TOP 5 * from quoted where boring<"inch""ing") as q')
		self._assertColumns(cols, [
			('fin', "imperial.mess", False),
			('pc', "boring.stuff", False),])
	
	def testQuotedExpressions(self):
		cols = self._getColSeq('select 4*plain*"inch""ing" from quoted')
		self._assertColumns(cols, [
			('pc*fin', None, True)])

	def testCaseSensitive(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			'select "Inch""ing" from quoted')


class JoinColResTest(ColumnTest):
	"""tests for column resolution with joins.
	"""
	def testJoin(self):
		cols = self._getColSeq("select dist, speed, 2*mass*height"
			" from spatial join misc on (mass>height)")
		self._assertColumns(cols, [
			('m', 'phys.distance', False),
			('km/s', 'phys.veloc', False),
			('kg*km', '', True),])

	def testJoinStar(self):
		cols = self._getColSeq("select * from spatial as q join misc as p on"
			" (1=contains(point('ICRS', q.dist, q.width), circle('ICRS',"
			" p.mass, p.mag, 0.02)))")
		self._assertColumns(cols, [
			('m', 'phys.distance', False),
			('m', 'phys.dim', False),
			('km', 'phys.dim', False),
			('deg', 'pos.eq.ra;meta.main', False),
			('rad', 'pos.eq.ra', False),
			('kg', 'phys.mass', False),
			('mag', 'phot.mag', False),
			('km/s', 'phys.veloc', False),
			])

	def testSubqueryJoin(self):
		cols = self._getColSeq("SELECT * FROM ("
  		"SELECT ALL q.mass, spatial.ra1 FROM ("
    	"  SELECT TOP 100 mass, mag FROM misc"
      "    WHERE speed BETWEEN 0 AND 1) AS q JOIN"
    	"  spatial ON (mass=width)) AS f")
		self._assertColumns(cols, [
			('kg', 'phys.mass', False),
			('deg', 'pos.eq.ra;meta.main', False)])

	def testSelfUsingJoin(self):
		cols = self._getColSeq("SELECT * FROM "
    	" misc JOIN misc AS u USING (mass)")
		self._assertColumns(cols, [
			('kg', 'phys.mass', False),
			('mag', 'phot.mag', False),
			('km/s', 'phys.veloc', False),
			('mag', 'phot.mag', False),
			('km/s', 'phys.veloc', False) ])

	def testExReferenceBad(self):
		self.assertRaises(adql.TableNotFound, self._getColSeq,
			"select foo.dist from spatial join misc on (mass>height)")

	def testExReference(self):
		cols = self._getColSeq("select a.dist, b.dist"
			" from spatial as a join spatial as b on (a.dist>b.dist)")
		self._assertColumns(cols, [
			('m', 'phys.distance', False),
			('m', 'phys.distance', False)])

	def testExReferenceMixed(self):
		cols = self._getColSeq("select spatial.dist, b.speed"
			" from spatial as a join misc as b on (a.dist>b.speed)")
		self._assertColumns(cols, [
			('m', 'phys.distance', False),
			('km/s', 'phys.veloc', False)])
	
	def testNaturalJoin(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2")
		self._assertColumns(cols, [
			("m", "phys.distance", False),
			("m", "phys.dim", False),
			("km", "phys.dim", False),
			("deg", "pos.eq.ra;meta.main", False),
			("rad", "pos.eq.ra", False),
			("deg", "pos.eq.dec;meta.main", False)])

	def testUsingJoin1(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2 USING (ra1)")
		self._assertColumns(cols, [
			("m", "phys.distance", False),
			("m", "phys.dim", False),
			("km", "phys.dim", False),
			("deg", "pos.eq.ra;meta.main", False),
			("rad", "pos.eq.ra", False),
			("deg", "pos.eq.dec;meta.main", False),
			("m", "phys.distance", False)])

	def testUsingJoin2(self):
		cols = self._getColSeq("SELECT * FROM"
			" spatial JOIN spatial2 USING (ra1, dist)")
		self._assertColumns(cols, [
			("m", "phys.distance", False),
			("m", "phys.dim", False),
			("km", "phys.dim", False),
			("deg", "pos.eq.ra;meta.main", False),
			("rad", "pos.eq.ra", False),
			("deg", "pos.eq.dec;meta.main", False)])


class UploadColResTest(ColumnTest):
	def setUp(self):
		ColumnTest.setUp(self)
		self.fieldInfoGetter = adqlglue.getFieldInfoGetter(tdsForUploads=[
			testhelpers.getTestTable("adql")])
	
	def testNormalResolution(self):
		cols = self._getColSeq("select alpha, rv from TAP_UPLOAD.adql")
		self._assertColumns(cols, [
			('deg', 'pos.eq.ra;meta.main', False),
			('km/s', 'phys.veloc;pos.heliocentric', False),])
	
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
			('', 'meta.ref;pos.frame', False),
			('deg', None, False),
			('m', None, False)])

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


class FlattenTest(unittest.TestCase):
	"""tests for flattening of plain ADQL trees.
	"""
	def _assertFlattensTo(self, rawADQL, flattenedADQL):
		self.assertEqual(adql.flatten(adql.parseToTree(rawADQL)),
			flattenedADQL)
	
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


class Q3CMorphTest(unittest.TestCase):
	"""tests the Q3C morphing of queries.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()

	def testCircleIn(self):
		t = adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where contains(point('ICRS', alphaFloat, deltaFloat), "
				" circle('ICRS', 23, 24, 0.2))=1")
		s, t = adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				"  (q3c_join(23, 24, alphaFloat, deltaFloat, 0.2))")
	
	def testCircleOut(self):
		t = adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where 0=contains(point('ICRS', alphaFloat, deltaFloat),"
				" circle('ICRS', 23, 24, 0.2))")
		s, t = adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" NOT (q3c_join(23, 24, alphaFloat, deltaFloat, 0.2))")

	def testConstantsFirst(self):
		t = adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where 0=contains(point('ICRS', 23, 24),"
				" circle('ICRS', alphaFloat, deltaFloat, 0.2))")
		s, t = adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT alphaFloat, deltaFloat FROM ppmx.data WHERE"
				" NOT (q3c_join(23, 24, alphaFloat, deltaFloat, 0.2))")

	def testCircleAnnotated(self):
		t = adql.parseToTree("SELECT TOP 10 * FROM spatial"
			" WHERE 1=CONTAINS(POINT('ICRS', ra1, ra2),"
			"  CIRCLE('ICRS', 10, 10, 0.5))")
		ctx = adql.annotate(t, _sampleFieldInfoGetter)
		s, t = adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT TOP 10 * FROM spatial WHERE  (q3c_join(10, 10, ra1, ra2, 0.5))")


class PQMorphTest(unittest.TestCase):
	"""tests for morphing to non-geometry ADQL syntax to postgres.
	"""
	def _testMorph(self, stIn, stOut):
		tree = adql.parseToTree(stIn)
		#pprint(tree.asTree())
		status, t = adql.morphPG(tree)
		self.assertEqual(nodes.flatten(t), stOut)

	def testSyntax(self):
		self._testMorph("select distinct top 10 x, y from foo", 
			'SELECT DISTINCT x, y FROM foo LIMIT 10')

	def testWhitespace(self):
		self._testMorph("select\t distinct top\n\r\n    10 x, y from foo", 
			'SELECT DISTINCT x, y FROM foo LIMIT 10')
	
	def testGroupby(self):
		self._testMorph("select count(*), inc from ("
			" select round(x) as inc from foo) as q group by inc",
			"SELECT COUNT ( * ), inc FROM"
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
			'SELECT TRUNC(ROUND((( x * 2 ) + y)*10^(4)) / 10^(4)) FROM foo')

	def testPointFunctionWithFieldInfo(self):
		t = adql.parseToTree("select coordsys(q.p) from "
			"(select point('ICRS', ra1, ra2) as p from spatial) as q")
		ctx = adql.annotate(t, _sampleFieldInfoGetter)
		self.assertEqual(ctx.errors[0], 
			'When constructing point: Argument 2 has incompatible STC')
		status, t = adql.morphPG(t)
		self.assertEqual(nodes.flatten(t), "SELECT 'ICRS' FROM (SELECT spoint"
			"(RADIANS(ra1), RADIANS(ra2)) AS p FROM spatial) AS q")

	def testNumerics(self):
		self._testMorph("select log10(x), log(x), rand(), rand(5), square(x+x),"
			" TRUNCATE(x), TRUNCATE(x,3) from foo", 
			'SELECT LOG(x), LN(x), random(),'
				' setseed(5)-setseed(5)+random(), (x + x)^2, TRUNC('
				'x), TRUNC((x)*10^(3)) / 10^(3) FROM foo')

	def testHarmless(self):
		self._testMorph("select delta*2, alpha*mag, alpha+delta"
			" from something where mag<-10",
			'SELECT delta * 2, alpha * mag, alpha + delta FROM something'
			' WHERE mag < - 10')

	def testOrder(self):
		self._testMorph("select top 100 * from ppmx.data where cmag>10"
			" order by cmag", 'SELECT * FROM ppmx.data WHERE cmag > 10'
			' ORDER BY cmag LIMIT 100')

	def testUploadKilled(self):
		self._testMorph("select * from TAP_UPLOAD.abc",
			"SELECT * FROM abc")

	def testAliasedUploadKilled(self):
		self._testMorph("select * from TAP_UPLOAD.abc as o",
			"SELECT * FROM abc AS o")

	def testSTCSSingle(self):
		self._testMorph(
			"select * from foo where 1=CONTAINS(REGION('Position ICRS 1 2'), x)",
			"SELECT * FROM foo WHERE "
			" ((spoint '(0.0174532925,0.0349065850)') @ (x))")

	def testSTCSExpr(self):
		self._testMorph(
			"select * from foo where 1=CONTAINS("
				"REGION('Union ICRS (Position 1 2 Intersection"
				" (circle  1 2 3 box 1 2 3 4 circle 30 40 2))'),"
				" REGION('circle GALACTIC 1 2 3'))",
			"SELECT * FROM foo WHERE  ((spoint '(0.0174532925,0.0349065850)' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771))) OR ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771))) AND (spoly '{(-0.0087266463,0.0000000000),(-0.0087266463,0.0698131701),(0.0436332313,0.0698131701),(0.0436332313,0.0000000000)}' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771))) AND (scircle '< (0.5235987756, 0.6981317008), 0.0349065850 >' @ ((scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >')+strans(1.346356,-1.097319,0.574771)))))")

	def testSTCSNotRegion(self):
		self._testMorph(
			"select * from foo where 1=INTERSECTS(REGION('NOT (circle  1 2 3)'), x)",
			"SELECT * FROM foo WHERE  (NOT (scircle '< (0.0174532925, 0.0349065850), 0.0523598776 >' && (x)))")


class PGSMorphTest(testhelpers.VerboseTest):
	"""tests for some pgSphere morphing.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		query, morphed = sample
		tree = adql.parseToTree(query)
		#pprint(tree.asTree())
		status, t = adql.morphPG(tree)
		self.assertEqual(nodes.flatten(t), morphed)

	samples = [
		("select AREA(circle('ICRS', COORD1(p1), coord2(p1), 2)),"
				" DISTANCE(p1,p2), centroid(box('ICRS', coord1(p1), coord2(p1),"
				" coord1(p2), coord2(p2))) from (select point('ICRS', ra1, dec1) as p1,"
				"   point('ICRS', ra2, dec2) as p2 from foo) as q", 
			'SELECT AREA(scircle(spoint(RADIANS(long(p1)), RADIANS(lat(p1))), RADIANS(2))), (p1) <-> (p2), @@((SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(long(p1))-RADIANS(long(p2))/2, RADIANS(lat(p1))-RADIANS(lat(p2))/2)), (1, spoint(RADIANS(long(p1))-RADIANS(long(p2))/2, RADIANS(lat(p1))+RADIANS(lat(p2))/2)), (2, spoint(RADIANS(long(p1))+RADIANS(long(p2))/2, RADIANS(lat(p1))+RADIANS(lat(p2))/2)), (3, spoint(RADIANS(long(p1))+RADIANS(long(p2))/2, RADIANS(lat(p1))-RADIANS(lat(p2))/2)) ORDER BY column1) as q(ind,p))) FROM (SELECT spoint(RADIANS(ra1), RADIANS(dec1)) AS p1, spoint(RADIANS(ra2), RADIANS(dec2)) AS p2 FROM foo) AS q'),
		("select coord1(p) from foo", 'SELECT long(p) FROM foo'),
		("select coord2(p) from foo", 'SELECT lat(p) FROM foo'),
		# Ahem -- the following could resolve the coordsys, but intra-query 
		# communication is through field infos; the trees here are not annotated,
		# though.  See above, testPointFunctinWithFieldInfo
		("select coordsys(q.p) from (select point('ICRS', x, y)"
			" as p from foo) as q", 
			"SELECT 'UNKNOWN' FROM (SELECT spoint(RADIANS(x), RADIANS(y)) AS p FROM foo) AS q"),
		("select alpha from foo where"
				" Intersects(circle('ICRS', alpha, delta,"
				" margin*margin), polygon('ICRS', 1, 12, 3, 4, 5, 6, 7, 8))=0",
				"SELECT alpha FROM foo WHERE NOT ((scircle(spoint(RADIANS(alpha), RADIANS(delta)), RADIANS(margin * margin))) && ((SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(1), RADIANS(12))), (1, spoint(RADIANS(3), RADIANS(4))), (2, spoint(RADIANS(5), RADIANS(6))), (3, spoint(RADIANS(7), RADIANS(8))) ORDER BY column1) as q(ind,p))))"),
		("select alpha from foo where"
				" contains(circle('ICRS', alpha, delta,"
				" margin*margin), box('ICRS', lf, up, ri, lo))=0",
			"SELECT alpha FROM foo WHERE NOT ((scircle(spoint(RADIANS(alpha), RADIANS(delta)), RADIANS(margin * margin))) @ ((SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(lf)-RADIANS(ri)/2, RADIANS(up)-RADIANS(lo)/2)), (1, spoint(RADIANS(lf)-RADIANS(ri)/2, RADIANS(up)+RADIANS(lo)/2)), (2, spoint(RADIANS(lf)+RADIANS(ri)/2, RADIANS(up)+RADIANS(lo)/2)), (3, spoint(RADIANS(lf)+RADIANS(ri)/2, RADIANS(up)-RADIANS(lo)/2)) ORDER BY column1) as q(ind,p))))"),
		("select point('ICRS', cos(a)*sin(b), cos(a)*sin(b)),"
				" circle('ICRS', raj2000, dej2000, 25-mag*mag) from foo",
			'SELECT spoint(RADIANS(COS(a) * SIN(b)), RADIANS(COS(a) * SIN(b))), scircle(spoint(RADIANS(raj2000), RADIANS(dej2000)), RADIANS(25 - mag * mag)) FROM foo'),
		("select POiNT('ICRS', 1, 2), CIRCLE('ICRS', 2, 3, 4),"
				" bOx('ICRS', 2 ,3, 4, 5), polygon('ICRS', 2, 3, 4, 5, 6, 7)"
				" from foo",
			'SELECT spoint(RADIANS(1), RADIANS(2)),'
			' scircle(spoint(RADIANS(2), RADIANS(3)), RADIANS(4)),'
			' (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(2)-RADIANS(4)/2, RADIANS(3)-RADIANS(5)/2)), (1, spoint(RADIANS(2)-RADIANS(4)/2, RADIANS(3)+RADIANS(5)/2)), (2, spoint(RADIANS(2)+RADIANS(4)/2, RADIANS(3)+RADIANS(5)/2)), (3, spoint(RADIANS(2)+RADIANS(4)/2, RADIANS(3)-RADIANS(5)/2)) ORDER BY column1) as q(ind,p)),'
			' (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(2), RADIANS(3))), (1, spoint(RADIANS(4), RADIANS(5))), (2, spoint(RADIANS(6), RADIANS(7))) ORDER BY column1) as q(ind,p)) FROM foo'),
		("select Box('ICRS',alphaFloat,deltaFloat,pmra*100,pmde*100)"
			"	from ppmx.data where pmra!=0 and pmde!=0", 
			"SELECT (SELECT spoly(q.p) FROM (VALUES (0, spoint(RADIANS(alphaFloat)-RADIANS(pmra * 100)/2, RADIANS(deltaFloat)-RADIANS(pmde * 100)/2)), (1, spoint(RADIANS(alphaFloat)-RADIANS(pmra * 100)/2, RADIANS(deltaFloat)+RADIANS(pmde * 100)/2)), (2, spoint(RADIANS(alphaFloat)+RADIANS(pmra * 100)/2, RADIANS(deltaFloat)+RADIANS(pmde * 100)/2)), (3, spoint(RADIANS(alphaFloat)+RADIANS(pmra * 100)/2, RADIANS(deltaFloat)-RADIANS(pmde * 100)/2)) ORDER BY column1) as q(ind,p)) FROM ppmx.data WHERE pmra != 0 AND pmde != 0"),
		("select * from data where 1=contains(point('fk4', 1,2),"
			" circle('Galactic',2,3,4))",
			'SELECT * FROM data WHERE  (((spoint(RADIANS(1), RADIANS(2)))-strans(1.565186,-0.004859,-1.576368)+strans(1.346356,-1.097319,0.574771)) @ (scircle(spoint(RADIANS(2), RADIANS(3)), RADIANS(4))))'),	
		("select * from data where 1=contains(point('UNKNOWN', ra,de),"
			" circle('Galactic',2,3,4))", 
			"SELECT * FROM data WHERE  ((spoint(RADIANS(ra), RADIANS(de))) @ (scircle(spoint(RADIANS(2), RADIANS(3)), RADIANS(4))))"),
			]


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
			"select alpha, delta from %s where mag<-10"%
			self.tableName, metaProfile="test")
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 2)
		self.assertEqual(res.rows[0]["alpha"], 22.0)
		raField, deField = res.tableDef.columns
		self._assertFieldProperties(raField, [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])
		self._assertFieldProperties(deField, [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec'), ("unit", 'deg'), 
			("tablehead", 'delta')])

	def testStarSelect(self):
		res = self.runQuery("select * from %s where mag<-10"%
			self.tableName, metaProfile="test")
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 4)
		fields = res.tableDef.columns
		self._assertFieldProperties(fields[0], [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])
		self._assertFieldProperties(fields[1], [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec'), ("unit", 'deg'), 
			("tablehead", 'delta')])
		self._assertFieldProperties(fields[3], [
			("ucd", 'phys.veloc;pos.heliocentric'),
			("description", 'A sample radial velocity'), ("unit", 'km/s')])
	
	def testQualifiedStarSelect(self):
		res = self.runQuery("select %s.* from %s, %s as q1 where q1.mag<-10"%(
			self.tableName, self.tableName, self.tableName))
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(len(res.rows[0]), 4)
		fields = res.tableDef.columns
		self._assertFieldProperties(fields[0], [("ucd", 'pos.eq.ra;meta.main'),
			("description", 'A sample RA'), ("unit", 'deg'), 
			("tablehead", "Raw RA")])

	def testNoCase(self):
		# will just raise an Exception if things are broken.
		self.runQuery("select ALPHA, DeLtA, MaG from %s"%self.tableName,
			metaProfile="test")

	def testTainting(self):
		res = self.runQuery("select delta*2, alpha*mag, alpha+delta"
			" from %s where mag<-10"% self.tableName, metaProfile="test")
		f1, f2, f3 = res.tableDef.columns
		self._assertFieldProperties(f1, [("ucd", 'pos.eq.dec;meta.main'),
			("description", 'A sample Dec -- *TAINTED*: the value was operated'
				' on in a way that unit and ucd may be severely wrong'),
			("unit", 'deg')])
		self._assertFieldProperties(f2, [("ucd", ''),
			("description", 'This field has traces of: A sample RA;'
				' A sample magnitude'),
			("unit", 'deg*mag')])
		self._assertFieldProperties(f3, [("ucd", ''),
			("description", 'This field has traces of: A sample RA; A sample Dec'
				' -- *TAINTED*: the value was operated on in a way that unit and'
				' ucd may be severely wrong'),
			("unit", 'deg')])

	def testGeometry(self):
		res = self.runQuery("select mag from %s where"
			" 1=intersects(circle('galactic', alpha, delta, 1),"
			"   box('galactic', alpha+1, delta+2, 3, 3))"%self.tableName)
		self.assertEqual(list(res)[0]["mag"], -27.0)
	
	def testTransformation(self):
		res = self.runQuery("select mag from %s where"
			" 1=contains(point('galactic', 133.792, -39.0994),"
			"   circle('icrs', alpha, delta, 1))"%self.tableName)
		self.assertEqual(list(res)[0]["mag"], -27.0)

	def testSTCSOutput(self):
		res = self.runQuery(
			"select rv, point('icrs', alpha, delta) as p, mag from %s"
			%self.tableName)
		self.assertEqual(list(res)[0]["p"], 
			'Position ICRS 22.0000000000 23.0000000000')
		self.assertEqual(list(res)[0]["rv"], 0)
		self.assertEqual(res.tableDef.getColumnByName("p").xtype,
			"adql:POINT")


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


if __name__=="__main__":
	testhelpers.main(ColResTest)
