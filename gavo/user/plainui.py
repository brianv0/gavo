"""
Observers for running interactive programs in the terminal.
"""

from gavo import utils
from gavo.base import ObserverBase, listensTo

class StingyPlainUI(ObserverBase):
	"""An Observer swallowing infos, warnings, and the like.
	"""
	def __init__(self, eh):
		ObserverBase.__init__(self, eh)
		self.curIndent = ""

	def showMsg(self, msg):
		print self.curIndent+msg

	def pushIndent(self):
		self.curIndent = self.curIndent+"  "
	
	def popIndent(self):
		self.curIndent = self.curIndent[:-2]

	@listensTo("NewSource")
	def announceNewSource(self, srcString):
		self.showMsg("Starting %s"%srcString)
		self.pushIndent()
	
	@listensTo("SourceFinished")
	def announceSourceFinished(self, srcString):
		self.popIndent()
		self.showMsg("Done %s, read %d"%(srcString, self.dispatcher.totalRead))
	
	@listensTo("SourceError")
	def announceSourceError(self, srcString):
		self.popIndent()
		self.showMsg("Failed %s"%srcString)

	@listensTo("Error")
	def printErrMsg(self, errMsg):
		self.showMsg("*X*X* "+errMsg)


class PlainUI(StingyPlainUI):
	"""An Observer spitting out most info to the screen.
	"""

	@listensTo("Shipout")
	def announceShipout(self, noShipped):
		self.showMsg("Shipped %d/%d"%(
			noShipped, self.dispatcher.totalShippedOut))
	
	@listensTo("IndexCreation")
	def announceIndexing(self, indexName):
		self.showMsg("Create index %s"%indexName)
	
	@listensTo("FailedRow")
	def announceFailedRow(self, args):
		row, excInfo = args
		self.showMsg("--- Ignoring bad row: %s (%s)"%(
			utils.makeEllipsis(str(row), 30), 
			str(excInfo[1])))
	
	@listensTo("ScriptRunning")
	def announceScriptRunning(self, runner):
		self.showMsg("%s excecuting script %s"%(
			runner.__class__.__name__, runner.name))
	
	@listensTo("Info")
	def printInfo(self, message):
		self.showMsg(message)

	@listensTo("Warning")
	def printWarning(self, message):
		self.showMsg(message)



