"""
Common test resources.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import contextlib
import os

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.base import sqlsupport
from gavo.protocols import creds
from gavo.user import admin


class DBConnection(testhelpers.TestResource):
	"""sets up a DB connection.
	"""
	setUpCost = 0.1

	def make(self, ignored):
		return base.getDBConnection("admin")
	
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

	prodtbl = None

	def make(self, deps):
		self.conn = deps["conn"]
		rd = testhelpers.getTestRD()
		self.tableDef = rd.getById("prodtest")
		dd = rd.getDataDescById("productimport")
		self.data = rsc.makeData(dd, 
			parseOptions=rsc.parseValidating.change(keepGoing=True), 
			connection=self.conn)
		self.conn.commit()
		return self.conn

	def clean(self, ignore):
		self.conn.rollback()
		t = self.data.tables["prodtest"].drop()
		self.conn.commit()

	_defaultProdtblEntry = {
		"accessPath": "/road/to/nowhere",
		"accref": "just.testing/nowhere",
		"sourceTable": "/////////////////////",
		"owner": None,
		"embargo": None,
		"mime": "application/x-bogus",
		"datalink": None,
		"preview": 'AUTO'}

	@contextlib.contextmanager
	def prodtblRow(self, **kwargs):
		rec = self._defaultProdtblEntry.copy()
		rec.update(kwargs)
		if self.prodtbl is None:
			self.prodtbl = rsc.TableForDef(
				base.caches.getRD("//products").getById("products"),
				connection=self.conn)
		self.prodtbl.addRow(rec)
		self.conn.commit()
		try:
			yield
		finally:
			self.prodtbl.query("delete from dc.products where sourceTable=%(s)s",
				{"s": rec["sourceTable"]})
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
		self.conn = deps["conn"]
		self.users = [
			_NS(user="X_test", password="megapass", remarks=""),
			_NS(user="Y_test", password="megapass", remarks="second test user"),
		]
		try:
			querier = base.UnmanagedQuerier(connection=self.conn)
			for u in self.users:
				admin.adduser(querier, u)
			admin.addtogroup(querier, _NS(user="X_test", group="Y_test"))
			self.conn.commit()
		except admin.ArgError:  # stale users?  try again.
			self.conn.rollback()
			self.clean(None)
			for u in self.users:
				admin.adduser(querier, u)
			admin.addtogroup(querier, _NS(user="X_test", group="Y_test"))
			self.conn.commit()
		return self.users

	def clean(self, ignore):
		querier = base.UnmanagedQuerier(connection=self.conn)
		for u in self.users:
			try:
				admin.deluser(querier, u)
			except admin.ArgError: # user hasn't been created, go on
				pass
		self.conn.commit()
		

testUsers = TestUsers()


class RDDataResource(testhelpers.TestResource):
	"""A resource consiting generated from a data item in an RD.

	Specify the name of an rd file in data in the rdName class attribute
	(default: test.rd), the id of the data object within in dataId.
	"""
	resources = [('conn', dbConnection)]

	rdName = "test.rd"
	dataId = None

	def make(self, deps):
		self.conn = deps["conn"]
		dd = testhelpers.getTestRD(self.rdName).getById(self.dataId)
		self.dataCreated = rsc.makeData(dd, connection=self.conn)
		return self.dataCreated.getPrimaryTable()
	
	def clean(self, table):
		self.conn.rollback()
		self.dataCreated.dropTables(rsc.parseNonValidating)
		self.conn.commit()


class CSTestTable(RDDataResource):
	"""A database table including positions, as defined by test#adql.
	"""
	dataId = "csTestTable"

csTestTable = CSTestTable()


class _SSATable(testhelpers.TestResource):
# This stuff is now imported by testhelpers on test environment creation
# (that's mainly so trial can use it, too).
	resources = [("conn", dbConnection)]

	def make(self, deps):
		conn = deps["conn"]
		dd = base.caches.getRD("data/ssatest").getById("test_import")
		data = rsc.makeData(dd, connection=conn)
		return data.getPrimaryTable()
	
	def clean(self, res):
		# Leave the stuff so trial still has it.
		pass

ssaTestTable = _SSATable()


class RandomDataTable(testhelpers.TestResource):
	"""An in-memory table with a couple of rows.
	"""
	def make(self, deps):
		td = base.parseFromString(rscdef.TableDef,
			"""<table id="randomDataTable"><column name="n" type="integer"/>
				<column name="x"/></table>""")
		return rsc.TableForDef(td, rows=[
			{"n": 23, "x": 29.25},
			{"n": 42, "x": -1.75}])

randomDataTable = RandomDataTable()


class FileResource(testhelpers.TestResource):
	"""An "abstract" resource that represents a temporary file within
	the root directory with a given name and content.

	path and content are given in class attributes of the same names,
	where path is interpreted relative to rootDir.
	"""
	path, content = None, None

	def make(self, ignored):
		if self.path is None or self.content is None:
			raise Exception("FileResource without name or content")
		self.absPath = os.path.join(base.getConfig("rootDir"), self.path)
		with open(self.absPath, "w") as f:
			f.write(self.content)
		return self.absPath
	
	def clean(self, rsc):
		os.unlink(self.absPath)
