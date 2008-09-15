"""
Code dealing with meta information.

The meta information we deal with here is *not* column information (which
is handled in datadef.py) but information on tables, services and
resources as a whole.

We deal with VO-style RMI metadata but also allow custom metadata.  Their
keys should start with _, however.

See develNotes for some discussion of why this is so messy and an explanation
of why in particular addMeta and helpers are a minefield of selections.

The rough plan to do this looks like this:

Metadata is kept in containers that mix in MetaMixin.  Meta information is 
accessed through keys of the form <atom>{.<atom>}  The first atom is the 
primary key.  An atom consists exclusively of ascii letters and the 
underscore.

There's a meta mixin having the methods addMeta and getMeta that care
about finding metadata including handover.  For compound metadata, they
will split the key and hand over to the parent if the don't have a meta 
item for the main key.
"""

import re
import textwrap
import warnings
import weakref

try:
	from docutils import core
except ImportError:
	pass

import gavo


def metaRstToHtml(inputString):
	sourcePath, destinationPath = None, None
	doctitle = False
	overrides = {'input_encoding': 'unicode',
		'doctitle_xform': None,
		'initial_header_level': 4}
	parts = core.publish_parts(
		source=inputString, source_path=sourcePath,
		destination_path=destinationPath,
		writer_name='html', settings_overrides=overrides)
	return parts["fragment"]


_metaPat = re.compile(r"([a-zA-Z_-]+)(?:\.([a-zA-Z_-]+))*$")
_primaryPat = re.compile(r"([a-zA-Z_-]+)(\.|$)")


def getPrimary(metaKey):
	key = _primaryPat.match(metaKey)
	if not key or not key.group(1):
		raise gavo.MetaSyntaxError("Invalid meta key: %s"%metaKey)
	return key.group(1)


def parseKey(metaKey):
	if not _metaPat.match(metaKey):
		raise gavo.MetaSyntaxError("Invalid meta key: %s"%metaKey)
	return metaKey.split(".")


class MetaMixin(object):
	"""is a mixin for entities carrying meta information.

	The meta mixin provides the followng methods:

	* setMetaParent(m) -- sets the name of the meta container enclosing the
	  current one.  m has to have the Meta mixin as well.
	* getMeta(key, propagate=True, raiseOnFail=False, default=None) -- returns 
	  meta information for key or default.
	* addMeta(key, metaItem) -- adds a piece of meta information here.  Key
	  may be a compound.

	When querying meta information, by default all parents are queried as
	well (propagate=True).

	Classes mixing this in must have a get_computer method returning a
	FieldComputer if there are any compute attributes in MetaItems
	belonging to it.

	To provide "computed" meta values or built-in default, you can override
	the getDefaultMeta(key) -> MetaItem method.  It *must* raise a KeyError
	for any key it doesn't know.  Manually set meta values always override
	this function.  They will interrupt the usual propagation of meta
	queries to parents.  To retrofit this into your getDefaultMeta, run
	getMeta(..., raiseOnFail="True") on getMetaParent.
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

	def getDefaultMeta(self, key):
		raise KeyError(key)

	def setMetaParent(self, parent):
		self.__metaParent = parent
	
	def getMetaParent(self):
		return self.__metaParent

	def _getMeta(self, atoms, propagate):
		self.__ensureMetaDict()
		try:
			return self._getFromAtom(atoms[0])._getMeta(atoms[1:])
		except gavo.NoMetaKey:
			pass   # Try if parent has the key
		if propagate:
			if self.__hasMetaParent():
				return self.__metaParent._getMeta(atoms, propagate)
			else:
				return configMeta._getMeta(atoms, propagate=False)
		raise gavo.NoMetaKey("No meta item %s"%".".join(atoms))

	def getMeta(self, key, propagate=True, raiseOnFail=False, default=None):
		try:
			return self._getMeta(parseKey(key), propagate)
		except gavo.NoMetaKey:
			if raiseOnFail:
				gavo.raiseTb(gavo.NoMetaKey, "No meta key %s"%key)
		return default

	def buildRepr(self, key, builder, propagate=True, raiseOnFail=True):
		value = self.getMeta(key, raiseOnFail=raiseOnFail, propagate=propagate)
		if value:
			builder.startKey(key)
			value.traverse(builder)
			builder.endKey(key)
		return builder.getResult()

	def _hasAtom(self, atom):
		self.__ensureMetaDict()
		return atom in self.__metaDict

	def _getFromAtom(self, atom):
		self.__ensureMetaDict()
		if atom in self.__metaDict:
			return self.__metaDict[atom]
		try:
			return self.getDefaultMeta(atom)
		except KeyError:
			raise gavo.NoMetaKey("No meta child %s"%atom)

	def keys(self):
		return self.__metaDict.keys()

	def _setForAtom(self, atom, metaItem):
		self.__ensureMetaDict()
		self.__metaDict[atom] = metaItem

	def _addMeta(self, atoms, metaItem):
		self.__ensureMetaDict()
		primary = atoms[0]
		if primary in self.__metaDict:
			self.__metaDict[primary]._addMeta(atoms[1:], metaItem)
		else:
			self.__metaDict[primary] = MetaItem.fromAtoms(atoms[1:], metaItem,
				primary)

	def addMeta(self, key, metaValue):
		"""adds metaItem to self under key.
		"""
		if isinstance(metaValue, basestring):
			metaValue = makeMetaValue(metaValue, name=key)
		self._addMeta(parseKey(key), metaValue)

	def traverse(self, builder):
		self.__ensureMetaDict()
		for key, item in self.__metaDict.iteritems():
			builder.startKey(key)
			item.traverse(builder)
			builder.endKey(key)
			

# Global meta, items get added from config
configMeta = MetaMixin()

class MetaItem(object):
	"""is a collection of homogenous MetaValues.

	All MetaValues within a MetaItem have the same key.

	A MetaItem contains a list of children MetaValues.

	The last added MetaValue is the "active" one that will be changed
	on _addMeta calls.
	"""
	def __init__(self, val):
		self.children = [val]

	def __str__(self):
		try:
			res = self.getContent(targetFormat="text")
			return res
		except gavo.MetaError:
			return "<meta sequence, %d items>"%(len(self.children))

	def __unicode__(self):
		try:
			res = self.getContent(targetFormat="text")
			return res
		except gavo.MetaError:
			return "<meta sequence, %d items>"%(len(self.children))

	def __iter__(self):
		return iter(self.children)

	def addContent(self, item):
		self.children[-1].addContent(item)

	def addChild(self, metaValue=None, key=None):
# XXX should we force metaValue to be "compatible" with what's 
# already in children?
		if metaValue==None:
			metaValue = makeMetaValue(name=key)
		assert isinstance(metaValue, MetaValue)
		self.children.append(metaValue)

	def _getMeta(self, atoms):
		if atoms:
			if len(self.children)!=1:
				raise gavo.MetaCardError("getMeta cannot be used on"
					" sequence meta items")
			else:
				return self.children[0]._getMeta(atoms)
		return self
	
	def _addMeta(self, atoms, metaValue):
# See above for this mess -- I'm afraid it has to be that complex
# if we want to be able to build compound sequences using text labels.

		# Case 1: Direct child of MetaMixin, sequence addition
		if not atoms:  
			self.addChild(metaValue)
		else:
			self.children[-1]._addMeta(atoms, metaValue)

	def getMeta(self, key):
		if len(self.children)==1:
			return self.children[0].getMeta(key)
		else:
			return gavo.MetaCardError("No getMeta for meta value sequences")

	def getContent(self, targetFormat="text"):
		if len(self.children)==1:
			return self.children[0].getContent(targetFormat)
		raise gavo.MetaCardError("getContent not allowed for sequence meta items")

	@classmethod
	def fromAtoms(cls, atoms, metaValue, key):
		if len(atoms)==0:  # This will become my child.
			return cls(metaValue)
		elif len(atoms)==1:  # Create a MetaValue with the target as child
			mv = makeMetaValue(name=key)
			mv._setForAtom(atoms[0], cls(metaValue))
			return cls(mv)
		else:   # Create a MetaValue with an ancestor of the target as child
			mv = makeMetaValue(name=key)
			mv._setForAtom(atoms[0], cls.fromAtoms(atoms[1:], metaValue, atoms[0]))
			return cls(mv)

	def traverse(self, builder):
		for mv in self.children:
			if mv.content:
				builder.enterValue(mv)
			mv.traverse(builder)


class MetaValue(MetaMixin):
	"""is a piece of meta information about a resource.

	The content is always a string.

	The text content may be in different formats, notably
	* literal
	* rst (restructured text)
	* plain (the default)
	"""
	def __init__(self, content="", format="plain"):
		self.content = content
		self.format = format
		self._preprocessContent()
	
	def _preprocessContent(self):
		if self.format=="plain":
			self.content = "\n\n".join(["\n".join(textwrap.wrap(
					re.sub("\s+", " ", para)))
				for para in re.split("\n\s*\n", self.content)])

	def _getContentAsText(self):
		return self.content
	
	def _getContentAsHTML(self):
		if self.format=="literal":
			return '<span class="literalmeta">%s</span>'%self.content
		elif self.format=="plain":
			return "\n".join('<span class="plainmeta">%s</span>'%p 
				for p in self.content.split("\n\n"))
		elif self.format=="rst":
			return metaRstToHtml(self.content)

	def getContent(self, targetFormat="text"):
		if targetFormat=="text":
			return self._getContentAsText()
		elif targetFormat=="html":
			return self._getContentAsHTML()
		else:
			raise gavo.MetaError("Invalid meta target format: %s"%targetFormat)

	def __str__(self):
		return self.getContent().encode("utf-8")
	
	def __unicode__(self):
		return self.getContent()

	def encode(self, enc):
		return unicode(self).encode(enc)

	def _getMeta(self, atoms, propagate=False):
		return self._getFromAtom(atoms[0])._getMeta(atoms[1:])

	def _addMeta(self, atoms, metaValue):
# Cases continued from MetaItem._addMeta
		# Case 2: Part of a compound, metaValue is to become direct child
		if len(atoms)==1: 
			primary = atoms[0]

			# Case 2.1: Requested child exists
			if self._hasAtom(primary):
				self._getFromAtom(primary).addChild(metaValue, primary)

			# Case 2.2: Requested child does not exist
			else:
				self._setForAtom(primary, MetaItem(metaValue))

		# Case 3: metaItem will become an indirect child
		else:
			primary = atoms[0]

			# Case 3.1: metaValue will become a child of an existing child of ours
			if self._hasAtom(primary):
				self._getFromAtom(primary)._addMeta(atoms[1:], metaValue)

			# Case 3.2: metaItem is on a branch that needs yet to be created.
			else:
				self._setForAtom(primary, MetaItem.fromAtoms(atoms, 
					metaValue, primary))


class MetaURL(MetaValue):
	"""is a meta value containing a link and a title.

	The title can also be set via addMeta for the benefit of constructing
	MetaURLs from key/value-pairs.
	"""
	def __init__(self, url, format="plain", title=None):
		MetaValue.__init__(self, url, format)
		self.title = title
	
	def _getContentAsHTML(self):
		return '<a href="%s">%s</a>'%(self.content, self.title or self.content)
	
	def _addMeta(self, atoms, metaValue):
		if atoms[0]=="title":
			self.title = metaValue.content
		else:
			MetaValue._addMeta(self, atoms, metaValue)


class InfoItem(MetaValue):
	"""is a meta value for info items in VOTables.

	In addition to the content (which should be rendered as the info element's
	text content), it contains an infoName and an infoValue.
	"""
	def __init__(self, content, format="plain", infoName=None, 
			infoValue=None, infoId=None):
		MetaValue.__init__(self, content, format)
		self.infoName, self.infoValue = infoName, infoValue
		self.infoId = infoId


class LogoMeta(MetaValue):
	"""is a MetaItem corresponding to a small image
	"""
	def _getContentAsHTML(self):
		return '<img class="metalogo" src="%s" height="16" alt="[Logo]"/>'%(
				unicode(self.content))


_metaTypeRegistry = {
	"link": MetaURL,
	"info": InfoItem,
	"logo": LogoMeta,
}

_typesForKeys = {
	"_related": "link",
	"referenceURL": "link",
	"info": "info",
	"logo": "logo",
}

def makeMetaValue(value="", **kwargs):
	"""returns a MetaValue instance depending on kwargs.

	Basically, with kwargs["type"] you can select various "special"
	MetaValue-derived types, for example InfoItems, MetaLinks, etc.

	These should always work as "normal" meta items but may provide
	special functionality or attributes, e.g. in HTML serializing (Links
	include a title, InfoItems provide additional attributes for VOTables.

	In general, it's preferable to use plain MetaValues and, e.g., add
	a title meta to a URL.  However, for the most common "structured" values
	it's more convenient to use specialized classes.

	In addition, you can pass the name the MetaValue will eventually have.
	If you do that, a type may automatically be added (but not overridden)
	from the _typesForKeys dictionary.
	"""
	cls = MetaValue
	if "name" in kwargs:
		lastKey = parseKey(kwargs["name"])[-1]
		if lastKey in _typesForKeys and not "type" in kwargs and not (
				kwargs.get("format")=="rst"):
			kwargs["type"] = _typesForKeys[lastKey]
		del kwargs["name"]
	if "type" in kwargs:
		if kwargs["type"]!=None:
			try:
				cls = _metaTypeRegistry[kwargs["type"]]
			except KeyError:
				raise gavo.MetaError("No such meta value type: %s"%kwargs["type"])
		del kwargs["type"]
	try:
		return cls(value, **kwargs)
	except TypeError:
		gavo.raiseTb(gavo.MetaError, "Invalid arguments for %s meta items :%s"%(
			cls.__name__, str(kwargs)))


class MetaBuilder(object):
	"""is a builder that does nothing.

	Builders are passed to a MetaItem's traverse method or to MetaMixin's
	buildRepr method to build representations of the meta information.

	You can either override startKey, endKey, and enterValue of just
	provide a process(keyAtoms, value) method.

	You will want to override getResult.
	"""
	def __init__(self):
		self.curAtoms = []

	def startKey(self, key):
		self.curAtoms.append(key)
	
	def endKey(self, key):
		self.curAtoms.pop()
		
	def enterValue(self, value):
		pass
	
	def getResult(self):
		pass


class TextBuilder(MetaBuilder):
	"""is a MetaBuilder that recovers a tuple sequence of the meta items
	in text representation.
	"""
	def __init__(self):
		self.metaItems = []
		super(TextBuilder, self).__init__()
	
	def enterValue(self, value):
		self.metaItems.append((".".join(self.curAtoms), value.getContent()))
	
	def getResult(self):
		return self.metaItems


def stanFactory(tag, **kwargs):
	"""returns a factory for ModelBasedBuilder built from a stan-like "tag".
	"""
	def factory(args, localattrs=None):
		if localattrs:
			localattrs.update(kwargs)
			attrs = localattrs
		else:
			attrs = kwargs
		return tag(**attrs)[args]
	return factory


class ModelBasedBuilder(object):
	"""is a meta builder that can create stan-like structures from meta
	information

	It is constructed with with a tuple-tree of keys and DOM constructors;
	these must work like stan elements, which is, e.g., also true for our
	registrymodel elements.

	Each node in the tree can be one of:
	
	* a meta key and a callable,
	* this, and a sequence of child nodes
	* this, and a dictionary mapping argument names to the callable
	  to meta keys of the node.
	"""
	def __init__(self, constructors, format="text"):
		self.constructors, self.format = constructors, format

	def _getItemsForConstructor(self, metaContainer, key, factory, 
			children=(), attrs={}):
		if factory:
			def processContent(childContent, metaItem):
				moreAttrs = {}
				for argName, metaKey in attrs.iteritems():
					val = metaItem.getMeta(metaKey)
					if val:
						moreAttrs[argName] = unicode(val)
				return [factory(childContent, localattrs=moreAttrs)]
		else:
			def processContent(childContent, metaItem):
				return childContent
			
		mi = metaContainer.getMeta(key, raiseOnFail=False)
		if not mi:
			return []
		result = []
		for child in mi.children:
			content = []
			c = child.getContent(self.format)
			if c:
				content.append(c)
			childContent = self._build(children, child)
			if childContent:
				content.append(childContent)
			if content:
				result.append(processContent(content, child))
		return result

	def _build(self, constructors, metaContainer):
		result = []
		for item in constructors:
			if isinstance(item, basestring):
				result.append(item)
			else:
				result.extend(self._getItemsForConstructor(metaContainer, *item))
		return result

	def build(self, metaContainer):
		return self._build(self.constructors, metaContainer)
