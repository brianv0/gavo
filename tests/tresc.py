"""
Common test resources.
"""

import os

from gavo import base
from gavo import rsc

import testhelpers


class ProdtestTable(testhelpers.TestResource):
	"""the prodtest table defined in test.rd.

	The resource builds and tears down the table.  It returns a connection
	that is commited in the end, so you should make sure you clean up
	after yourself.  The prodtest table is dropped, of course.
	"""
	def make(self, ignored):
		base.setDBProfile("test")
		self.oldInputs = base.getConfig("inputsDir")
		base.setConfig("inputsDir", os.getcwd())
		rd = testhelpers.getTestRD()
		self.tableDef = rd.getById("prodtest")
		dd = rd.getDataDescById("productimport")
		self.conn = base.getDefaultDBConnection()
		self.data = rsc.makeData(dd, parseOptions=rsc.parseValidating, 
			connection=self.conn)
		return self.conn

	def clean(self, ignore):
		t = self.data.tables["prodtest"].drop()
		base.setConfig("inputsDir", self.oldInputs)
		self.conn.commit()
		self.conn.close()
