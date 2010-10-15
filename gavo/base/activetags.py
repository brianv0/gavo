"""
Active tags are used in prepare and insert computed material into RD trees.

And, ok, we are dealing with elements here rather than tags, but I liked
the name "active tags" much better, and there's too much talk of elements
in this source as it is.
"""

import csv
from cStringIO import StringIO

from gavo import utils
from gavo.base import attrdef
from gavo.base import macros
from gavo.base import structure
from gavo.utils import excs


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
	_doc = attrdef.UnicodeAttribute("doc", description="A description of"
		" this stream (should be restructured text).")

	def __init__(self, *args, **kwargs):
		self.events = []
		self.tagStack = []
		ActiveTag.__init__(self, *args, **kwargs)

	def start_(self, ctx, name, value):
		if name in self.managedAttrs and not self.tagStack:
			res = ActiveTag.start_(self, ctx, name, value)
		else:
			self.events.append(("start", name, value, ctx.pos))
			res = self
			self.tagStack.append(name)
		return res

	def end_(self, ctx, name, value):
		if not self.tagStack: # end of STREAM element
			res = self.parent
			self.parent = None
			return res
		self.tagStack.pop()
		if name in self.managedAttrs:
			ActiveTag.end_(self, ctx, name, value)
		else:
			self.events.append(("end", name, value, ctx.pos))
		return self
	
	def value_(self, ctx, name, value):
		if name in self.managedAttrs and not self.tagStack:
			# our attribute
			ActiveTag.value_(self, ctx, name, value)
		else:
			self.events.append(("value", name, value, ctx.pos))
		return self


class ReplayedEvents(ActiveTag, macros.MacroPackage):
	"""An active tag that takes an event stream and replays the events,
	possibly filling variables.

	This element supports arbitrary attributes with unicode values.  These
	values are available as macros for replayed values.
	"""
	name_ = "FEED"

	_source = attrdef.ActionAttribute("source", "_setupReplay",
		description="id of a stream to replay")

	def __init__(*args, **kwargs):
		ActiveTag.__init__(*args, **kwargs)

	def completeElement(self):
		self._completeElementNext(ReplayedEvents)
		if not hasattr(self, "_replayer"):
			raise excs.StructureError("FEED elements need a source attribute")
		self._replayer()

	def _setupReplay(self, ctx):
		def replayer():
			stream = ctx.getById(self.source)
			evTarget = self.evproc_.clone()
			evTarget.setRoot(self.parent)
			for type, name, val, pos in stream.events:
				if type=="value" and "\\" in val:
					try:
						val = self.expand(val)
					except macros.MacroError, ex:
						ex.hint = ("This probably means that you should have set a %s"
							" attribute in the FEED tag.  For details see the"
							" documentation of the %s STREAM."%(
								ex.macroName,
								self.source))
						raise
				try:
					evTarget.feed(type, name, val)
				except Exception, msg:
					msg.pos = "%s (replaying, real error position %s)"%(
						ctx.pos, pos)
					raise
		self._replayer = replayer
	
	def getDynamicAttribute(self, name):
		def m():
			return getattr(self, name)
		setattr(self, "macro_"+name, m)
		# crazy hack: Since all our peudo attributes are atomic, we do not
		# enter them into managedAttributes.  Actually, we *must not* do
		# so (for now) since managedAttributes is a *class* attribute
		# and entering something there would keep getDynamicAttribute
		# from being called for a second instance.  That instance would
		# then not receive the macro_X method an thus fail.
		newAtt = attrdef.UnicodeAttribute(name)
		return newAtt


class Loop(ReplayedEvents):
	"""An active tag that replays a feed several times, each time with
	different values.
	"""
	name_ = "LOOP"

	_csvItems = attrdef.UnicodeAttribute("csvItems", default=utils.Undefined,
		description="The items to loop over, in CSV-with-labels format.",
		strip=True)

	def completeElement(self):
		# No upcall here since I don't want ReplayedEvents' completeElement to
		# run here.
		if not hasattr(self, "_replayer"):
			raise excs.StructureError("LOOP elements need a source attribute")
		csvItems = csv.DictReader(StringIO(self.csvItems.encode("utf-8")))
		for row in csvItems:
			for name, value in row.iteritems():
				setattr(self, "macro_"+name, lambda v=value: v.strip())
			self._replayer()

			

getActiveTag = utils.buildClassResolver(ActiveTag, globals().values(),
	key=lambda obj: getattr(obj, "name_", None))


def isActive(name):
	return name in getActiveTag.registry
