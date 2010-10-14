"""
Active tags are used in prepare and insert computed material into RD trees.

And, ok, we are dealing with elements here rather than tags, but I liked
the name "active tags" much better, and there's too much talk of elements
in this source as it is.
"""

from gavo import utils
from gavo.base import attrdef
from gavo.base import structure


class EvprocAttribute(attrdef.AtomicAttribute):
	def __init__(self):
		attrdef.AtomicAttribute.__init__(self, "evproc_", 
			default=utils.Undefined,
			description="Used internally, do not attempt to set (you can't).")
	
	def feedObject(self, instance, value):
		instance.evproc_ = value


class ActiveTag(structure.Structure):
	"""The base class for active tags.

	All active tags are constructed with a parse context and a parser
	class that is to take over on this element's end tag.

	The input events are passed in through the feedEvent(type, name, value)
	function.
	"""
	name_ = None
	
	_evproc = EvprocAttribute()
	
	def onElementComplete(self):
		# All active tags are "ghostly", i.e., the do not (directly)
		# show up in their parents.  Therefore, as a part of the wrap-up
		# of the new element, we raise an Ignore exception, which tells
		# the Structure's end_ method to not feed us to the parent.
		self._onElementCompleteNext(ActiveTag)
		self.evproc_ = None
		raise structure.Ignore(self)


class EventStream(ActiveTag):
	"""An active tag that records events as they come in.

	Their only direct effect is to leave a trace in the parser's id map.
	The resulting event stream can be played back later.
	"""
	# Warning: Attributes defined here will be ignored -- structure parsing
	# is not in effect for EventStream.
	name_ = "STREAM"

	def __init__(self, *args, **kwargs):
		self.events = []
		self.inRoot = True
		ActiveTag.__init__(self, *args, **kwargs)

	def start_(self, ctx, name, value):
		self.inRoot = False
		self.events.append(("start", name, value, ctx.pos))
		return self

	def end_(self, ctx, name, value):
		if name==self.name_:
			res = self.parent
			self.parent = None, None
			return res
		else:
			self.events.append(("end", name, value, ctx.pos))
			return self
	
	def value_(self, ctx, name, value):
		if self.inRoot and name=="id":
			self.id = value
			ctx.registerId(self.id, self)
		else:
			self.events.append(("value", name, value, ctx.pos))
		return self


class ReplayedEvents(ActiveTag):
	"""An active tag that takes an event stream and replays the events,
	possibly filling variables.
	"""
	name_ = "FEED"

	_source = attrdef.ActionAttribute("source", "_replayStream",
		description="id of a stream to replay")

	def _replayStream(self, ctx):
		stream = ctx.getById(self.source)
		evTarget = self.evproc_.clone()
		evTarget.setRoot(self.parent)
		for type, name, val, pos in stream.events:
			evTarget.feed(type, name, val)
	

getActiveTag = utils.buildClassResolver(ActiveTag, globals().values(),
	key=lambda obj: getattr(obj, "name_", None))


def isActive(name):
	return name in getActiveTag.registry
