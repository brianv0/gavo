"""
Some tests for the database interface.

This only works with psycopg2.
"""

import unittest

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import nullui
from gavo import sqlsupport

import testhelpers


class TestTypes(unittest.TestCase):
	"""Tests for some special adapters we provide.
	"""
	def setUp(self):
		config.setDbProfile("test")
		tableDef = testhelpers.getTestTable("misctypes")
		tw = sqlsupport.TableWriter(tableDef)
		tw.createTable()
		feed = tw.getFeeder()
		feed({"box": coords.Box(1,2,3,4)})
		tw.finish()
		self.tableName = tableDef.getQName()

	def testBoxUnpack(self):
		querier = sqlsupport.SimpleQuerier()
		try:
			r = querier.query(
				"SELECT * FROM %s WHERE box IS NOT NULL"%self.tableName).fetchall()
			self.assertEqual(r[0][0][0], (2,4))
			self.assertEqual(r[0][0][1], (1,3))
		finally:
			querier.close()

	def tearDown(self):
		querier = sqlsupport.SimpleQuerier()
		querier.query("DROP TABLE %s CASCADE"%self.tableName)
		querier.commit()


if __name__=="__main__":
	unittest.main()
