"""
A special Resource Descriptor for web services.

We probably don't want this and should merge that stuff into the
paring resource descriptor -- that way, we could enter the defined
tables into the meta data table, etc.

It may also come in handy when we want to support free-form SQL queries.
"""


from gavo import record
from gavo import parsing
from gavo.parsing import importparser
import contextgrammar

class ServiceDescriptor(importparser.ResourceDescriptor):
	def __init__(self):
		importparser.ResourceDescriptor.__init__(self)
		self._extendFields({
			"computer": record.RequiredField,
		})


class ServiceDescriptorParser(importparser.RdParser):
	"""is an xml.sax content handler to parse service resource descriptors.

	Unfortunately, we have to mush around in RdParser's guts for quite
	a bit.  A well, it's not worth abstracting out what we need to know
	for RdParser's innards for now.
	"""
	def _start_ResourceDescriptor (self, name, attrs):
		self.rd = ServiceDescriptor()
		self.rd.set_resdir(attrs["srcdir"])

	def _end_computer(self, name, attrs, content):
		self.rd.set_computer(content.strip())

	def _start_ContextGrammar(self, name, attrs):
		self._startGrammar(contextgrammar.ContextGrammar, attrs)

	_end_ContextGrammar = importparser.RdParser._endGrammar

	def _end_docKey(self, name, attrs, content):
		if name=="docKey":
			adder = self.curGrammar.addto_docKeys
		elif name=="rowKey":
			adder = self.curGrammar.addto_rowKeys
		else:
			raise gavo.Error("Unknown key type: %s"%name)
		adder(contextgrammar.ContextKey({"label": attrs.get("label"),
			"widgetHint": attrs.get("widgetHint"),
			"condgen": attrs.get("condgen"),
			"default": attrs.get("default", ""),
			"name": content.strip()}))

	_end_rowKey = _end_docKey


def parseServiceDescriptor(srcFile):
#	parsing.verbose = True
	return importparser.getRd(srcFile, ServiceDescriptorParser)

if __name__=="__main__":
	parseServiceDescriptor("/auto/gavo/inputs/apfs/res/apfs_dyn.vord")
