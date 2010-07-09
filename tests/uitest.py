"""
Tests for event propagation and user interaction.
"""

import os
import traceback

from gavo import base
from gavo.base import events
from gavo.helpers import testhelpers
from gavo.user import cli



class Tell(Exception):
	"""is raised by some listeners to show they've been called.
	"""


class EventDispatcherTest(testhelpers.VerboseTest):
	def testNoNotifications(self):
		"""tests for the various notifications not bombing out by themselves.
		"""
		ed = events.EventDispatcher()
		ed.notifyErrorOccurred("Something")

	def testNotifyError(self):
		def callback(ex):
			raise Exception(ex)
		ed = events.EventDispatcher()
		ed.subscribeErrorOccurred(callback)
		fooMsg = "WumpMessage"
		try:
			ed.notifyErrorOccurred(fooMsg)
		except Exception, foundEx:
			self.assertEqual(fooMsg, foundEx.args[0])

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


class LoadModuleTest(testhelpers.VerboseTest):
	"""tests for cli's module loader.
	"""
	def testLoading(self):
		ns = cli.loadGAVOModule("utils.codetricks")
		self.failUnless("loadPythonModule" in dir(ns))
	
	def testNotLoading(self):
		self.assertRaises(ImportError, cli.loadGAVOModule, "noexist")


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
		"""runs a complete lifecycle of a resource.
		"""
		querier = base.SimpleQuerier()
		try:
			self.assertOutput(cli.main, 
				argList=["imp", "data/test", "productimport"],
				stdoutStrings=["Columns affected: 2"])

			self.failUnless(querier.tableExists("test.prodtest"))
			self.failIf(querier.tableExists("test.typestable"))

			self.assertOutput(cli.main,
				argList=["publish", "data/test"])

			self.failUnless(list(querier.query("SELECT * FROM srv_subjs"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))

			# drop it all, make sure all traces are gone
			self.assertOutput(cli.main,
				argList=["drop", "data/test"], expectedStdout="", expectedStderr="")

			self.failIf(list(querier.query("SELECT * FROM srv_subjs"
				" WHERE subject=%(s)s", {'s': "Problems, somebody else's"})))
			self.failIf(querier.tableExists("test.prodtest"))
		finally:
			querier.close()



if __name__=="__main__":
	testhelpers.main(CLITest)
