"""
Active tags are used in prepare and insert computed material into RD trees.

And, ok, we are dealing with elements here rather than tags, but I liked
the name "active tags" much better, and there's too much talk of elements
in this source as it is.
"""

import csv
import re
from cStringIO import StringIO

from gavo import utils
from gavo.base import attrdef
from gavo.base import complexattrs
from gavo.base import macros
from gavo.base import parsecontext
from gavo.base import structure
from gavo.utils import excs


class ActiveTag(structure.Structure):
	"""The base class for active tags.
	"""
	name_ = None

	def _hasActiveParent(self):
		el = self.parent
		while el:
			if isinstance(el, ActiveTag):
				return True
			el = el.parent
		return False


class GhostMixin(object):
	"""A mixin to make a Structure ghostly.
	
	Most active tags are "ghostly", i.e., the do not (directly)
	show up in their parents.  Therefore, as a part of the wrap-up
	of the new element, we raise an Ignore exception, which tells
	the Structure's end_ method to not feed us to the parent.
	"""
	def onElementComplete(self):
		self._onElementCompleteNext(GhostMixin)
		raise structure.Ignore(self)


class _PreparedEventSource(object):
	"""An event source for xmlstruct.

	It is constructed with a list of events as recorded by classes
	inheriting from RecordingBase.
	"""
	def __init__(self, events):
		self.events = events
		self.curEvent = -1
		self.pos = None
	
	def __iter__(self):
		return _PreparedEventSource(self.events)
	
	def next(self):
		self.curEvent += 1
		try:
			nextItem = self.events[self.curEvent]
		except IndexError:
			raise StopIteration()
		res, self.pos = nextItem[:3], nextItem[-1]
		return res


class RecordingBase(ActiveTag):
	"""An "abstract base" for active tags doing event recording.

	The recorded events are available in the events attribute.
	"""
	name_ = None

	_doc = attrdef.UnicodeAttribute("doc", description="A description of"
		" this stream (should be restructured text).", strip=False)

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
	
	def getEventSource(self):
		"""returns an object suitable as event source in xmlstruct.
		"""
		return _PreparedEventSource(self.events)


class EventStream(RecordingBase, GhostMixin):
	"""An active tag that records events as they come in.

	Their only direct effect is to leave a trace in the parser's id map.
	The resulting event stream can be played back later.
	"""
	name_ = "STREAM"

	def end_(self, ctx, name, value):
		# keep self out of the parse tree
		if not self.tagStack: # end of STREAM element
			res = self.parent
			self.parent = None
			return res
		return RecordingBase.end_(self, ctx, name, value)


class EmbeddedStream(RecordingBase):
	"""An event stream as a child of another element.
	"""
	name_ = "events"  # Lower case since it's really a "normal" element that's
	                  # added into the parse tree.
	def end_(self, ctx, name, value):
		if not self.tagStack: # end of my element, do standard structure thing.
			return ActiveTag.end_(self, ctx, name, value)
		return RecordingBase.end_(self, ctx, name, value)


class Edit(EmbeddedStream):
	"""an event stream targeted at editing other structures.
	"""
	name_ = "EDIT"

	_ref = attrdef.UnicodeAttribute("ref", description="Destination of"
		" the edits, the form elementName[<name or id>]", default=utils.Undefined)

	refPat = re.compile(
		r"([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z_][A-Za-z0-9_]*)\]")

	def onElementComplete(self):
		mat = self.refPat.match(self.ref)
		if not mat:
			raise excs.LiteralParseError("ref", self.ref, 
				hint="edit references have the form <element name>[<value of"
					" name or id attribute>]")
		self.triggerEl, self.triggerId = mat.groups()
	

class ReplayBase(ActiveTag, macros.MacroPackage):
	"""An "abstract base" for active tags replaying streams.
	"""
	name_ = None  # not a usable active tag

	_source = parsecontext.ReferenceAttribute("source",
		description="id of a stream to replay", default=None)
	_events = complexattrs.StructAttribute("events",
		childFactory=EmbeddedStream, default=None,
		description="Alternatively to source, an XML fragment to be replayed")
	_edits = complexattrs.StructListAttribute("edits",
		childFactory=Edit, description="Changes to be performed on the"
		" events played back.")

	def _ensureEditsDict(self):
		if not hasattr(self, "editsDict"):
			self.editsDict = {}
			for edit in self.edits:
				self.editsDict[edit.triggerEl, edit.triggerId] = edit

	def _replayTo(self, events, evTarget, ctx, doExpansions):
		"""pushes stored events into an event processor.

		The public interface is replay (that receives a structure rather
		than an event processor).
		"""
		idStack = []
		
		for type, name, val, pos in events:
			if doExpansions and type=="value" and "\\" in val:
				try:
					val = self.expand(val)
				except macros.MacroError, ex:
					ex.hint = ("This probably means that you should have set a %s"
						" attribute in the FEED tag.  For details see the"
						" documentation of the STREAM with id %s."%(
							ex.macroName,
							getattr(self.source, "id", "<embedded>")))
					raise

			# the following mess is to notice when we should edit and
			# replay EDIT content when necessary
			if type=="start":
				idStack.append(set())
			elif type=="value":
				if name=="id" or name=="name":
					idStack[-1].add(val)
			elif type=="end":
				ids = idStack.pop()
				for foundId in ids:
					if (name, foundId) in self.editsDict:
						self._replayTo(self.editsDict[name, foundId].events,
							evTarget,
							ctx, doExpansions)

			try:
				evTarget.feed(type, name, val)
			except Exception, msg:
				msg.pos = "%s (replaying, real error position %s)"%(
					ctx.pos, pos)
				raise

	def replay(self, events, destination, ctx):
		"""pushes the stored events into the destination structure.

		While doing this, local macros are expanded.  There is a hack, though,
		in that we must not expand if we're (going to be) fed into anyother 
		replayer, since multiple expansions would foul up macros intended for 
		the element being played into.  Thus, we check if we have an active
		parent and suppress macro expansion if so.
		"""
		# XXX TODO: Circular import here.  Think again and resolve.
		from gavo.base.xmlstruct import EventProcessor
		evTarget = EventProcessor(None, ctx)
		evTarget.setRoot(destination)

		self._ensureEditsDict()
		doExpansions = not self._hasActiveParent()
		self._replayTo(events, evTarget, ctx, doExpansions)


class DelayedReplayBase(ReplayBase, GhostMixin):
	"""An base class for active tags wanting to replay streams from
	where the context is invisible.

	These define a _replayer attribute that, when called, replays
	the stored events *within the context at its end* and to the
	parent.

	This is what you want for the FEED and LOOP since they always work
	on the embedding element and, by virtue of being ghosts, cannot
	be copied.  If the element embedding an event stream can be
	copied, this will almost certainly not do what you want.
	"""
	def _setupReplay(self, ctx):
		sources = [s for s in [self.source, self.events] if s]
		if len(sources)!=1:
			raise excs.StructureError("Need exactly one of source and events"
				" on %s elements"%self.name_)
		stream = sources[0].events
		def replayer():
			self.replay(stream, self.parent, ctx)
		self._replayer = replayer

	def end_(self, ctx, name, value):
		self._setupReplay(ctx)
		return ActiveTag.end_(self, ctx, name, value)


class ReplayedEvents(DelayedReplayBase):
	"""An active tag that takes an event stream and replays the events,
	possibly filling variables.

	This element supports arbitrary attributes with unicode values.  These
	values are available as macros for replayed values.
	"""
	name_ = "FEED"

	def completeElement(self):
		self._completeElementNext(ReplayedEvents)
		self._replayer()

	def getDynamicAttribute(self, name):
		def m():
			return getattr(self, name)
		setattr(self, "macro_"+name.strip(), m)
		# crazy hack: Since all our peudo attributes are atomic, we do not
		# enter them into managedAttributes.  Actually, we *must not* do
		# so (for now) since managedAttributes is a *class* attribute
		# and entering something there would keep getDynamicAttribute
		# from being called for a second instance.  That instance would
		# then not receive the macro_X method an thus fail.
		newAtt = attrdef.UnicodeAttribute(name)
		return newAtt


class GeneratorAttribute(attrdef.UnicodeAttribute):
	"""An attribute containing a generator working on the parse context.
	"""
	def feed(self, ctx, instance, literal):
		if ctx.restricted:
			raise excs.RestrictedElement("codeItems")
		attrdef.UnicodeAttribute.feed(self, ctx, instance, literal)
		src = utils.fixIndentation(
			getattr(instance, self.name_), 
			"  ", governingLine=1)
		src = "def makeRows():\n"+src+"\n"
		instance.iterRowsFromCode = utils.compileFunction(
			src, "makeRows", useGlobals={"context": ctx})


class Loop(DelayedReplayBase):
	"""An active tag that replays a feed several times, each time with
	different values.
	"""
	name_ = "LOOP"

	_csvItems = attrdef.UnicodeAttribute("csvItems", default=None,
		description="The items to loop over, in CSV-with-labels format.",
		strip=True)
	_listItems = attrdef.UnicodeAttribute("listItems", default=None,
		description="The items to loop over, as space-separated single"
		" items.  Each item will show up once, as 'item' macro.",
		strip=True)
	_codeItems = GeneratorAttribute("codeItems", default=None,
		description="A python generator body that yields dictionaries"
		" that are then used as loop items.  You can access the parse context"
		" as the context variable in these code snippets.", strip=False)

	def maybeExpand(self, val):
		if "\\" in val:
			el = self.parent
			while el:
				if hasattr(el, "expand"):
					return el.expand(val)
				el = el.parent
		return val

	def _makeRowIteratorFromListItems(self):
		if self.listItems is None:
			return None
		def rowIterator():
			for item in self.maybeExpand(self.listItems).split():
				yield {"item": item}
		return rowIterator()
	
	def _makeRowIteratorFromCSV(self):
		if self.csvItems is None:
			return None
		# I'd rather not do the encode below, but 2.5 csv throws a weird
		# exception if I pass unicode strings...
		src = self.maybeExpand(self.csvItems).strip().encode("utf-8")
		return iter(csv.DictReader(StringIO(src), skipinitialspace=True))

	def _makeRowIteratorFromCode(self):
		if self.codeItems is None:
			return None
		return self.iterRowsFromCode()

	def _getRowIterator(self):
		rowIterators = [ri for ri in [
			self._makeRowIteratorFromListItems(),
			self._makeRowIteratorFromCSV(),
			self._makeRowIteratorFromCode()] if ri]
		if len(rowIterators)!=1:
				raise excs.StructureError("Must give exactly one data source in"
					" LOOP")
		return rowIterators[0]
			
	def completeElement(self):
		self._completeElementNext(Loop)
		for row in self._getRowIterator():
			for name, value in row.iteritems():
				if value:
					value = value.strip()
				setattr(self, "macro_"+name.strip(), lambda v=value: v)
			self._replayer()

			
getActiveTag = utils.buildClassResolver(ActiveTag, globals().values(),
	key=lambda obj: getattr(obj, "name_", None))


def registerActiveTag(activeTag):
	getActiveTag.registry[activeTag.name_] = activeTag


def isActive(name):
	return name in getActiveTag.registry
