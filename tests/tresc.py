"""
Common test resources.
"""

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

	prodtbl = None

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

	_defaultProdtblEntry = {
		"accessPath": "/road/to/nowhere",
		"accref": "just.testing/nowhere",
		"sourceTable": "/////////////////////",
		"owner": None,
		"embargo": None,
		"mime": "application/x-bogus"}

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
		self.dataCreated.dropTables(rsc.parseNonValidating)


class CSTestTable(RDDataResource):
	"""A database table including positions, as defined by test#adql.
	"""
	dataId = "csTestTable"

csTestTable = CSTestTable()


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

