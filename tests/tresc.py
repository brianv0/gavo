"""
Common test resources.
"""

from __future__ import with_statement

import os

from gavo import base
from gavo import rsc
from gavo.base import sqlsupport
from gavo.helpers import testhelpers
from gavo.protocols import creds
from gavo.user import admin


class DBConnection(testhelpers.TestResource):
	"""sets up a DB connection.
	"""
	setUpCost = 0.1

	def make(self, ignored):
		res = base.getDefaultDBConnection()
		return res
	
	def clean(self, conn):
		if not conn.closed:
			conn.commit()
			conn.close()


dbConnection = DBConnection()


class TestWithDBConnection(testhelpers.VerboseTest):
	"""A base class for tests needing just a connection as test resources.

	You get auto rollback of the connection.
	"""
	resources = [("conn", dbConnection)]

	def tearDown(self):
		self.conn.rollback()
		testhelpers.VerboseTest.tearDown(self)


class ProdtestTable(testhelpers.TestResource):
	"""the prodtest table defined in test.rd.

	The resource builds and tears down the table.  It returns a connection
	that is commited in the end, so you should make sure you clean up
	after yourself.  The prodtest table is dropped, of course.
	"""
	resources = [('conn', dbConnection)]
	setUpCost = 5

	def make(self, deps):
		self.conn = deps["conn"]
		rd = testhelpers.getTestRD()
		self.tableDef = rd.getById("prodtest")
		dd = rd.getDataDescById("productimport")
		self.data = rsc.makeData(dd, parseOptions=rsc.parseValidating, 
			connection=self.conn)
		return self.conn

	def clean(self, ignore):
		t = self.data.tables["prodtest"].drop()
		self.conn.commit()


prodtestTable = ProdtestTable()


class _NS(object): 
	def __init__(self, **kwargs):
		for k,v in kwargs.iteritems():
			setattr(self, k, v)


class TestUsers(testhelpers.TestResource):
	"""Test values in the user table.
	"""
	resources = [('conn', dbConnection)]
	setUpCost = 2
	tearDownCost = 2

	def make(self, deps):
		creds.adminProfile = "test"
		self.users = [
			_NS(user="X_test", password="megapass", remarks=""),
			_NS(user="Y_test", password="megapass", remarks="second test user"),
		]
		try:
			with base.SimpleQuerier(connection=deps["conn"]) as self.querier:
				for u in self.users:
					admin.adduser(self.querier, u)
				admin.addtogroup(self.querier, _NS(user="X_test", group="Y_test"))
		except admin.ArgError:  # stale users?  try again.
			self.clean(None)
			self.make(deps)
		return self.users

	def clean(self, ignore):
		with self.querier:
			for u in self.users:
				admin.deluser(self.querier, u)

testUsers = TestUsers()


class CSTestTable(testhelpers.TestResource):
	"""A database table including positions, as defined by test#adql.
	"""
	resources = [('conn', dbConnection)]

	def make(self, deps):
		self.conn = deps["conn"]
		dd = testhelpers.getTestRD().getById("csTestTable")
		self.dataCreated = rsc.makeData(dd, connection=self.conn)
		return self.dataCreated.getPrimaryTable()
	
	def clean(self, table):
		self.dataCreated.dropTables()

csTestTable = CSTestTable()
