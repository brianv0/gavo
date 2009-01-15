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

from gavo import base
from gavo.base import valuemappers
from gavo.svcs.computedcore import argMFRegistry


class RunnerError(base.Error):
	pass


class StdioProtocol(protocol.ProcessProtocol):
	"""is a simple program protocol that writes input to the process and
	sends the output to the deferred result in one swoop when done.
	"""
	def __init__(self, input, result, swallowStderr=False):
		self.input, self.result = input, result
		self.swallowStderr = swallowStderr
		self.dataReceived = []
	
	def connectionMade(self):
		self.transport.write(self.input)
		self.transport.closeStdin()
	
	def outReceived(self, data):
		self.dataReceived.append(data)

	def errReceived(self, data):
		if not self.swallowStderr:
			sys.stderr.write(data)

	def processEnded(self, status):
		if status.value.exitCode!=0:
			self.result.errback(status)
		else:
			self.result.callback("".join(self.dataReceived))
	

def runWithData(prog, inputString, args, swallowStderr=False):
	"""returns a deferred firing the complete result of running prog with
	args and inputString.
	"""
	result = defer.Deferred()
	fetchOutputProtocol = StdioProtocol(inputString, result, swallowStderr)
	prog = base.getBinaryName(prog)
	reactor.spawnProcess(fetchOutputProtocol, prog,
		args=[prog]+list(args), path=os.path.dirname(prog))
	return result
