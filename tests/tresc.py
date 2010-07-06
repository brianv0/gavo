"""
Common test resources.
"""

import os

from gavo import base
from gavo import rsc
from gavo.base import sqlsupport

import testhelpers


class DBConnection(testhelpers.TestResource):
	"""sets up a DB connection.
	"""
	def make(self, ignored):
		return base.getDefaultDBConnection()
	
	def clean(self, conn):
		try:
			conn.commit()
		except sqlsupport.InterfaceError:  # connection already closed
			pass


dbConnection = DBConnection()


class ProdtestTable(testhelpers.TestResource):
	"""the prodtest table defined in test.rd.

	The resource builds and tears down the table.  It returns a connection
	that is commited in the end, so you should make sure you clean up
	after yourself.  The prodtest table is dropped, of course.
	"""
	resources = [('conn', dbConnection)]

	def make(self, dependents):
		self.conn = dependents["conn"]
		rd = testhelpers.getTestRD()
		self.tableDef = rd.getById("prodtest")
		dd = rd.getDataDescById("productimport")
		self.data = rsc.makeData(dd, parseOptions=rsc.parseValidating, 
			connection=self.conn)
		return self.conn

	def clean(self, ignore):
		t = self.data.tables["prodtest"].drop()
		self.conn.commit()
		self.conn.close()


prodtestTable = ProdtestTable()
