"""
Iterative parsing of XML documents.

This is basically like ElementTree's iterparse, except we don't
do anything fancy at all but instead push out character data in parcels.
"""

import traceback
import collections

from xml.parsers import expat

from gavo.votable import common

chunkSize = 2**20


class iterparse(object):
	"""iterates over start, data, and end events in source.

	Note that no namespace processing takes place here.
	"""
	def __init__(self, source):
		self.source = source
		self.parser = expat.ParserCreate()
		self.parser.buffer_text = True
		# We want ordered attributes for forcing attribute names to be
		# byte strings.
		self.parser.returns_unicode = True
		self.evBuf = collections.deque()
		self.parser.StartElementHandler = (lambda name, attrs, buf=self.evBuf: 
			buf.append(("start", name, attrs)))
		self.parser.EndElementHandler = (lambda name, buf=self.evBuf: 
			buf.append(("end", name)))
		self.parser.CharacterDataHandler = (lambda data, buf=self.evBuf:
			buf.append(("data", data)))

	def __iter__(self):
		return self

	def next(self):
		if not self.evBuf:
			try:
				nextChunk = self.source.read(chunkSize)
				if not nextChunk:
					self.close()
					raise StopIteration("File is empty")
				self.parser.Parse(nextChunk)
			except expat.ExpatError, ex:
				raise common.VOTableParseError(ex.message)
		return self.evBuf.popleft()

	def close(self):
		self.parser.Parse("", True)

	@property
	def pos(self):
		return (self.parser.CurrentLineNumber, self.parser.CurrentColumnNumber)

	def raiseParseError(self, msg):
		raise common.VOTableParseError("%s %s"%(msg,
			"near line %d, column %d"%self.pos))
