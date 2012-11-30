"""
Tests for event propagation and user interaction.
"""

import contextlib
import os
import sys
import traceback

from gavo.helpers import testhelpers

from gavo import base
from gavo import api
from gavo import rsc
from gavo.base import events
from gavo.helpers import testtricks
from gavo.user import cli

import tresc


class Tell(Exception):
	"""is raised by some listeners to show they've been called.
	"""


class EventDispatcherTest(testhelpers.VerboseTest):
	def testNoNotifications(self):
		"""tests for the various notifications not bombing out by themselves.
		"""
		ed = events.EventDispatcher()
		ed.notifyError("Something")

	def testNotifyError(self):
		def callback(ex):
			raise Exception(ex)
		ed = events.EventDispatcher()
		ed.subscribeError(callback)
		fooMsg = "WumpMessage"
		try:
			ed.notifyError(fooMsg)
		except Exception, foundEx:
			self.assertEqual(fooMsg, foundEx.args[0])

	def testUnsubscribe(self):
		res = []
		def callback(arg):
			res.append(arg)
		ed = events.EventDispatcher()
		ed.subscribeInfo(callback)
		ed.notifyInfo("a")
		ed.unsubscribeInfo(callback)
		ed.notifyInfo("b")
		self.assertEqual(res, ["a"])

	def testObserver(self):
		ed = events.EventDispatcher()
		class Observer(base.ObserverBase):
			@base.listensTo("NewSource")
			def gotNewSource(self, sourceName):
				raise Tell(sourceName)
		o = Observer(ed)
		ex = None
		try:
			ed.notifyNewSource("abc")
		except Tell, ex:
			pass
		self.assertEqual(ex.args[0], "abc")
		try:
			ed.notifyNewSource(range(30))
		except Tell, ex:
			pass
		self.assertEqual(ex.args[0], '[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1')


class MiscCLITest(testhelpers.VerboseTest):
	def testUnhandledException(self):
		self.assertOutput(cli.main, argList=["raise"], 
			expectedStderr=lambda msg: "Unhandled exception" in msg,
			expectedRetcode=1)

	def testTopLevelHelp(self):
		self.assertOutput(cli.main, argList=["--help"], 
			expectedStdout=lambda msg: "<func> is a unique" in msg)

	def testNonUniqueMatch(self):
		self.assertOutput(cli.main, argList=["a"], 
			expectedRetcode=1,
			expectedStderr=
				lambda msg: msg.startswith("Multiple matches for function a"))

	def testNoMatch(self):
		self.assertOutput(cli.main, argList=["xyloph"], 
			expectedRetcode=1,
			expectedStderr=
				lambda msg: msg.startswith("No match for function xyloph"))

	def testSubCmdHelp(self):
		self.assertOutput(cli.main, argList=["publish", "--help"], 
			expectedStdout=lambda msg: "gavo publish [options] {<rd-name>}" in msg)

	def testAProg(self):
		self.assertOutput(cli.main, argList=["stc", "utypes", "Position ICRS"],
			expectedStdout=lambda msg: 
				"AstroCoordSystem.SpaceFrame.CoordRefFrame" in msg)

	def testCleanTAP(self):
		self.assertOutput(cli.main, argList=["admin", "cleantap"],
			expectedRetcode=0)

	def testCleanTAPPending(self):
		self.assertOutput(cli.main, argList=["admin", "cleantap", "-p"],
			expectedRetcode=0, expectedStderr="")

	def testShowDD(self):
		self.assertOutput(cli.main, argList=["show", "dds", "//tap"],
			expectedStdout="createSchema*\nimport_examples*\ncreateJobTable*\n")

	def testShowDDBad(self):
		self.assertOutput(cli.main, argList=["show", "dds", "//dc_tables", "bla"],
			expectedRetcode=1,
			expectedStderr=lambda msg: 
				"The DD 'bla' you are trying to import" in msg)


class ImportTest(testhelpers.VerboseTest):
	def testLifecycle(self):
		with base.AdhocQuerier() as querier:
			self.assertOutput(cli.main, 
				argList=["--suppress-log",
					"imp", "data/test", "productimport"],
				stdoutStrings=["Columns affected: 2"])

			self.failUnless(querier.tableExists("test.prodtest"))
			self.failIf(querier.tableExists("test.typesTable"))

			self.assertOutput(cli.main,
				argList=["--disable-spew", "--suppress-log", "publish", "data/test"])

			self.failUnless(list(querier.query("SELECT * FROM dc.subjects"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))

			# drop it all, make sure all traces are gone
			self.assertOutput(cli.main,
				argList=["--disable-spew", "--suppress-log",
					"drop", "data/test"], expectedStdout="", expectedStderr="")
			self.failIf(list(querier.query("SELECT * FROM dc.subjects"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))
			self.failIf(querier.tableExists("test.prodtest"))

	def testImportDeniedForOffInputs(self):
		destName = os.path.expanduser("~/foobar.rd")
		with testhelpers.testFile(destName, '<resource schema="junk"/>'):
			self.assertOutput(cli.main, 
				argList=["imp", destName],
				expectedRetcode=1, expectedStderr=
				"*** Error: Only RDs from below inputsDir may be imported.\n")

	def testMetaImportAndPurge(self):
		self.assertOutput(cli.main, argList=["purge", "test.adql"])
		try:
			with base.AdhocQuerier(base.getWritableAdminConn) as querier:
				querier.query("CREATE TABLE test.adql (erratic INTEGER)")
				querier.query("INSERT INTO test.adql VALUES (1)")

			with base.AdhocQuerier() as querier:
				self.assertOutput(cli.main, argList=
					["imp", "-m", "data/test", "ADQLTest"],
					expectedStdout="Updating meta for ADQLTest\n")
				self.assertEqual(list(querier.query(
					"select * from dc.tablemeta where tablename='test.adql'")),
					[(u'test.adql', u'data/test', None, None, True)])
				
				# make sure gavo imp didn't touch the table
				self.assertEqual(list(querier.query("SELECT * FROM test.adql")),
					[(1,)])
		finally:
			self.assertOutput(cli.main, argList=["purge", "test.adql"])

	def testNoDataImpError(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "empty.rd"),
				"""<resource schema="test"><table id="foo"/></resource>"""):
			self.assertOutput(cli.main, argList=["--hints", "imp", "empty"],
				expectedRetcode=1, expectedStderr='*** Error: Neither automatic'
					" not manual data selected from RD empty\nHint: There is no"
					" data element in your RD.  This is almost never what\nyou want"
					' (see the tutorial)\n')

	def testNonExistingDataImpError(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "empty.rd"),
				"""<resource schema="test"><table id="foo"/></resource>"""):
			self.assertOutput(cli.main, argList=["--hints", "imp", "empty", "foo"],
				expectedRetcode=1, expectedStderr="*** Error: The DD 'foo'"
					" you are trying to import is not defined within\nthe RD"
					" 'empty'.\nHint: Data elements available in empty include (None)\n")

	def testNoAutoDataImpError(self):
		with testtricks.testFile(
				os.path.join(base.getConfig("inputsDir"), "empty.rd"),
				"""<resource schema="test"><table id="foo"/>
				<data auto="False" id="x"><make table="foo"/></data>
				<data auto="False" id="y"><make table="foo"/></data>
				</resource>"""):
			self.assertOutput(cli.main, argList=["--hints", "imp", "empty"],
				expectedRetcode=1, expectedStderr='*** Error: Neither automatic'
					' not manual data selected from RD empty\nHint: All data'
					' elements have auto=False.  You have to explicitely name\none'
					' or more data to import (names available: x, y)\n')


class _SysRDResource(tresc.FileResource):
	path = "inputs/sysrd.rd"
	content = """<resource schema="test">
			<table onDisk="True" id="fromclitest" system="True">
				<column name="x" type="integer"><values nullLiteral="0"/></column>
			</table>
			<data id="y"><make table="fromclitest"/></data>
		</resource>"""


class SystemImportTest(testhelpers.VerboseTest):
	resources = [("conn", tresc.dbConnection),
		("sysrdFile", _SysRDResource())]

	def _fillTable(self):
		rd = api.getRD("sysrd")
		t = rsc.TableForDef(rd.getById("fromclitest"), connection=self.conn)
		t.addRow({'x': 2})
		self.conn.commit()

	def testNoSystemImportDefault(self):
		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		# Write a 2 into the table that must survive the next imp
		self._fillTable()

		self.assertOutput(cli.main, argList=["imp", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.assertEqual(list(q.query("select * from test.fromclitest")),
				[(2,)])
			
	def testSystemImport(self):
		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		# Write a 2 into the table that must survive the next imp
		self._fillTable()

		self.assertOutput(cli.main, argList=["imp", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.assertEqual(list(q.query("select * from test.fromclitest")),
				[])

	def testSystemDropDrops(self):
		self.assertOutput(cli.main, argList=["drop", "--system", "sysrd"],
			expectedRetcode=0, expectedStderr="", expectedStdout="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.fromclitest"))


class _MyRDResource(tresc.FileResource):
	path = "inputs/myrd.rd"
	content = """<resource schema="test">
			<table onDisk="True" id="autotable">
				<column name="x" type="integer" required="True"/></table>
			<table onDisk="True" id="noautotable">
				<column name="x" type="integer" required="True"/></table>
			<data id="y"><make table="autotable"/></data>
			<data id="z" auto="False"><make table="noautotable"/></data>
		</resource>"""


class DropTest(testhelpers.VerboseTest):
	resources = [("myrdFile", _MyRDResource())]

	def testAutoDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.autotable"))
			self.failUnless(q.tableExists("test.noautotable"))

	def testAllDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd", "--all"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failIf(q.tableExists("test.autotable"))
			self.failIf(q.tableExists("test.noautotable"))

	def testNamedDropping(self):
		self.assertOutput(cli.main, argList=["imp", "myrd", "y", "z"],
			expectedRetcode=0, expectedStderr="")
		self.assertOutput(cli.main, argList=["drop", "myrd", "z"],
			expectedRetcode=0, expectedStderr="")
		with base.AdhocQuerier() as q:
			self.failUnless(q.tableExists("test.autotable"))
			self.failIf(q.tableExists("test.noautotable"))


if __name__=="__main__":
	testhelpers.main(DropTest)
