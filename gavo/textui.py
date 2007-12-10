import sys

import gavo
from gavo import nullui

class _GoodBadCounter:
	"""is a progress counter that allows counting bad items in progress.
	"""
	def __init__(self, title, updateInterval):
		self.title = title
		self.updateInterval = updateInterval
		self.counter, self.badCounter = 0, 0
		self.formatString = "\r%s: %%d (%%d bad)"%self.title
		self._updateDisplay()
	
	def hit(self):
		self.counter += 1
		self._updateDisplay()

	def unhit(self):
		self.counter -= 1

	def hitBad(self):
		self.badCounter += 1
		self._updateDisplay(force=True)

	def _updateDisplay(self, force=False):
		if force or not self.counter%self.updateInterval:
			sys.stdout.write(self.formatString%(self.counter, 
				self.badCounter))
			sys.stdout.flush()
	
	def close(self):
		print "\r%s finished.  %d processed, of which %d had errors"%(
			self.title, self.counter, self.badCounter)


class TextUi:
	silence = False

	def displayMessage(self, msg):
		if not self.silence:
			print msg
	
	def displayError(self, msg):
		print "\n***\n*** Error: %s\n***"%msg

	def getGoodBadCounter(self, title, updateInterval):
		if self.silence:
			return nullui.NullCounter()
		else:
			return _GoodBadCounter(title, updateInterval)


gavo.ui = TextUi()
