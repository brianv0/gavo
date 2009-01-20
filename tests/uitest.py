"""
Tests for event propagation and user interaction.
"""

import traceback

from gavo import base
from gavo.base import events

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


if __name__=="__main__":
	testhelpers.main(EventDispatcherTest)
