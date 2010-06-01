"""
A simplified SAX content handler.

This is mainly for client code or non-DC XML parsing.
"""

import weakref
import xml.sax
from xml.sax.handler import ContentHandler


class StartEndHandler(ContentHandler):
	"""This class provides startElement, endElement and characters
	methods that translate events into method calls.

	When an opening tag is seen, we look of a _start_<element name>
	method and, if present, call it with the name and the attributes. 
	When a closing tag is seen, we try to call _end_<element name> with
	name, attributes and contents.	If the _end_xxx method returns a
	string (or similar), this value will be added to the content of the
	enclosing element.
	"""
	def __init__(self):
		ContentHandler.__init__(self)
		self.realHandler = weakref.proxy(self)
		self.elementStack = []
		self.contentsStack = [[]]

	def processingInstruction(self, target, data):
		self.contentsStack[-1].append(data)

	def cleanupName(self, name):
		return name.split(":")[-1].replace("-", "_")

	def startElement(self, name, attrs):
		self.contentsStack.append([])
		name = self.cleanupName(name)
		self.elementStack.append((name, attrs))
		if hasattr(self.realHandler, "_start_%s"%name):
			getattr(self.realHandler, "_start_%s"%name)(name, attrs)
		elif hasattr(self, "_defaultStart"):
			self._defaultStart(name, attrs)

	def endElement(self, name, suppress=False):
		contents = "".join(self.contentsStack.pop())
		name = self.cleanupName(name)
		_, attrs = self.elementStack.pop()
		res = None
		if hasattr(self.realHandler, "_end_%s"%name):
			res = getattr(self.realHandler,
				"_end_%s"%name)(name, attrs, contents)
		elif hasattr(self, "_defaultEnd"):
			res = self._defaultEnd(name, attrs, contents)
		if isinstance(res, basestring) and not suppress:
			self.contentsStack[-1].append(res)

	def characters(self, chars):
		self.contentsStack[-1].append(chars)
	
	def getResult(self):
		return self.contentsStack[0][0]

	def getParentTag(self):
		if self.elementStack:
			return self.elementStack[-1][0]
	
	def parse(self, stream):
		xml.sax.parse(stream, self)
		return self
	
	def parseString(self, string):
		xml.sax.parseString(string, self)
		return self
	
	def getAttrsAsDict(self, attrs):
		"""returns attrs as received from SAX as a dictionary.

		The main selling point is that any namespace prefixes are removed from
		the attribute names.  Any prefixes on attrs remain, though.
		"""
		return dict((k.split(":")[-1], v) for k, v in attrs.items())
