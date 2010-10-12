"""
Active tags are used in prepare and insert computed material into RD trees.

And, ok, we are dealing with elements here rather than tags, but I liked
the name "active tags" much better, and there's too much talk of elements
in this source as it is.
"""

from gavo import utils
from gavo.base import structure


class ActiveTag(structure.Parser):
	"""The base class for active tags.

	All active tags are constructed with a parse context and a parser
	class that is to take over on this element's end tag.

	The input events are passed in through the feedEvent(type, name, value)
	function.
	"""
	name_ = None

	def __init__(self, ctx, prevParser):
		self.ctx, self.prevParser = ctx, prevParser


class EventStream(ActiveTag):
	"""An active tag that records events as they come in.

	Their only direct effect is to leave a trace in the parser's id map.
	The resulting event stream can be played back later.
	"""
	name_ = "STREAM"

	def __init__(self, *args):
		ActiveTag.__init__(self, *args)
		self.events = []
		self.id = None
	
	def start_(self, ctx, name, value):
		self.events.append(("start", name, value, ctx.pos))
		return self

	def end_(self, ctx, name, value):
		if name==self.name_:
			res = self.prevParser
			self.ctx, self.prevParser = None, None
			return res
		else:
			self.events.append(("end", name, value, ctx.pos))
			return self
	
	def value_(self, ctx, name, value):
		if name=="id":
			self.id = value
			self.ctx.registerId(self.id, self)
		else:
			self.events.append(("value", name, value, ctx.pos))
		return self


getActiveTag = utils.buildClassResolver(ActiveTag, globals().values(),
	key=lambda obj: getattr(obj, "name_", None))


def isActive(name):
	return name in getActiveTag.registry
