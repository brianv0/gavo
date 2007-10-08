"""
Code dealing with meta information.

The meta information we deal with here is *not* column information (which
is handled in datadef.py) but information on tables, services and
resources as a whole.

In the context of gavo, meta information is associated with (at least)
ResourceDescriptors, DataTransformers, RecordDefs.

The resource descriptor is (usually) responsible to declare itself as the
meta parent to all other meta containers.
"""

import weakref
import re
import textwrap


class MetaItem:
	"""is a piece of meta information about a resource.

	The trouble with meta items is that they're used for so many things that
	you'd need a big infrastructure to do it right.  I don't want that for 
	now (metadata on metadata is a bad way to go...).

	Instead, we work with a couple of conventions: Metadata destined for
	"official" IVOA resource records has names as dotted paths, like
	curation.creator.name.  Local metadata for presentation purposes has
	names starting with an underscore.

	MetaItems are untyped, their values always are strings.  They have
	a format, though.  This can currently take the values "plain" (which
	does whitespace normalization and recognizes paragraphs) and "literal"
	(the default).  I'll do rst (restructured text) later, I don't think
	I'll do xhtml or junk like that.

	Other MetaItem properties:

	* combine -- can be "top", "bottom", or None (the default).  If it's
	  bottom, the content will be combined with the corresponding meta
	  item of a parent, with the current content at the bottom.  This
	  functionality is implemented in MetaMixin.
	* compute -- the value will be computed at query time using @-expansions.
	"""
	def __init__(self, parent, name, content, format=None, 
			compute=None, combine=None):
		self.name = name
		self.content = content
		self.format = format
		self.compute = compute
		self.combine = combine
		self.parent = weakref.ref(parent)
		self._normalizeContent()

	def _normalizeContent(self):
		"""does as much preformatting as we can at construction time.
		"""
		if self.format=="plain":
			self.content = "\n\n".join(["\n".join(textwrap.wrap(para))
				for para in re.split("\n\s*\n", self.content)])

	def __str__(self):
		if self.compute:
			desc = self.compute.split(",")
			if not desc[-1].strip():
				del desc[-1]
			return self.parent().get_computer().compute(desc[0], None, desc[1:])
		return self.content
	
	def asHtml(self):
		if self.format==None or self.format=="literal":
			return "<pre>%s</pre>"%str(self)
		elif self.format=="plain":
			return "\n".join(["<p>%s</p>"%para for para in str(self).split("\n\n")])
		else:
			raise Error("Unknown meta content format %s"%sel.format)

	def getName(self):
		return self.name


class MetaMixin(object):
	"""is a mixin for entities carrying meta information.

	The meta mixin provides the followng methods:

	* setMetaParent(m) -- sets the name of the meta container enclosing the
	  current one.  m has to have the Meta mixin as well.
	* getMeta(key) -- returns meta information for key or None.
	* addMeta(attDict) -- adds a piece of meta information here.  attDict
	  is a dictionary of keywords for MetaItem construction.

	When querying meta information, by default all parents are queried as
	well.

	Classes mixing this in may define a registerAsMetaParent method.  When
	a MetaParent gets set, this method is called.  It may be used to
	call setMetaParent methods of dependent meta containers.

	Classes mixing this in must have a get_computer method returning a
	FieldComputer if there are any compute attributes in MetaItems
	belonging to it.
	"""
	def __ensureMetaDict(self):
		try:
			self.__metaDict
		except AttributeError:
			self.__metaDict = {}

	def __hasMetaParent(self):
		try:
			_ = self.__metaParent
			return True
		except AttributeError:
			return False

	def setMetaParent(self, parent):
		self.__metaParent = parent
		try:
			self.registerAsMetaParent()
		except AttributeError:
			pass

	def getMeta(self, key):
		self.__ensureMetaDict()
		if self.__metaDict.has_key(key):
			return self.__metaDict[key]
		else:
			if self.__hasMetaParent():
				return self.__metaParent.getMeta(key)
	
	def addMeta(self, attDict):
		self.__ensureMetaDict()
		newItem = MetaItem(self, **attDict)
		self.__metaDict[newItem.getName()] = newItem

