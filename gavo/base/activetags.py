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
from gavo.base import common
from gavo.base import complexattrs
from gavo.base import macros
from gavo.base import parsecontext
from gavo.base import structure


# the following is a sentinel for values that have been expanded
# by an active tag already.  When active tags are nested, only the
# innermost must expand macros so one can be sure that double-escaped
# macros actually end up at the top level.  _EXPANDED_VALUE must
# compare true to value since it is used as such in event triples.
class _ExValueType(object):
	def __str__(self):
		return "value"

	def __repr__(self):
		return "'value/expanded'"

	def __eq__(self, other):
		return other=="value"

	def __ne__(self, other):
		return not other=="value"

_EXPANDED_VALUE =_ExValueType()


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
		raise common.Ignore(self)


class Prune(ActiveTag):
	"""An active tag that lets you selectively delete children of the
	current object.

	You give it regular expression-valued attributes; the prune tag will then
	recurse through all list-style attributes (technically, all that have
	an iterChildren attribute) and remove all children that match the
	given condition(s).

	If you give more than one attribute, the result will be a conjunction
	of the specified conditions.

	Note that it usually doesn't make sense to match by id since ids do not 
	copy.
	"""
	name_ = "PRUNE"
	
	def __init__(self, parent, **kwargs):
		self.conds = {}
		ActiveTag.__init__(self, parent)

	def value_(self, ctx, name, value):
		self.conds[name] = value
		return self
	
	def end_(self, ctx, name, value):
		assert name==self.name_
		self.match = self._getMatcher()
		self._recurse(self.parent)
		return self.parent

	def _recurse(self, root):
		# this does a preorder traversal of root's children, pruning anything
		# for which self.match returns true
		if not root:
			return
		removals = []
		for attDef in root.attrSeq:
			if not hasattr(attDef, "iterChildren"):
				continue
			for child in attDef.iterChildren(root):
				if self.match(child):
					removals.append(lambda attDef=attDef, child=child:
						attDef.remove(child))
				else:
					self._recurse(child)
		
		for action in removals:
			action()

	def _getMatcher(self):
		conditions = []
		for attName, regEx in self.conds.iteritems():
			conditions.append((attName, re.compile(regEx)))

		def match(element):
			for attName, expr in conditions:
				val = getattr(element, attName, None)
				if val is None:  # not given or null empty attrs never match
					return False
				if not expr.search(val):
					return False
			return True

		return match
	

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

	def feedEvent(self, ctx, type, name, value):
		# keep _EXPANDED_VALUE rather than "value"
		if type is _EXPANDED_VALUE:
			self.events.append((_EXPANDED_VALUE, name, value, ctx.pos))
			return self
		else:
			return ActiveTag.feedEvent(self, ctx, type, name, value)

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

	# This lets us feedFrom these
	iterEvents = getEventSource


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
			raise common.LiteralParseError("ref", self.ref, 
				hint="edit references have the form <element name>[<value of"
					" name or id attribute>]")
		self.triggerEl, self.triggerId = mat.groups()
	

class ReplayBase(ActiveTag, macros.MacroPackage):
	"""An "abstract base" for active tags replaying streams.
	"""
	name_ = None  # not a usable active tag
	_expandMacros = True

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

	def _replayTo(self, events, evTarget, ctx):
		"""pushes stored events into an event processor.

		The public interface is replay (that receives a structure rather
		than an event processor).
		"""
		idStack = []
		
		for type, name, val, pos in events:
			if (self._expandMacros
					and type=="value" 
					and type is not _EXPANDED_VALUE 
					and "\\" in val):
				try:
					val = self.expand(val)
				except macros.MacroError, ex:
					ex.hint = ("This probably means that you should have set a %s"
						" attribute in the FEED tag.  For details see the"
						" documentation of the STREAM with id %s."%(
							ex.macroName,
							getattr(self.source, "id", "<embedded>")))
					raise
				type = _EXPANDED_VALUE

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
							ctx)

			try:
				evTarget.feed(type, name, val)
			except Exception, msg:
				msg.pos = "%s (replaying, real error position %s)"%(
					ctx.pos, pos)
				raise

	def replay(self, events, destination, ctx):
		"""pushes the stored events into the destination structure.

		While doing this, local macros are expanded unless we already
		receive the events from an active tag (e.g., nested streams
		and such).
		"""
		# XXX TODO: Circular import here.  Think again and resolve.
		from gavo.base.xmlstruct import EventProcessor
		evTarget = EventProcessor(None, ctx)
		evTarget.setRoot(destination)

		self._ensureEditsDict()
		self._replayTo(events, evTarget, ctx)


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
			raise common.StructureError("Need exactly one of source and events"
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

	def __init__(self, *args, **kwargs):
		DelayedReplayBase.__init__(self, *args, **kwargs)
		# managedAttrs in general is a class attribute.  Here, we want
		# to add values for the macros, and these are instance-local.
		self.managedAttrs = self.managedAttrs.copy()

	def completeElement(self):
		self._completeElementNext(ReplayedEvents)
		self._replayer()

	def getAttribute(self, name):
		try:
			return DelayedReplayBase.getAttribute(self, name)
		except common.StructureError: # no "real" attribute, it's a macro def
			def m():
				return getattr(self, name)
			setattr(self, "macro_"+name.strip(), m)
			self.managedAttrs[name] = attrdef.UnicodeAttribute(name)
			return self.managedAttrs[name]


class NonExpandedReplayedEvents(ReplayedEvents):
	"""A ReplayedEventStream that does not expand active tag macros.

	You only want this when embedding a stream into another stream
	that could want to expand the embedded macros.
	"""
	name_ = "LFEED"
	_expandMacros = False


class GeneratorAttribute(attrdef.UnicodeAttribute):
	"""An attribute containing a generator working on the parse context.
	"""
	def feed(self, ctx, instance, literal):
		if ctx.restricted:
			raise common.RestrictedElement("codeItems")
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
				raise common.StructureError("Must give exactly one data source in"
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
