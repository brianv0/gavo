"""
Tests for ADQL parsing and resoning about query results.
"""

import unittest

import testhelpers

from gavo import adql
from gavo import adqltree

class Error(Exception):
	pass


class NakedParseTest(testhelpers.VerboseTest):
	"""tests for plain parsing (without tree building).
	"""
	def setUp(self):
		_, self.grammar = adql.getADQLGrammar()

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
		])


class TreeParseTest(testhelpers.VerboseTest):
	"""tests for parsing into ADQL trees.
	"""
	def setUp(self):
		self.grammar = adqltree.getADQLGrammar()
	
	def testSelectList(self):
		for q, e in [
			("select a from z", ["a"]),
			("select x.a from z", ["x.a"]),
			("select x.a, b from z", ["x.a", "b"]),
			('select "one weird name", b from z', ['"one weird name"', "b"]),
		]:
			res = self.grammar.parseString(q)[0].getSelectList()
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


def singleTest():
	suite = unittest.makeSuite(TreeParseTest, "test")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
#	unittest.main()
	singleTest()
