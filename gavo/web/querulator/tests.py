import unittest

import pyparsing

import sqlparse
from gavo.web import querulator


class TestSqlparser(unittest.TestCase):
	def testValidGrammar(self):
		sqlparse.simpleSql.validate()

	def testLiteralSql(self):
		"""simple SQL statements for correct associativity, parens and such.
		"""
		literalSqlCases = [
			("select {{x|y|z}} from bla where a=b",
				"<Query for bla, <Items: x> -- a=b>"),
			("select {{x|y|z}} from bla where a=b and c=0",
				"<Query for bla, <Items: x> -- <a=b AND c=0>>"),
			("select {{x|y|z}} from bla where a=b and c=0 or d=e",
				"<Query for bla, <Items: x> -- <<a=b AND c=0> OR d=e>>"),
			("select {{x|y|z}} from bla where a=b and (c=0 or d=e)",
				"<Query for bla, <Items: x> -- <a=b AND <c=0 OR d=e>>>"),
			("select {{x|y|z}} from bla where x=y and a=b and (c=0 or d=e)",
				"<Query for bla, <Items: x> -- <x=y AND a=b AND <c=0 OR d=e>>>"),
			("select {{x|y|z}} from bla where x=y and a=b and c=0 or d=e",
				"<Query for bla, <Items: x> -- <<x=y AND a=b AND c=0> OR d=e>>"),
			("select {{x|y|z}} from bla where x=y and a=b or c=0 and d=e",
				"<Query for bla, <Items: x> -- <<x=y AND a=b> OR <c=0 AND d=e>>>"),
		]
		for sqlStatement, expectation in literalSqlCases:
			self.assertEqual(repr(sqlparse.parse(sqlStatement)), expectation)

	def testBadSql(self):
		"""bad sql that should raise exceptions.
		"""
		badSql = [
			"select from where",
			"select {{x|y|z}} {{y|z|a}} from where a=b",
			"select {{x|y|z}} from b, c, d where a=b",
			"select {{x|y|z}} from b, where a=b",
			"select {{x|y|z}} from b where a=b AND",
			"select {{x|y|z}}, from b where a=b AND c=d",
		]
		for botchedStatement in badSql:
			self.assertRaises(querulator.Error,
				sqlparse.parse, botchedStatement) 

	def _runStatementTests(self, statements):
		for statement, expectation in statements:
			self.assertEqual(repr(sqlparse.parse(statement)), expectation)

	def testPredefinedTests(self):
		"""predefined Tests in where conditions.
		"""
		statements = [
			("select {{x|x|x}} from y where {{bla|SexagConeSearch()}}",
				 "<Query for y, <Items: x> -- <Condition 'bla', "
				 	"SexagConeSearch(...)>>"),
		]
		self._runStatementTests(statements)

	def testClauses(self):
		"""tests for various forms of where clauses.
		"""
		statements = [
			("select {{x|x|x}} from y where {{bla|foo<IntField()}}",
				"<Query for y, <Items: x> -- <Condition 'bla', foo < IntField()>>"),
		]
		self._runStatementTests(statements)

	def testCompoundLvalues(self):
		"""tests for compound expressions left of a where operator.
		"""
		statements = [
			("select {{x|x|x}} from y where {{bla|a+b<IntField()}}",
				"<Query for y, <Items: x> -- <Condition 'bla', a+b < IntField()>>"),
			("select {{x|x|x}} from y where {{bla|sqrt(a^2+b^2)<IntField()}}",
				"<Query for y, <Items: x> -- <Condition 'bla', sqrt(a^2+b^2) <"
					" IntField()>>"),
		]
		self._runStatementTests(statements)

	def testSelectLists(self):
		"""tests various valid select lists.
		"""
		statements = [
			("select {{field|title with space|simplehint}} from u where x=y",
				"<Query for u, <Items: field> -- x=y>"),
			("select {{a+b||simplehint}} from u where x=y",
				"<Query for u, <Items: a+b> -- x=y>"),
			("select {{a||hint,'arg1',2,'arg blank'}} from u where x=y",
				"<Query for u, <Items: a> -- x=y>"),
			("select {{a+b/c|crazy stuff|hint,'arg1',2}} from u where x=y",
				"<Query for u, <Items: a+b/c> -- x=y>"),
		]
		self._runStatementTests(statements)


if __name__ == '__main__':
    unittest.main()
