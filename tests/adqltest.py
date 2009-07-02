"""
Tests for ADQL parsing and reasoning about query results.
"""

import os
import unittest

import pyparsing

from gavo import rscdesc
from gavo import protocols
from gavo import adql
from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.adql import morphpg
from gavo.adql import nodes
from gavo.adql import tree
from gavo.protocols import adqlglue


import testhelpers


class Error(Exception):
	pass


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
		except adql.ParseException:
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


class NakedParseTest(testhelpers.VerboseTest):
	"""tests for plain parsing (without tree building).
	"""
	def setUp(self):
		_, self.grammar = adql.getRawGrammar()

	def _assertParse(self, correctStatements):
		for stmt in correctStatements:
			try:
				self.grammar.parseString(stmt)
			except adql.ParseException:
				raise AssertionError("%s doesn't parse but should."%stmt)
			except RuntimeError:
				raise Error("%s causes an infinite recursion"%stmt)

	def _assertDontParse(self, badStatements):
		for stmt in badStatements:
			try:
				self.assertRaisesVerbose(adql.ParseException, 
					self.grammar.parseString, (stmt,), "Parses but shouldn't: %s"%stmt)
			except RuntimeError:
				raise Error("%s causes an infinite recursion"%stmt)

	def testPlainSelects(self):
		"""tests for non-errors on some elementary select expressions parse.
		"""
		self._assertParse([
				"SELECT x FROM y",
				"SELECT x FROM y WHERE z=0",
				"SELECT x, v FROM y WHERE z=0 AND v>2",
				"SELECT 89 FROM X",
			])

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
			p+"rectangle('fk5', 2, 3, 3, 0)=x",
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

	def testFunctions(self):
		"""tests for parsing of ADQL functions.
		"""
		p = "select x from y where "
		self._assertParse([
			p+"ABS(-3)<3",
			p+"ABS(-3.0)<3",
			p+"ABS(-3.0E4)<3",
			p+"ABS(-3.0e-4)<3",
			p+"ATAN2(-3.0e-4, 4.5)=x",
			p+"RAND(4)=x",
			p+"RAND()=x",
			p+"ROUND(23)=x",
			p+"ROUND(23,2)=x",
			p+"ROUND(PI(),2)=3.14",
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
			('select "one weird name", b from z', ['"one weird name"', "b"]),
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
			res = self.grammar.parseString(q)[0].getSourceTableNames()
			self.assertEqual(res, e, 
				"Source tables from %s: expected %s, got %s"%(q, e, res))

	def testSourceTablesJoin(self):
		for q, e in [
			("select * from z join x", ["z", "x"]),
		]:
			res = self.grammar.parseString(q)[0].getSourceTableNames()
			self.assertEqual(res, e, 
				"Source tables from %s: expected %s, got %s"%(q, e, res))

	def testAliasedColumn(self):
		q = "select foo+2 as fp2 from x"
		res = self.grammar.parseString(q)[0]
		field = res.getSelectFields()[0]
		self.assertEqual(field.name, "fp2")
	
	def testTainting(self):
		for q, (exName, exTaint) in [
			("select x from z", ("x", False)),
			("select x as u from z", ("u", False)),
			("select x+2 from z", (None, True)),
			('select x+2 as "99 Monkeys" from z', ('"99 Monkeys"', True)),
			('select x+2 as " ""cute"" Monkeys" from z', 
				('" ""cute"" Monkeys"', True)),
		]:
			res = self.grammar.parseString(q)[0].getSelectFields()[0]
			self.assertEqual(res.tainted, exTaint, "Field taintedness wrong in %s"%
				q)
			if exName:
				self.assertEqual(res.name, exName)

	def testValueExpressionColl(self):
		t = adql.parseToTree("select x from z where 5+9>'gaga'||'bla'")
		chs = t.find("comparisonPredicate").children
		self.assertEqual(len(chs), 3)
		self.assertEqual(chs[0].type, "numericValueExpression")
		self.assertEqual(chs[1], ">")
		self.assertEqual(chs[2].type, "valueExpression")


spatialFields = [
	rscdef.Column(None, name="distance", ucd="phys.distance", unit="m"),
	rscdef.Column(None, name="width", ucd="phys.dim", unit="m"),
	rscdef.Column(None, name="height", ucd="phys.dim", unit="km"),
	rscdef.Column(None, name="ra1", ucd="pos.eq.ra;meta.main", unit="deg"),
	rscdef.Column(None, name="ra2", ucd="pos.eq.ra", unit="rad"),]
miscFields = [
	rscdef.Column(None, name="mass", ucd="phys.mass", unit="kg"),
	rscdef.Column(None, name="mag", ucd="phot.mag", unit="mag"),
	rscdef.Column(None, name="speed", ucd="phys.veloc", unit="km/s")]

def _sampleFieldInfoGetter(tableName):
	if tableName=='spatial':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in spatialFields]
	elif tableName=='misc':
		return [(f.name, adqlglue.makeFieldInfo(f))
			for f in miscFields]


class NodeTest(testhelpers.VerboseTest):
	"""tests for the ADQLNode class.
	"""
	def setUp(self):
		class FooNode(nodes.ADQLNode):
			type = "foo"
		class BarNode(nodes.ADQLNode):
			type = "bar"
		self.FooNode, self.BarNode = FooNode, BarNode

	def testGetChildrenOk(self):
		fooNode = self.FooNode([])
		tree = self.FooNode([
			self.BarNode([]),
			fooNode,
			"textContent",
			self.BarNode([])])
		self.assertEqual(tree.getChildOfType("foo"), fooNode)
		self.assertEqual(tree.getChildrenOfType("foo"), [fooNode])
		self.assertEqual(len(tree.getChildrenOfType("bar")), 2)
		self.assertEqual(len(tree.getChildrenOfType("foo")), 1)
		self.assertEqual(len(tree.getChildrenOfType("baz")), 0)
		self.assertEqual(len(tree.getChildrenOfType(str)), 1)
		self.assertRaises(adql.NoChild, tree.getChildOfType, "baz")
		self.assertRaises(adql.MoreThanOneChild, tree.getChildOfType, "bar")
	
	def testGetFlattenedChildren(self):
		tree = self.FooNode([
			self.FooNode([
				self.FooNode([]),
				self.BarNode(["needle"])]),
			self.BarNode([])])
		self.assertEqual(tree.getFlattenedChildren()[0].children[0], "needle")
		tree = self.FooNode([
			self.FooNode([
				self.FooNode([]),
				self.BarNode(["needle"])]),
			self.BarNode([
				self.FooNode(["scissors"]),
				self.BarNode([
					self.FooNode(["thread"])])])])
		res = tree.getFlattenedChildren()
		self.assertEqual(res[0].type, "bar")
		self.assertEqual(res[1].children[0], "scissors")
		self.assertEqual(res[2].children[0], "thread")
		tree = self.FooNode([
			"direct",
			self.BarNode([
				self.FooNode(["indirect"])])])
		res = tree.getFlattenedChildren()
		self.assertEqual(res[0], "direct")
		self.assertEqual(res[1].type, "foo")


class ColumnTest(testhelpers.VerboseTest):
	def setUp(self):
		self.fieldInfoGetter = _sampleFieldInfoGetter
		self.grammar = adql.getGrammar()

	def _getColSeq(self, query):
		t = self.grammar.parseString(query)[0]
		adql.addFieldInfos(t, self.fieldInfoGetter)
		return t.fieldInfos.seq

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
			("", "", True),])

	def testConstantSelectWithAs(self):
		cols = self._getColSeq("select 1+0.1 as x from spatial")
		self._assertColumns(cols, [
			("", "", False),])

		
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
			("rad", "", False),
			("deg", "pos.eq.ra", False),
			("rad", "pos.eq.ra;meta.main", False),
			("", "", False),
			("m", "phys.dim", False),
			("m", "phys.dim", False),
			("km", "phys.dim", True)])

	def testGeometricFunctions(self):
		cols = self._getColSeq("select point('ICRS', ra1, ra2) from spatial")
		self._assertColumns(cols, [
			('', '', False)])
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

	def testErrorReporting(self):
		self.assertRaises(adql.ColumnNotFound, self._getColSeq,
			"select gnurks from spatial")


class FunctionNodeTest(unittest.TestCase):
	"""tests for nodes.FunctionMixin and friends.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()
	
	def testPlainArgparse(self):
		t = self.grammar.parseString("select POINT('ICRS', width,height)"
			" from spatial")[0]
		p = t.find("point")
		self.assertEqual(p.cooSys, "ICRS")
		self.assertEqual(p.x, "width")
		self.assertEqual(p.y, "height")

	def testExprArgparse(self):
		t = self.grammar.parseString("select POINT('ICRS', "
			"5*width+height*LOG(width),height)"
			" from spatial")[0]
		p = t.find("point")
		self.assertEqual(p.cooSys, "ICRS")
		self.assertEqual(p.x, "5 * width + height * LOG ( width )")
		self.assertEqual(p.y, "height")


class ComplexExpressionTest(unittest.TestCase):
	"""quite random tests for correct processing of complex-ish search expressions.
	"""
	def testOne(self):
		t = adql.getGrammar().parseString("select top 5 * from"
			" lsw.plates where dateobs between 'J2416642 ' and 'J2416643'")[0]
		self.assertEqual(t.find("columnReference").children[0], "dateobs")
		self.assertEqual(adql.flatten(t.whereClause.children[-1]), "'J2416643'")


class Q3CMorphTest(unittest.TestCase):
	"""tests the Q3C morphing of queries.
	"""
	def setUp(self):
		self.grammar = adql.getGrammar()

	def testCircle(self):
		t = adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where contains(point('ICRS', alphaFloat, deltaFloat), "
				" circle('ICRS', 23, 24, 0.2))=1")
		adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT alphafloat , deltafloat FROM ppmx . data WHERE"
				"  q3c_join(23, 24, alphafloat, deltafloat, 0.2)")
		t = adql.parseToTree("select alphaFloat, deltaFloat from ppmx.data"
			" where 1=contains(point('ICRS', alphaFloat, deltaFloat),"
				" circle('ICRS', 23, 24, 0.2))")
		adql.insertQ3Calls(t)
		self.assertEqual(adql.flatten(t),
			"SELECT alphafloat , deltafloat FROM ppmx . data WHERE"
				"  q3c_join(23, 24, alphafloat, deltafloat, 0.2)")


class PQMorphTest(unittest.TestCase):
	"""tests for morphing to psql geometry types and operators.
	"""
	def _testMorph(self, stIn, stOut):
		t = adql.morphPG(adql.parseToTree(stIn))
		self.assertEqual(nodes.flatten(t), stOut)

	def testSyntax(self):
		self._testMorph("select distinct top 10 x, y from foo", 
			'SELECT DISTINCT x , y FROM foo LIMIT 10')

	def testSimpleTypes(self):
		self._testMorph("select POiNT('ICRS', 1, 2), CIRCLE('ICRS', 2, 3, 4),"
				" REctAngle('ICRS', 2 ,3, 4, 5), polygon('ICRS', 2, 3, 4, 5, 6, 7)"
				" from foo",
			"SELECT POINT(1, 2) , CIRCLE(POINT(2, 3), 4) , POLYGON("
				"BOX(2, 3, 4, 5)) , '2, 3, 4, 5, 6, 7'"
				"::polygon FROM foo")
	
	def testTypesWithExpressions(self):
		self._testMorph("select point('ICRS', cos(a)*sin(b), cos(a)*sin(b)),"
				" circle('ICRS', raj2000, dej2000, 25-mag*mag) from foo",
			'SELECT POINT(cos ( a ) * sin ( b ), cos ( a ) * sin ( b )) , CIRCLE('
				'POINT(raj2000, dej2000), 25 - mag * mag) FROM foo')

	def testContains(self):
		self._testMorph("select alpha from foo where"
				" contains(circle('ICRS', alpha, delta,"
				" margin*margin), rectangle('ICRS', lf, up, ri, lo))=0",
			'SELECT alpha FROM foo WHERE NOT (CIRCLE(POINT(alpha, delta),'
				' margin * margin)) ~ (POLYGON(BOX(lf, up, ri, lo)))')

	def testIntersects(self):
		self._testMorph("select alpha from foo where"
				" Intersects(circle('ICRS', alpha, delta,"
				" margin*margin), polygon('ICRS', 1, 12, 3, 4, 5, 6, 7, 8))=0",
			"SELECT alpha FROM foo WHERE NOT (CIRCLE(POINT(alpha, delta"
				"), margin * margin)) ?# ('1, 12, 3, 4, 5, 6, 7, 8'::polygon)")

	def testPointFunction(self):
		self._testMorph("select coord1(p) from foo", 'SELECT (p)[0] FROM foo')
		self._testMorph("select coord2(p) from foo", 'SELECT (p)[1] FROM foo')

		# Ahem -- the following could resolve the coordsys, but intra-query 
		# communication is through field infos, which we don't have here.
		self._testMorph("select coordsys(q.p) from (select point('ICRS', x, y)"
			" as p from foo) as q", 
			"SELECT 'unknown' FROM (SELECT POINT(x, y) AS p FROM foo) AS q")

	def testPointFunctionWithFieldInfo(self):
		t = adql.parseToTree("select coordsys(q.p) from "
			"(select point('ICRS', ra1, ra2) as p from spatial) as q")
		adql.addFieldInfos(t, _sampleFieldInfoGetter)
		t = adql.morphPG(t)
		self.assertEqual(nodes.flatten(t), "SELECT 'ICRS' FROM (SELECT POINT"
			"(ra1, ra2) AS p FROM spatial) AS q")

	def testBoringGeometryFunctions(self):
		self._testMorph("select AREA(circle('ICRS', COORD1(p1), coord2(p1), 2)),"
				" DISTANCE(p1,p2), centroid(rectangle('ICRS', coord1(p1), coord2(p1),"
				" coord1(p2), coord2(p2))) from (select point('ICRS', ra1, dec1) as p1,"
				"   point('ICRS', ra2, dec2) as p2 from foo) as q", 
			'SELECT AREA ( CIRCLE(POINT((p1)[0], (p1)[1]), 2) ) , celDistPP('
				'p1, p2) , center(POLYGON(BOX((p1)[0], (p1)[1], (p2)[0], (p2)'
				'[1]))) FROM (SELECT POINT(ra1, dec1) AS p1 , POINT(ra2, dec2'
				') AS p2 FROM foo) AS q')
		self.assertRaises(adql.RegionError, self._testMorph,
			"select REGION('mystery') from foo", "")

	def testNumerics(self):
		self._testMorph("select log10(x), log(x), rand(), rand(5), square(x+x),"
			" TRUNCATE(x), TRUNCATE(x,3) from foo", 
			'SELECT LOG ( x ) , LN ( x ) , random() ,'
				' setseed(5)-setseed(5)+random() , (x + x)^2 , TRUNC ('
				' x ) , TRUNC ( x , 3 ) FROM foo')

	def testHarmless(self):
		self._testMorph("select delta*2, alpha*mag, alpha+delta"
			" from something where mag<-10",
			'SELECT delta * 2 , alpha * mag , alpha + delta FROM something'
			' WHERE mag < - 10')


class QueryTest(unittest.TestCase):
	"""performs some actual queries to test the whole thing.
	"""
	def setUp(self):
		base.setDBProfile("test")
		self.rd = testhelpers.getTestRD()
		self.ds = rsc.makeData(self.rd.getById("ADQLTest"),
				forceSource=[
				{"alpha": 22, "delta": 23, "mag": -27, "rv": 0},]).commitAll()
		self.tableName = self.ds.tables["adql"].tableDef.getQName()

	def tearDown(self):
		self.ds.dropTables()
		self.ds.commitAll().closeAll()

	def _assertFieldProperties(self, dataField, expected):
		for label, value in expected:
			self.assertEqual(getattr(dataField, label, None), value, "Data field %s:"
				" Expected %s for %s, found %s"%(dataField.name, repr(value), 
					label, repr(getattr(dataField, label, None))))

	def testPlainSelect(self):
		res = adqlglue.query("select alpha, delta from %s where mag<-10"%
			self.tableName, queryProfile="test", metaProfile="test")
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
		res = adqlglue.query("select * from %s where mag<-10"%
			self.tableName, metaProfile="test", queryProfile="test")
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

	def testNoCase(self):
		# will just raise an Exception if things are broken.
		adqlglue.query("select ALPHA, DeLtA, MaG from %s"%self.tableName,
			metaProfile="test", queryProfile="test")

	def testTainting(self):
		res = adqlglue.query("select delta*2, alpha*mag, alpha+delta"
			" from %s where mag<-10"% self.tableName, metaProfile="test",
			queryProfile="test")
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


if __name__=="__main__":
	testhelpers.main(QueryTest)
