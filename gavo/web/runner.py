"""
Methods and classes to run programs described through DataDescriptors
within a twisted event loop.
"""

import sys
import os

from twisted.internet import protocol
from twisted.internet import reactor 
from twisted.internet import defer
from twisted.python import threadable
from twisted.python.failure import Failure

import gavo
from gavo import config
from gavo import table
from gavo.parsing import resource


class RunnerError(gavo.Error):
	pass


class StreamingRunner(protocol.ProcessProtocol):
	"""is a connector of a program writing to stdout and the consumer interface
	of a nevow request.
	"""
	def __init__(self, prog, args, request):
		self.buffer = []
		self.errMsgs = []
		self.request = request
		self.isPaused = False
		self.allDataIsIn = False
		reactor.spawnProcess(self, prog,
			args=[prog]+args, path=os.path.dirname(prog))
		request.registerProducer(self, True)

	def outReceived(self, data):
		if self.isPaused:
			self.buffer.append(data)
			return
		self.request.write(data)

	def errReceived(self, data):
		self.errMsgs.append(data)
	
	def handleFatalError(self, data):
# XXX TODO: make this actually used -- e.g., when the program doesn't exist
		self.request.setHeader("content-type", "text/plain")
		self.request.write("Yikes -- something bad happened while I was"
			" reading from an external program (%s).  I must give up and hope"
			" you're seeing this to alert GAVO staff."%str(data))
		self.request.unregisterProducer()
		self.request.finishRequest(True)

	def processEnded(self, status):
		if status.value.exitCode!=0:
			# XXX TODO figure out how to make request emit an error
			pass
		else:
			self.allDataIsIn = True
			self.resumeProducing()

	def resumeProducing(self):
		self.isPaused = False
		if self.buffer:
			self.request.write("".join(self.buffer))
			self.buffer = []
		if self.allDataIsIn:
			self.request.unregisterProducer()
			self.request.finish()
			self.request = None

	def pauseProducing(self):
		self.isPaused = False

	def stopProducing(self):
# XXX TODO: Kill child if necessary
		self.buffer = []
		self.request = None

	synchronized = ['resumeProducing', 'stopProducing']

threadable.synchronize(StreamingRunner)


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
	

def getBinaryName(baseName):
	"""returns the name of a binary it thinks is appropriate for the platform.

	To do this, it asks config for the platform name, sees if there's a binary
	<bin>-<platname> if platform is nonempty.  If it exists, it returns that name,
	in all other cases, it returns baseName unchanged.
	"""
	platform = config.get("platform")
	if platform:
		platName = baseName+"-"+platform
		if os.path.exists(platName):
			return platName
	return baseName


def run(core, inputData):
	"""returns the output of the the binary specified by core with the
	arguments and input specified by the DataSet inputData.
	"""
	inputString = _makeInputs(core, inputData)
	args = _makeArguments(core, inputData)
	computerPath = getBinaryName(os.path.join(config.get("rootDir"),
		core.get_computer()))
	return runWithData(computerPath, inputString, args)


def runWithData(prog, inputString, args):
	"""returns a deferred firing the complete result of running prog with
	args and inputString.
	"""
	result = defer.Deferred()
	fetchOutputProtocol = StdioProtocol(inputString, result)
	prog = getBinaryName(prog)
	reactor.spawnProcess(fetchOutputProtocol, prog,
		args=[prog]+args, path=os.path.dirname(prog))
	return result


def _makeArguments(core, inputData):
	"""returns an argument list from inputData.

	The argument list is generated from the fields defined in the
	commandLine table in the core definition, taking data from the
	inputData's docRec
	"""
# XXX TODO: stringification currently sucks.  Maybe do something with
# formatting hints?
	args = []
	docRec = inputData.getDocRec()
	cmdItems = core.getTableDefWithRole("commandLine").get_items()
	for field in cmdItems:
		args.append(str(field.getValueIn(docRec)))
	return args


def _makeInputs(core, inputData):
	"""returns the program input as a string.

	The program input is defined by the inputLine table of the core
	definition.  The values are taken from each row of inputData's
	primary table, stringified and concatenated with spaces in the
	sequence of the inputLine definition.  Each row comes in a line
	of its own.
	"""
	lineItems = core.getTableDefWithRole("inputLine").get_items()
	res = []
	for row in inputData.getPrimaryTable().rows:
		res.append(" ".join([repr(field.getValueIn(row)) for field in lineItems]))
	return "\n".join(res)


if __name__=="__main__":
	from gavo import resourcecache
	from gavo import nullui
	from gavo import config
	config.setDbProfile("trustedquery")
	import datetime
	def printRes(res):
		print "Yay!"
		print res
	def printErr(err):
		print "Error:", err.getErrorMessage()
	rd = resourcecache.getRd("apfs/res/apfs_new")
	srv = rd.get_service("catquery")
	inputData = srv.getInputData({u'startDate': datetime.date(2008, 12, 10), 
		u'hrInterval': 24, u'star': u'56', 
		u'endDate': datetime.date(2008, 12, 14)})
	val = run(srv.get_core(), inputData)
	val.addCallback(printRes)
	val.addErrback(printErr)
	reactor.run()
