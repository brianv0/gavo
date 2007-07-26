"""
Abstract the execution of external programs or callables.
"""

import os
import sys
import popen2
import select
import fcntl
import cStringIO

import gavo

class DataCollector:
	"""is a simple data collector satisfying the the table protocol. 
	
	It can stand in as a table in a parsing.importparser.DataDescriptor,
	and you can get the parsed data through either fetchall (that returns
	something that looks like it's coming from a dbapi2 cursor) or
	through getRecords (which returns dictionaries).
	"""
	def __init__(self, recordDef):
		self.recordDef = recordDef
		self.indexDict = dict([(field.get_dest(), index) 
			for index, field in enumerate(recordDef.get_items())])
		self.recordWidth = max(self.indexDict.values())+1
		self.data = []

	def getRecordDef(self):
		return self.recordDef

	def addData(self, record):
		self.data.append(record)
	
	def fetchall(self):
		res = []
		for rec in self.data:
			newRec = [None]*self.recordWidth
			for key, val in rec.iteritems():
				newRec[self.indexDict[key]] = val
			res.append(newRec)
		return res
	
	def getRecords(self):
		return self.data


def runChild(args, inputs):
	"""runs args[0] with args[1:] and input, returning its output in a
	string.
	
	args[0] is the full path to a program, args is a list of str-able command
	line arguments, and input is a list of inputs, with one sequence of
	str-able items per line.

	This won't work on non-Posix systems.  It's not very beautiful anyway,
	so maybe we'll want to revisit it at some point.
	"""
	os.chdir(os.path.dirname(args[0]))
	pipe = popen2.Popen3([str(a) for a in args])
	childOutput, childInput = pipe.fromchild, pipe.tochild
	fcntl.fcntl(childOutput.fileno(), fcntl.F_SETFL, os.O_NDELAY)
	outputItems = []
	inputs = iter(inputs)
	watchedInputs, watchedOutputs = [childOutput], [childInput]
	while True:
		try:
			rdReady, wrReady, _ = select.select(watchedInputs, watchedOutputs,
				[], 2)
			if rdReady:
				bytes = rdReady[0].read(1024)
				if bytes:
					outputItems.append(bytes)
				else:
					retval = (pipe.wait()&0xff00)>>8
					break
			if wrReady:
				line = " ".join([str(a) for a in inputs.next()])+"\n"
				childInput.write(line)
			retval = pipe.poll()
			if retval!=-1:
				break
		except StopIteration:
			childInput.flush()
			childInput.close()
			watchedOutputs = []
	if retval!=0:
		raise gavo.Error("Child signalled error %d"%retval)
	if watchedOutputs:
		raise gavo.Error("Child exited prematurely")
	return "".join(outputItems)


def parseAnswer(rawResult, outputService, verbose=False):
	data = DataCollector(outputService.getRecordDef())
	outputService.setHandlers(data)
	outputService.get_Grammar().parse(cStringIO.StringIO(rawResult))
	return data.fetchall()
