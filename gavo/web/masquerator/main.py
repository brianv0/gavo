"""
The main entry point to the masquerator.
"""

import os
import popen2
import select
import fcntl
import itertools

import gavo
from gavo import utils
from gavo import nullui
from gavo.datadef import DataField
from gavo.parsing import grammar
from gavo.parsing import resource
from gavo.parsing import importparser

from gavo.web.querulator import context

def runChild(childName, args, inputs):
	"""runs childName with args and input, returning its output in a
	string.
	
	childName is the name of a program, args is a list of str-able command
	line arguments, and input is a list of inputs, with one sequence of
	str-able items per line.

	This won't work on non-Posix systems.  It's not very beautiful anyway,
	so maybe we'll want to revisit it at some point.
	"""
	os.chdir(os.path.dirname(childName))
	pipe = popen2.Popen3(
		[childName]+[str(a) for a in args])
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


class ContextGrammar(grammar.Grammar):
	"""is a grammar that gets values from a context.

	It has docKeys that will be packed into a dictionary and handed over
	to a documentHandler, and rowKeys that will be packed into a dictionary
	and handed over to a row handler.

	For docKeys, only the first value in the context will be used, while
	for rowKeys the lists will be iterated over (they must all have the
	same length, though).  Usually, however, the rowKeys will be expanded
	by row processors.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"docKeys": utils.ListField,
			"rowKeys": utils.ListField,
		})

	def _iterRows(self):
		inputs = [self.inputFile.getlist(key) for key in self.get_rowKeys()]
		baseLen = len(inputs[0])
		if sum([abs(len(i)-baseLen) for i in inputs]):
			raise gavo.Error("Input sequences have unequal lengths")
		names = self.get_rowKeys()
		for tuple in itertools.izip(*inputs):
			yield dict(itertools.izip(names, tuple))
	
	def _getDocumentRow(self):
		docdict = {}
		for key in self.get_docKeys():
			docdict[key] = self.inputFile.getfirst(key)
		return docdict
	
	def parse(self, context):
		self.curInputFileName = "<Context>"
		self.inputFile = context
		self._parse(None)
		self.inputFile = None
		self.curInputFileName = None


class Service:
	"""is a model for a service.

	The service consists of a computer and specifications of
	the inputs (an InputSpec instance) and the outputs (an
	OutputSpecInstance).

	The computer may name an executable or be a callable; if it's a
	callable, it has to accept a list of global arguments and a list
	containing row arguments, one set per line; they currently have
	to return their results in a string, one row per line (you'll
	want to change this when you need it).

	A service satisfies the the table protocol, i.e. it can stand
	in as a table in a parsing.importparser.DataDescriptor.
	"""
	def __init__(self, descriptor):
		self.descriptor = descriptor
		self.computer = descriptor.get_computer()
		self.inputDesc = descriptor.getDataById("input")
		self.inputRecordDef = self.inputDesc.get_Semantics(
			).getRecordDefByName("input")

	def getRecordDef(self):
		return self.inputRecordDef

	def addData(self, rowdict):
		args = [(int(ct), val) for ct, val in rowdict.iteritems()]
		args.sort()
		self.inputs.append([val for ct, val in args])

	def _makeArguments(self):
		self.inputDesc.validate(self.rb.getDocRec())
		args = [(int(ct), val) for ct, val in self.rb.getDocRec().items()]
		args.sort()
		return [val for ct, val in args]

	def run(self, context):
		"""runs the computer with the arguments and inputs specified in context
		and returns the result(s) in a list of records.

		context is a gavo.web.context instance.

		The records are dictionaries mapping the names defined in OutputSpec
		to their values.
		"""
		self.rb = self.inputDesc.setHandlers(self)
# Nasty -- not thread safe.  Improve changing setHandler's signature
# or some other nice trick.
		self.inputs = []
		self.inputDesc.get_Grammar().parse(context)
		args = self._makeArguments()
		computer = self.descriptor.get_computer()
		try:
			if isinstance(computer, basestring):
				return runChild(computer, args, self.inputs)
			else:
				return computer(args, self.inputs)
		except Exception, msg:
			import traceback
			traceback.print_exc()
			raise gavo.Error("Service computer %s failed (%s)"%(computer,
				msg))


class ServiceDescriptor(importparser.ResourceDescriptor):
	def __init__(self):
		importparser.ResourceDescriptor.__init__(self)
		self._extendFields({
			"computer": utils.RequiredField,
		})


class ServiceParser(importparser.RdParser):
	"""is an xml.sax content handler to parse service resource descriptors.

	Unfortunately, we have to mush around in RdParser's guts for quite
	a bit.  A well, it's not worth abstracting out what we need to know
	for RdParser's innards for now.
	"""
	def _start_ServiceDescriptor (self, name, attrs):
		self.rd = ServiceDescriptor()
		self.rd.set_resdir(attrs["srcdir"])

	def _start_ResourceDescriptor(self, name, attrs):
		raise gavo.Error("Service parsers don't parse Resource Descriptors")

	def _end_computer(self, name, attrs, content):
		self.rd.set_computer(content.strip())

	def _start_ContextGrammar(self, name, attrs):
		self._startGrammar(ContextGrammar, attrs)
		self.curGrammar = ContextGrammar()
		self.dataSrcStack[-1].set_Grammar(self.curGrammar)
		self.macroContainerStack.append(self.curGrammar)

	_end_ContextGrammar = importparser.RdParser._endGrammar

	def _end_docKey(self, name, attrs, content):
		self.curGrammar.addto_docKeys(content.strip())

	def _end_rowKey(self, name, attrs, content):
		self.curGrammar.addto_rowKeys(content.strip())


def parseService(srcFile):
	return importparser.getRd(srcFile, ServiceParser)


service = Service(parseService("/auto/gavo/inputs/apfs/res/apfs_dyn"))
ctx = context.DebugContext(args={"alpha": 219.90206583333332,
	"delta": -60.833974722222223,	"mu_alpha": -3678.08, 
	"mu_delta": 482.87, "parallax": 0.742, "rv": -21.6
	"year": 2008, "month": 10, "day": 5, "hour": 3})
print service.run(ctx)
