"""
Tests for event propagation and user interaction.
"""

import os
import sys
import traceback

from gavo.helpers import testhelpers

from gavo import base
from gavo.base import events
from gavo.helpers import testtricks
from gavo.user import cli



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


class CLITest(testhelpers.VerboseTest):
	"""tests for the CLI.
	"""
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

	def testLifecycle(self):
		querier = base.SimpleQuerier()
		try:
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
		finally:
			querier.close()

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
			with base.SimpleQuerier(useProfile="admin") as querier:
				querier.query("CREATE TABLE test.adql (erratic INTEGER)")
				querier.query("INSERT INTO test.adql VALUES (1)")

			with base.getTableConn() as conn:
				querier = base.SimpleQuerier(connection=conn)
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


if __name__=="__main__":
	testhelpers.main(CLITest)
