"""
Code to parse structures from XML sources.
"""

from cStringIO import StringIO
from xml.sax import make_parser, SAXException
from xml.sax.handler import ContentHandler

from gavo.base import excs
from gavo.base import parsecontext
from gavo.base import structure


class NodeBuilder(ContentHandler):
	"""is a SAX content handler interfacing to the structure.EventProcessor.
	"""
	# These are attributes that may not occur in elements and are always
	# processed first.  See original/parsecontext.OriginalAttribute as to why 
	# we need this hack.
	specialAttributes = set(["original", "ref"])
	
	# These are elements for which character content is not stripped
	# XXX TODO: figure out how to let structures tell NodeBuilder about those
	preserveWhitespaceNames = set(["meta", "script", "proc", "rowgen",
		"consComp", "customRF", "macDef", "GENERATOR", "formatter"])

	def __init__(self, evProc):
		ContentHandler.__init__(self)
		self.elementsById = {}
		self.charData = []
		self.evProc = evProc
		self.nameStack = [None]
		self.locator = None
	
	def setDocumentLocator(self, locator):
		self.locator = locator

	def startElement(self, name, attrs):
		if name in self.specialAttributes:
			raise structure.StructureError("%s is only allowed as an attribute"%
				name)
		self._deliverCharData(self.nameStack[-1])
		self.nameStack.append(name)
		self.evProc.feed("start", name)
		for n in attrs.keys():
			if n in self.specialAttributes:
				self.evProc.feed("value", n, attrs[n])
		for key, val in attrs.items():
			if key not in self.specialAttributes:
				self.evProc.feed("value", key, val)

	def _deliverCharData(self, name):
		if self.charData:
			cd = "".join(self.charData)
			if name not in self.preserveWhitespaceNames:
				cd = cd.strip()
			if cd:
				self.evProc.feed("value", "content_", cd)
			self.charData = []

	def endElement(self, name):
		self.evProc.notifyPosition(self.locator.getLineNumber(), 
			self.locator.getColumnNumber())
		self._deliverCharData(name)
		self.nameStack.pop()
		self.evProc.feed("end", name)
	
	def characters(self, chars):
		self.charData.append(chars)


def parseFromStream(rootStruct, inputStream, context=None):
	"""parses a tree rooted in rootStruct from some file-like object inputStream.

	It returns the root element of the resulting tree.  If rootStruct is
	a type subclass, it will be instanciated to create a root
	element, if it is an instance, this instance will be the root.
	"""
	parser = make_parser()
	if context is None:
		context = parsecontext.ParseContext()
	evProc = structure.EventProcessor(rootStruct, context)
	cHandler = NodeBuilder(evProc)
	if context is not None:
		context.parser = cHandler
	parser.setContentHandler(cHandler)
	try:
		parser.parse(inputStream)
	except SAXException, msg:
		raise excs.ReportableError("Bad XML: %s"%unicode(msg))
	return evProc.result


def parseFromString(rootStruct, inputString, context=None):
	"""parses a tree rooted in rootStruct from a string.

	It returns the root element of the resulting tree.
	"""
	return parseFromStream(rootStruct, StringIO(inputString), context)
