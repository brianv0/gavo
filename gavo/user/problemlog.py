"""
An observer that collects notifications of failed rows and lets clients
dump them.
"""

from gavo.base import ObserverBase, listensTo

class FailedRowCollector(ObserverBase):
	def __init__(self, eh):
		ObserverBase.__init__(self, eh)
		self.failedRows = []
	
	@listensTo("FailedRow")
	def addFailedRow(self, args):
		row, excInfo = args  # Don't store exc_info as a whole, since that might
			# use up astonishing amounts of memory.
		self.failedRows.append((str(excInfo[1]), row))
	
	def dump(self, destFName):
		if self.failedRows:
			f = open(destFName, "w")
			for r in self.failedRows:
				f.write("%s -- %s\n"%r)
			f.close()
