"""
Tests for event propagation and user interaction.
"""

import traceback

from gavo.base import events

import testhelpers

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


if __name__=="__main__":
	testhelpers.main(EventDispatcherTest)
