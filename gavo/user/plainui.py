"""
Observers for running interactive programs in the terminal.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base


class StingyPlainUI(base.ObserverBase):
	"""An Observer swallowing infos, warnings, and the like.
	"""
	def __init__(self, eh):
		self.curIndent = ""
		base.ObserverBase.__init__(self, eh)
 
	def showMsg(self, msg):
		print self.curIndent+msg

	def pushIndent(self):
		self.curIndent = self.curIndent+"  "
	
	def popIndent(self):
		self.curIndent = self.curIndent[:-2]

	@base.listensTo("SourceError")
	def announceSourceError(self, srcString):
		self.showMsg("Failed source %s"%srcString)

	@base.listensTo("Error")
	def printErrMsg(self, errMsg):
		self.showMsg("*X*X* "+errMsg)


class SemiStingyPlainUI(StingyPlainUI):
	"""a StingyPlainUI that at least displays warnings.
	"""
	@base.listensTo("Warning")
	def printWarning(self, message):
		self.showMsg("** WARNING: "+message)


class PlainUI(SemiStingyPlainUI):
	"""An Observer spitting out most info to the screen.
	"""
	@base.listensTo("NewSource")
	def announceNewSource(self, srcString):
		self.showMsg("Starting %s"%srcString)
		self.pushIndent()
	
	@base.listensTo("SourceFinished")
	def announceSourceFinished(self, srcString):
		self.popIndent()
		self.showMsg("Done %s, read %d"%(srcString, self.dispatcher.totalRead))
	
 	@base.listensTo("SourceError")
 	def announceSourceError(self, srcString):
		self.popIndent()
 		self.showMsg("Failed %s"%srcString)

	@base.listensTo("Shipout")
	def announceShipout(self, noShipped):
		self.showMsg("Shipped %d/%d"%(
			noShipped, self.dispatcher.totalShippedOut))
	
	@base.listensTo("IndexCreation")
	def announceIndexing(self, indexName):
		self.showMsg("Create index %s"%indexName)
	
	@base.listensTo("ScriptRunning")
	def announceScriptRunning(self, runner):
		self.showMsg("%s excecuting script %s"%(
			runner.__class__.__name__, runner.name))
	
	@base.listensTo("Info")
	def printInfo(self, message):
		self.showMsg(message)
