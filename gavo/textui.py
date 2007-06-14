import sys

import gavo

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

	def _updateDisplay(self):
		if not self.counter%self.updateInterval:
			sys.stdout.write(self.formatString%(self.counter, 
				self.badCounter))
			sys.stdout.flush()
	
	def close(self):
		print "\r%s finished.  %d processed, of which %d had errors"%(
			self.title, self.counter, self.badCounter)


class TextUi:
	def displayMessage(self, msg):
		print msg
	
	def displayError(self, msg):
		print "*** Nonfatal error:", msg

	def getGoodBadCounter(self, title, updateInterval):
		return _GoodBadCounter(title, updateInterval)


gavo.ui = TextUi()
