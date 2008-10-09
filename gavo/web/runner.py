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
from gavo import valuemappers
from gavo.parsing import resource


class RunnerError(gavo.Error):
	pass


# Valuemappers for both command line arguments and input values 
_argMFRegistry = valuemappers.ValueMapperFactoryRegistry()
_registerArgMF = _argMFRegistry.registerFactory

def _defaultMapperFactory(colProps):
	def coder(val):
		return str(val)
	return coder
_registerArgMF(_defaultMapperFactory)

datetimeDbTypes = set(["timestamp", "date", "time"])
def _datetimeMapperFactory(colProps):
	if colProps["dbtype"] not in datetimeDbTypes:
		return
	def coder(val):
		if val:
			return val.strftime("%Y-%m-%dT%H:%M:%S")
		return "None"
	return coder
_registerArgMF(_datetimeMapperFactory)


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
		args=[prog]+list(args), path=os.path.dirname(prog))
	return result


def _makeArguments(core, inputData):
	"""returns an argument list from inputData.

	The argument list is generated from the fields defined in the
	commandLine table in the core definition, taking data from the
	inputData's docRec
	"""
	argNames = [f.get_dest() 
		for f in core.getTableDefWithRole("commandLine").get_items()]
	argTable = table.Table(None, core.getTableDefWithRole("commandLine"))
	argTable.addData(inputData.getDocRec())
	row = valuemappers.getMappedValues(argTable, _argMFRegistry).next()
	return [row[name] for name in argNames]


def _makeInputs(core, inputData):
	"""returns the program input as a string.

	The program input is defined by the inputLine table of the core
	definition.  The values are taken from each row of inputData's
	primary table, stringified and concatenated with spaces in the
	sequence of the inputLine definition.  Each row comes in a line
	of its own.
	"""
	res = []
	inputNames = [f.get_dest() 
		for f in core.getTableDefWithRole("inputLine").get_items()]
	for row in valuemappers.getMappedValues(inputData.getPrimaryTable(),
			_argMFRegistry):
		res.append(" ".join([row[name] for name in inputNames]))
	return str("\n".join(res))


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
