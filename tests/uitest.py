"""
Tests for event propagation and user interaction.
"""

import traceback

from gavo import base
from gavo.base import events
from gavo.user import cli

import testhelpers


class Tell(Exception):
	"""is raised by some listeners to show they've been called.
	"""


class EventDispatcherTest(testhelpers.VerboseTest):
	def testNoNotifications(self):
		"""tests for the various notifications not bombing out by themselves.
		"""
		ed = events.EventDispatcher()
		ed.notifyException(Exception())

	def testNotifyException(self):
		def callback(ex):
			raise ex
		ed = events.EventDispatcher()
		ed.subscribeException(callback)
		fooEx = Exception("foo")
		try:
			ed.notifyException(fooEx)
		except Exception, foundEx:
			self.assertEqual(fooEx, foundEx)

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
			expectedStdout=lambda msg: "<func> is one of adql" in msg)

	def testSubCmdHelp(self):
		self.assertOutput(cli.main, argList=["pub", "--help"], 
			expectedStdout=lambda msg: "gavo pub [options] {<rd-name>}" in msg)

	def testAProg(self):
		self.assertOutput(cli.main, argList=["stc", "utypes", "Position ICRS"],
			expectedStdout=lambda msg: 
				"AstroCoordSystem.SpaceFrame.CoordRefFrame" in msg)


if __name__=="__main__":
	testhelpers.main(CLITest)
