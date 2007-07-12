"""
The main entry point to the masquerator.
"""

import os
import sys
import popen2
import select
import fcntl
import itertools
import re
import urllib
import cStringIO

import gavo
from gavo import utils
from gavo import nullui
from gavo.datadef import DataField
from gavo.parsing import grammar
from gavo.parsing import resource
from gavo.parsing import importparser

from gavo.web import common
from gavo.web import querulator
from gavo.web.querulator import forms
from gavo.web.querulator import queryrun


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


class ContextKey(utils.Record):
	"""is a key for a ContextGrammar.

	Both docKeys and rowKeys are modelled by this class.
	"""
	def __init__(self, initvals):
		utils.Record.__init__(self, {
				"label": None,      # Human-readable label for display purposes
				"widgetHint": None, # Hint for building a widget
				"type": "real",     # The type of this key
				"name": utils.RequiredField, # the "preterminal" we provide
				"default": "",    # a string containing a proper default value
			}, initvals)

	def asHtml(self, context):
		return ('<div class="condition"><div class="clabel">%s</div>'
			' <div class="quwidget"><input type="text" name="%s"'
			' value="%s"></div></div>'%(
				self.get_label(),
				self.get_name(), 
				urllib.quote(self.get_default())))


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
		names = [k.get_name() for k in self.get_rowKeys()]
		inputs = [self.inputFile.getlist(name) 
			for name in names]
		baseLen = len(inputs[0])
		if sum([abs(len(i)-baseLen) for i in inputs]):
			raise gavo.Error("Input sequences have unequal lengths")
		for tuple in itertools.izip(*inputs):
			yield dict(itertools.izip(names, tuple))
	
	def _getDocumentRow(self):
		docdict = {}
		for key in self.get_docKeys():
			docdict[key.get_name()] = self.inputFile.getfirst(key.get_name())
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
	def __init__(self, descriptor, serviceName):
		self.descriptor = descriptor
		self.serviceName = serviceName
		self.computer = descriptor.get_computer()
		self.inputDesc = descriptor.getDataById(self.serviceName)
		self.recordDef = self.inputDesc.get_Semantics(
			).getRecordDefByName("default")

	def getRecordDef(self):
		return self.recordDef

	def getItemdefs(self):
		return [{"name": field.get_dest(), "title": field.get_tablehead() or
				field.get_dest(), "hint": ["string"]}
			for field in self.getRecordDef().get_items()]

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
# NASTY -- not thread safe.  Improve changing setHandler's signature
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

	def getFormItems(self, context):
		allFields = (self.inputDesc.get_Grammar().get_docKeys()+
			self.inputDesc.get_Grammar().get_rowKeys())
		return "\n".join([field.asHtml(context)
			for field in allFields])

	def asHtml(self, serviceLocation, context):
		"""returns HTML for a from querying this service.
		"""
		return ('<form action="%(serviceLocation)s"'
			' method="get" class="masquerator">%(form)s'
			' %(submitButtons)s</form>'
			)%{
				"serviceLocation": serviceLocation,
				"form": self.getFormItems(context),
				"submitButtons": common.getSubmitButtons(),
				}


class ServiceDescriptor(importparser.ResourceDescriptor):
	def __init__(self):
		importparser.ResourceDescriptor.__init__(self)
		self._extendFields({
			"computer": utils.RequiredField,
		})


class ServiceDescriptorParser(importparser.RdParser):
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
		if name=="docKey":
			adder = self.curGrammar.addto_docKeys
		elif name=="rowKey":
			adder = self.curGrammar.addto_rowKeys
		else:
			raise gavo.Error("Unknown key type: %s"%name)
		adder(ContextKey({"label": attrs.get("label"),
			"widgetHint": attrs.get("widgetHint"),
			"default": attrs.get("default", ""),
			"name": content.strip()}))

	_end_rowKey = _end_docKey


def parseServiceDescriptor(srcFile):
	return importparser.getRd(srcFile, ServiceDescriptorParser)


class RecordBuilder:
	"""is a class that makes stuff that looks like it's coming from
	a dbapi2 reader from records from our parsing infrastructure.
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
		newRec = [None]*self.recordWidth
		for key, val in record.iteritems():
			newRec[self.indexDict[key]] = val
		self.data.append(newRec)
	
	def getData(self):
		return self.data


class ServiceTemplate(forms.AbstractTemplate):
	"""is a template for a service collection.

	The context passed at construction time is only used for resolving
	paths -- you can later pass in different ones.
	"""
	servicePat = re.compile(r"<\?service\s+(\w+)\s*\?>")

	def __init__(self, templatePath, context):
		self.path = templatePath
		forms.AbstractTemplate.__init__(self, 
			querulator.resolvePath(context.getEnv("MASQ_TPL_ROOT"), templatePath))
		self._parseServices(context)
	
	def getPath(self):
		return self.path
	
	def _parseServices(self, context):
		self.descriptor = parseServiceDescriptor(querulator.resolvePath(
			context.getEnv("GAVO_HOME"), self.getMeta("DESCRIPTOR")))

	def _handlePrivateElements(self, src, context):
		locationTpl = "%s/masqrun/%s/%%s"%(context.getEnv("ROOT_URL"),
			self.getPath())
		return self.servicePat.sub(lambda mat: 
				Service(self.descriptor, mat.group(1)).asHtml(
					locationTpl%mat.group(1), context), 
			src)

	def _parseAnswer(self, rawResult):
# XXX TODO: pull into Service
		reader = Service(self.descriptor, "output")
		data = RecordBuilder(reader.getRecordDef())
		reader.inputDesc.setHandlers(data)
		reader.inputDesc.get_Grammar().parse(cStringIO.StringIO(rawResult))
		return data.getData()

	def runQuery(self, context):
		# NASTY -- not thread-safe -- we'll probably want to insert
		# another class in here and have that passed by processMasqQuery
# but let's first see if we need curService at all.
		self.curService = Service(self.descriptor,
			context.getfirst("masq_service"))
		return self._parseAnswer(self.curService.run(context))

	def getDefaultTable(self):
		return "%s.%s"%(self.descriptor.get_schema(), 
			self.curService.serviceName)

	def getHiddenForm(self, context):
		return None

	def getProductCol(self):
		return None
	
	def getItemdefs(self):
		return Service(self.descriptor, "output").getItemdefs()

	def getConditionsAsText(self, context):
		return []


def getMasqForm(context, subPath):
	tpl = ServiceTemplate(subPath, context)
	return "text/html", tpl.asHtml(context), {}


def processMasqQuery(context, subPath):
	subPath = subPath.rstrip("/")
	context.addArgument("masq_service", os.path.basename(subPath))
	tpl = ServiceTemplate(os.path.dirname(subPath), context)
	return queryrun.processQuery(tpl, context)

if __name__=="__main__":
#	service = Service(parseService("/auto/gavo/inputs/apfs/res/apfs_dyn", 
#		"single"))
	from gavo.web.querulator import context
	ctx = context.DebugContext(args={"alpha": 219.90206583333332,
		"delta": -60.833974722222223,	"mu_alpha": -3678.08, 
		"mu_delta": 482.87, "parallax": 0.742, "rv": -21.6,
		"year": 2008, "month": 10, "day": 5, "hour": 3})
	tpl = ServiceTemplate("apfs.cq", ctx)
	print tpl.asHtml(ctx)
