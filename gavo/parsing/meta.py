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


from gavo import config


class InfoItem(object):
	"""is a container for VOTable info elements that you can stick into
	a MetaItem.

	The assumption is that the info value item usually is from a controlled
	vocabulary that non-VOTable clients won't want to see, so the str() doesn't
	return it.
	"""
	def __init__(self, value, content):
		self.value, self.content = value, content

	def __str__(self):
		return str(self.content)


class MetaItem(object):
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
		self.format = format or "literal"
		self.compute = compute
		self.combine = combine
		self.parent = weakref.ref(parent)

	def __str__(self):
		if self.compute:
			desc = self.compute.split(",")
			if not desc[-1].strip():
				del desc[-1]
			content = unicode(self.parent().get_computer().compute(
				desc[0], None, desc[1:])).encode("utf-8")
		else: 
			content = unicode(self.content).encode("utf-8")
		if self.format=="plain":
			content = "\n\n".join(["\n".join(textwrap.wrap(para))
				for para in re.split("\n\s*\n", content)])
		return content

	def encode(self, enc):
		return str(self).encode(enc)

	def asHtml(self):
		if self.format=="literal":
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

	def getMeta(self, key, propagate=True):
		self.__ensureMetaDict()
		if self.__metaDict.has_key(key):
			return self.__metaDict[key]
		if propagate:
			if self.__hasMetaParent():
				return self.__metaParent.getMeta(key)
			else:
				return config.getMeta(key)

	def addMeta(self, *args, **kwargs):
		if len(args)>1:
			raise TypeError("addMeta takes only up to one positional argument"
				" (%d given)"%len(args))
		elif len(args)==0:
			attDict = kwargs
		else:
			attDict = args[0].copy()
			attDict.update(kwargs)
		self.__ensureMetaDict()
		newItem = MetaItem(self, **attDict)
		self.__metaDict[newItem.getName()] = newItem

