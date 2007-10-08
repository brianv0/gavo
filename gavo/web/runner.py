"""
Methods and classes to run programs described through DataDescriptors
within a twisted event loop.
"""

import sys
import os

from twisted.internet import protocol, reactor, defer
from twisted.python.failure import Failure

import gavo
from gavo import config


class RunnerError(gavo.Error):
	pass


class StdioProtocol(protocol.ProcessProtocol):
	"""is a simple program protocol that writes input to the process and
	sends the output to the deferred result in one swoop when done.
	"""
	def __init__(self, input, result):
		self.input = input
		self.result = result
		self.dataReceived = []
	
	def connectionMade(self):
		self.transport.write(self.input)
		self.transport.closeStdin()
	
	def outReceived(self, data):
		self.dataReceived.append(data)

	def errReceived(self, data):
		sys.stderr.write(data)

	def processEnded(self, status):
		if status.value.exitCode!=0:
			self.result.errback(status)
		else:
			self.result.callback("".join(self.dataReceived))
	

def run(coreDescriptor, inputData):
	"""returns a table generated from running the computed data descriptor
	coreDescriptor on the DataSet inputData.
	"""
	result = defer.Deferred()
	inputString = _makeInputs(coreDescriptor, inputData)
	args = _makeArguments(coreDescriptor, inputData)
	fetchOutputProtocol = StdioProtocol(inputString, result)
	computerPath = os.path.join(config.get("rootDir"),
		coreDescriptor.get_computer())
	reactor.spawnProcess(fetchOutputProtocol, computerPath,
		args=[computerPath]+args, path=os.path.dirname(computerPath))
	return result


def _makeArguments(coreDescriptor, inputData):
	"""returns a list of command line arguments for coreDescriptor taken
	from (the docrec of) inputData
	"""
	clItems = coreDescriptor.getRecordDefByName("commandline").get_items()
	docRec = inputData.getDocRec()
# TODO: get and @-expander here?
# TODO: Validation!
	args = [(int(item.get_dest()), item.getValueIn(docRec)) 
		for item in clItems]
	args.sort()
	return [str(val) for ct, val in args if val!=None]


def _makeInputs(coreDescriptor, inputData):
	"""returns a string suitable as input to coreDescriptor's executable
	from inputData's first table's rows.
	"""
	res = []
	fields = coreDescriptor.getRecordDefByName("inputline").get_items()[:]
	fields.sort(lambda a, b: cmp(int(a.get_dest()), int(b.get_dest())))
# TODO: get and @-expander here?
	for row in inputData.getTables()[0]:
		res.append(" ".join([repr(field.getValueIn(row)) for field in fields]))
	return "\n".join(res)


if __name__=="__main__":
	from gavo import resourcecache
	from gavo import nullui
	from gavo import config
	config.setDbProfile("querulator")
	import datetime
	def printRes(res):
		print "Yay!"
		print res
	def printErr(err):
		print "Error:", err.getErrorMessage()
	rd = resourcecache.getRd("apfs/res/apfs_new")
	srv = rd.get_service("catquery")
	inputData = srv._getInputData({u'startDate': datetime.date(2008, 12, 10), 
		u'hrInterval': 24, u'star': u'56', 
		u'endDate': datetime.date(2008, 12, 14)})
	val = run(srv.get_core(), inputData)
	val.addCallback(printRes)
	val.addErrback(printErr)
	reactor.run()
