"""
Code to parse structures from XML sources.

The purpose of much of the mess here is to symmetrized XML attributes
and values.  Basically, we want start, value, end events whether
or not a piece of data comes in an element with a certain tag name or
via a named attribute.
"""

import re
from cStringIO import StringIO
from xml.sax import make_parser, SAXException
from xml.sax.handler import ContentHandler

from gavo import utils
from gavo.base import parsecontext
from gavo.base import structure
from gavo.utils import excs


ALL_WHITESPACE = re.compile("\s*$")


class ErrorPosition(object):
	"""A wrapper for an error position for use with utils.excs.

	Construct it with an SAX locator and a file like object.  None values
	are ok.
	"""
	def __init__(self, locator, fObject):
		self.line, self.col, self.srcName = "?", "?", "<internal>"
		if locator is not None:
			self.line = locator.getLineNumber() or '?' 
			self.col = locator.getColumnNumber() or '?'
		if fObject is not None and getattr(fObject, "name", None):
			self.srcName  = fObject.name
	
	def __str__(self):
		return "%s, line %s, col %s"%(self.srcName, self.line, self.col)


class Generator(structure.Parser):
	"""is an event generator created from python source code embedded
	in an XML element.
	"""
	def __init__(self, parent):
		nextParser = parent.curParser
		self.code = ""
		def start(ctx, name, value):
			raise StructureError("GENERATORs have no children")
		def value(ctx, name, value):
			if name!="content_":
				raise StructureError("GENERATORs have no children")
			self.code = parent.rootStruct.expand(("def gen():\n"+value).rstrip())
			return self
		def end(ctx, name, value):
			vals = {"context": ctx}
			try:
				exec self.code in vals
			except Exception, ex:
				raise common.logOldExc(BadCode(self.code, "GENERATOR", ex))
			for ev in vals["gen"]():
				if ev[0]=="element":
					self._expandElementEvent(ev, parent)
				elif ev[0]=="values":
					self._expandValuesEvent(ev, parent)
				else:
					parent.eventQueue.append(ev)
			return nextParser
		structure.Parser.__init__(self, start, value, end)
	
	def _expandElementEvent(self, ev, parent):
		parent.eventQueue.append(("start", ev[1]))
		for key, val in ev[2:]:
			parent.eventQueue.append(("value", key, val))
		parent.eventQueue.append(("end", ev[1]))

	def _expandValuesEvent(self, ev, parent):
		for key, val in ev[1:]:
			parent.eventQueue.append(("value", key, val))


class EventProcessor(object):
	"""A dispatcher for parse events to structures.

	It is constructed with the root structure of the result tree, either
	as a type or as an instance.

	After that, events can be fed to the feed method that makes sure
	they are routed to the proper object.
	"""

# The event processor distinguishes between parsing atoms (just one
# value) and structured data using the next attribute.  If it is not
# None, the next value coming in will be turned to a "value" event
# on the current parser.  If it is None, we hand through the event
# to the current structure.

	def __init__(self, rootStruct, ctx):
		self.rootStruct = rootStruct
		self.curParser, self.next = self._parse, None
		self.result, self.ctx = None, ctx
		# a queue of events to replay after the current structured
		# element has been processed
		self.eventQueue = []

	def _processEventQueue(self):
		while self.eventQueue:
			self.feed(*self.eventQueue.pop(0))

	def _feedToAtom(self, type, name, value):
		if type=='start':
			raise structure.StructureError("%s elements cannot have %s children"%(
				self.next, name))
		elif type=='value' or type=="parsedvalue":
			self.curParser(self.ctx, 'value', self.next, value)
		elif type=='end':
			self.next = None

	def _feedToStructured(self, type, name, value):
		next = self.curParser(self.ctx, type, name, value)
		if isinstance(next, basestring):
			self.next = next
		else:
			self.curParser = next
		if type=="end":
			self._processEventQueue()

	def feed(self, type, name, value=None):
		"""feeds an event.

		This is the main entry point for user calls.
		"""
		if type=="start" and name=="GENERATOR":
			self.curParser = Generator(self)
			return
		try:
			if self.next is None:
				self._feedToStructured(type, name, value)
			else:
				self._feedToAtom(type, name, value)
		except structure.ChangeParser, ex:
			self.curParser = ex.newParser
	
	def _parse(self, ctx, evType, name, value):
		"""dispatches an event to the root structure.

		Do not call this yourself unless you know what you're doing.  The
		method to feed "real" events to is feed.
		"""
		if name!=self.rootStruct.name_:
			raise structure.StructureError("Expected root element %s, found %s"%(
				self.rootStruct.name_, name))
		if evType=="start":
			if isinstance(self.rootStruct, type):
				self.result = self.rootStruct(None)
			else:
				self.result = self.rootStruct
			self.result.idmap = ctx.idmap
			return self.result.feedEvent
		else:
			raise structure.StructureError("Bad document structure")
	
	def setRoot(self, root):
		"""artifically inserts an instanciated root element.

		This is only required in odd cases like structure.feedFrom
		"""
		self.result = root
		self.curParser = root.feedEvent
		self.result.idmap = self.ctx.idmap
	

def _synthesizeAttributeEvents(evProc, context, attrs):
	"""generates value events for the attributes in attrs.
	"""
	# original attributes must be fed first since they will ususally
	# yield a different target object
	original = attrs.pop("original", None)
	if original:
		evProc.feed("value", "original", original)

# XXX TODO: Remove the ref mess soon.
	ref = attrs.pop("ref", None)
	if ref:
		evProc.feed("value", "ref", ref)
#		raise excs.Error("The ref attribute was a bad error.")
	for key, val in attrs.iteritems():
		evProc.feed("value", key, val)


def parseFromStream(rootStruct, inputStream, context=None):
	"""parses a tree rooted in rootStruct from some file-like object inputStream.

	It returns the root element of the resulting tree.  If rootStruct is
	a type subclass, it will be instanciated to create a root
	element, if it is an instance, this instance will be the root.
	"""
	if context is None:
		context = parsecontext.ParseContext()
	evProc = EventProcessor(rootStruct, context)
	eventSource = utils.iterparse(inputStream)
	buf = []

	try:
		for type, name, payload in eventSource:

			# buffer data
			if type=="data":
				buf.append(payload)
				continue
			else:
				if buf:
					res = "".join(buf)
					if not ALL_WHITESPACE.match(res):
						evProc.feed("value", "content_", res)
				buf = []

			# "normal" event feed
			evProc.feed(type, name, payload)

			# start event: Synthesize value events for attributes.
			if type=="start" and payload:  
				_synthesizeAttributeEvents(evProc, context, payload)
				payload = None
	except Exception, ex:
		if (not getattr(ex, "posInMsg", False) 
				and getattr(ex, "pos", None) is None):
			# only add pos when the message string does not already have it.
			ex.pos = eventSource.pos
			ex.posInMsg = True
		raise

	return evProc.result


def parseFromString(rootStruct, inputString, context=None):
	"""parses a tree rooted in rootStruct from a string.

	It returns the root element of the resulting tree.
	"""
	return parseFromStream(rootStruct, StringIO(inputString), context)
