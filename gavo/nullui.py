"""
This is a ui that swallows all output.  You'll want this when you're
talking to the web.
"""

import gavo


class NullCounter:
	def __init__(self, *args):
		pass
	
	def hit(*args):
		pass
	
	def unhit(*args):
		pass
	
	def hitBad(*args):
		pass
	
	def close(*args):
		pass


class NullUi:
	silence = True
	def displayMessage(*args):
		pass
	displayError = displayMessage
	
	def getGoodBadCounter(self, *args):
		return NullCounter()
	

gavo.ui = NullUi()
