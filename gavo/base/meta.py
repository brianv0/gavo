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
import urllib
import warnings
import weakref

try:
	from docutils import core
except ImportError:
	pass

from gavo import utils
from gavo.base import attrdef
from gavo.base import structure


class MetaError(utils.Error):
	pass

class MetaSyntaxError(MetaError):
	"""is raised when a meta key is invalid.
	"""

class NoMetaKey(MetaError):
	"""is raised when a meta key does not exist (and raiseOnFail is True).
	"""

class MetaCardError(MetaError):
	"""is raised when a meta value somehow has the wrong cardinality (e.g.,
	on attempting to stringify a sequence meta).
	"""

def metaRstToHtml(inputString):
	sourcePath, destinationPath = None, None
	doctitle = False
	overrides = {'input_encoding': 'unicode',
		'doctitle_xform': None,
		'initial_header_level': 4}
	if not isinstance(inputString, unicode):
		inputString = inputString.decode("utf-8")
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
		raise MetaSyntaxError("Invalid meta key: %s"%metaKey)
	return key.group(1)


def parseKey(metaKey):
	if not _metaPat.match(metaKey):
		raise MetaSyntaxError("Invalid meta key: %s"%metaKey)
	return metaKey.split(".")


class MetaParser(structure.Parser):
	"""is a structure parser that kicks in when meta information is 
	parsed from XML.
	"""
# These are constructed a lot, so let's keep __init__ as clean as possible, 
# shall we?
	def __init__(self, container, nextParser):
		self.container, self.nextParser = container, nextParser
		self.attrs = {}
		self.children = []  # containing key, metaValue pairs
		self.next = None

	def addMeta(self, *value):
		self.children.append(value)

	def start(self, ctx, name, value):
		if name=="meta":
			return MetaParser(self, self)
		else:
			self.next = name
			return self

	def value(self, ctx, name, value):
		if self.next is None:
			self.attrs[str(name)] = value
		else:
			self.attrs[str(self.next)] = value
		return self

	def _getMetaValue(self):
		content = self.attrs.pop("content_", "")
		if self.attrs.get("format", "plain")=="plain":
			content = content.strip()
		else:
			content = utils.fixIndentation(content, "", 1)
		mv = makeMetaValue(content, **self.attrs)
		if not "name" in self.attrs:
			raise structure.StructureError("meta elements must have a"
				" name attribute")
		return self.attrs.pop("name"), mv

	def end(self, ctx, name, value):
		if name=="meta":
			key, mv = self._getMetaValue()
			for child in self.children:
				mv.addMeta(*child)
			self.container.addMeta(key, mv)
			return self.nextParser
		else:
			self.next = None
			return self


class MetaAttribute(attrdef.AttributeDef):
	"""is an attribute magically inserting meta values to Structures mixing
	in MetaMixin.

	We don't want to keep metadata in structures, so we define a parser
	of our own in here.
	"""
	typedesc = "Metadata"

	def __init__(self, description="Metadata"):
		attrdef.AttributeDef.__init__(self, "meta_", 
			attrdef.Computed, description)
		self.xmlName_ = "meta"

	@property
	def default_(self):
		return {}

	def getParser(self, parent):
		return MetaParser(parent, parent.feedEvent)

	def feedObject(self, instance, value):
		self.meta_ = value

	def getCopy(self, parent, newParent):
		"""creates a deep copy of the current meta dictionary and sets it
		as the new meta dictionary.

		You need to call this when you do a copy (using something like copy.copy()
		of an object mixing in this class.

		Note that the copying semantics is a bit funky: Copied values
		remain, but on write, sequences are replaced rather than added to.
		"""
		oldDict = self.meta_
		newMeta = {}
		for key, mi in oldDict.iteritems():
			newMeta[key] = mi.copy()
		return oldDict
	
	def create(self, parent, name):
		return self  # we're it...

	def makeUserDoc(self):
		return ("**meta** -- a piece of meta information, giving at least a name"
			" and some content.  See Metadata_ on what is permitted here.")


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
	"""
	_metaAttr = MetaAttribute()

	def __init__(self):
		"""is a constructor for standalone use.  You do *not* want to
		call this when mixing into a Structure.
		"""
		self.meta_ = {}

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
		try:
			return self._getFromAtom(atoms[0])._getMeta(atoms[1:])
		except NoMetaKey:
			pass   # See if parent has the key
		if propagate:
			if self.__hasMetaParent():
				return self.__metaParent._getMeta(atoms, propagate)
			else:
				return configMeta._getMeta(atoms, propagate=False)
		raise NoMetaKey("No meta item %s"%".".join(atoms))

	def getMeta(self, key, propagate=True, raiseOnFail=False, default=None):
		try:
			return self._getMeta(parseKey(key), propagate)
		except NoMetaKey, ex:
			if raiseOnFail:
				ex.key = key
				raise
		return default

	def buildRepr(self, key, builder, propagate=True, raiseOnFail=True):
		value = self.getMeta(key, raiseOnFail=raiseOnFail, propagate=propagate)
		if value:
			builder.startKey(key)
			value.traverse(builder)
			builder.endKey(key)
		return builder.getResult()

	def _hasAtom(self, atom):
		return atom in self.meta_

	def _getFromAtom(self, atom):
		if atom in self.meta_:
			return self.meta_[atom]
		try:
			return self.getDefaultMeta(atom)
		except KeyError:
			raise NoMetaKey("No meta child %s"%atom)

	def getMetaKeys(self):
		return self.meta_.keys()

# XXX TRANS remove; this is too common a name
	keys = getMetaKeys

	def _setForAtom(self, atom, metaItem):
		self.meta_[atom] = metaItem

	def _addMeta(self, atoms, metaValue):
		primary = atoms[0]
		if primary in self.meta_:
			self.meta_[primary]._addMeta(atoms[1:], metaValue)
		else:
			self.meta_[primary] = MetaItem.fromAtoms(atoms[1:], metaValue,
				primary)

	def addMeta(self, key, metaValue):
		"""adds metaItem to self under key.
		"""
		if isinstance(metaValue, basestring):
			metaValue = makeMetaValue(metaValue, name=key)
		self._addMeta(parseKey(key), metaValue)

	def traverse(self, builder):
		for key, item in self.meta_.iteritems():
			builder.startKey(key)
			item.traverse(builder)
			builder.endKey(key)

	def deepCopyMeta(self):
		"""creates a deep copy of the current meta dictionary and sets it
		as the new meta dictionary.

		This is used during a recursive copy of a meta tree.  If this
		is mixed into a structure, its attribute magic will automatically
		make sure this ist applied.

		Note that the copying semantics is a bit funky: Copied values
		remain, but on write, sequences are replaced rather than added to.
		"""
		oldDict = self.meta_
		self.meta_ = {}
		for key, mi in oldDict.iteritems():
			self.meta_[key] = mi.copy()

# Global meta, items get added from config
configMeta = MetaMixin()


class ComputedMetaMixin(MetaMixin):
	"""is a MetaMixin for classes that want to implement defaults for
	unresolvable meta items.

	If getMeta would return a NoMetaKey, this mixin's getMeta will check
	the presence of a _meta_<key> method (replacing dots with two underscores)
	and, if it exists, returns whatever it returns.  Otherwise, the
	exception will be propagated.
	"""
	def getMeta(self, key, raiseOnFail=False, default=None, **kwargs):
		try:
			res = MetaMixin.getMeta(self, key, default=default, raiseOnFail=True, 
				**kwargs)
		except NoMetaKey:
			methName = "_meta_"+key.replace(".", "__")
			import sys
			if hasattr(self, methName):
				res = getattr(self, methName)()
			else:
				if raiseOnFail:
					raise
				else:
					res = default
		return res

class MetaItem(object):
	"""is a collection of homogenous MetaValues.

	All MetaValues within a MetaItem have the same key.

	A MetaItem contains a list of children MetaValues.

	The last added MetaValue is the "active" one that will be changed
	on _addMeta calls.
	"""
	def __init__(self, val):
		self.children = [val]

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

	def __str__(self):
		try:
			res = self.getContent(targetFormat="text")
			return res
		except MetaError:
			return ", ".join(m.getContent(targetFormat="text") 
				for m in self.children)

	__unicode__ = __str__

	def __iter__(self):
		return iter(self.children)

	def __len__(self):
		return len(self.children)

	def addContent(self, item):
		self.children[-1].addContent(item)

	def addChild(self, metaValue=None, key=None):
# XXX should we force metaValue to be "compatible" with what's 
# already in children?
		if hasattr(self, "copied"):
			self.children = []
			delattr(self, "copied")
		if metaValue is None:
			metaValue = makeMetaValue(name=key)
		assert isinstance(metaValue, MetaValue)
		self.children.append(metaValue)

	def _getMeta(self, atoms):
		if atoms:
			if len(self.children)!=1:
				raise MetaCardError("getMeta cannot be used on"
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
			return MetaCardError("No getMeta for meta value sequences")

	def getContent(self, targetFormat="text"):
		if len(self.children)==1:
			return self.children[0].getContent(targetFormat)
		raise MetaCardError("getContent not allowed for sequence meta items")

	def traverse(self, builder):
		for mv in self.children:
			if mv.content:
				builder.enterValue(mv)
			mv.traverse(builder)

	def copy(self):
		"""returns a deep copy of self.
		"""
		newOb = self.__class__("")
		newOb.children = [mv.copy() for mv in self.children]
		newOb.copied = True
		return newOb

	def serializeToXMLStan(self):
		return unicode(self)


class MetaValue(MetaMixin):
	"""is a piece of meta information about a resource.

	The content is always a string.

	The text content may be in different formats, notably
	* literal
	* rst (restructured text)
	* plain (the default)
	* raw (for embedded HTML, mainly -- only use this if you know
	  the item will only be embedded into HTML templates).
	"""
	knownFormats = set(["literal", "rst", "plain", "raw"])

	def __init__(self, content="", format="plain"):
		MetaMixin.__init__(self)
		if format not in self.knownFormats:
			raise StructureError("Unknown meta format '%s'; allowed are %s."%(
				format, ", ".join(self.knownFormats)))
		self.content = content
		self.format = format
		self._preprocessContent()
	
	def _preprocessContent(self):
		if self.format=="plain":
			self.content = "\n\n".join(["\n".join(textwrap.wrap(
					re.sub("\s+", " ", para)))
				for para in re.split("\n\s*\n", self.content)])

	def _getContentAsText(self, content):
		return content
	
	def _getContentAsHTML(self, content):
		if self.format=="literal":
			return '<span class="literalmeta">%s</span>'%content
		elif self.format=="plain":
			return "\n".join('<span class="plainmeta">%s</span>'%p 
				for p in content.split("\n\n"))
		elif self.format=="rst":
			return metaRstToHtml(content)
		elif self.format=="raw":
			return content

	def getContent(self, targetFormat="text", macroPackage=None):
		content = self.content
		if macroPackage and "\\" in self.content:
			content = macroPackage.expand(content)
		if targetFormat=="text":
			return self._getContentAsText(content)
		elif targetFormat=="html":
			return self._getContentAsHTML(content)
		else:
			raise MetaError("Invalid meta target format: %s"%targetFormat)

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

	def copy(self):
		"""returns a deep copy of self.
		"""
		newOb = self.__class__()
		newOb.format, newOb.content = self.format, self.content
		newOb.deepCopyMeta()
		return newOb


class MetaURL(MetaValue):
	"""A meta value containing a link and a title.

	In plain text, this would look like
	this::
	
		_related:http://foo.bar
		_related.title: The foo page

	In XML, you can write::

			<meta name="_related" title="The foo page">http://foo.bar</meta>

	or, if you prefer::

		<meta name="_related">http://foo.bar
			 <meta name="title">The foo page</meta></meta>
	"""
	def __init__(self, url, format="plain", title=None):
		MetaValue.__init__(self, url, format)
		self.title = title
	
	def _getContentAsHTML(self, content):
		return '<a href="%s">%s</a>'%(content, self.title or content)
	
	def _addMeta(self, atoms, metaValue):
		if atoms[0]=="title":
			self.title = metaValue.content
		else:
			MetaValue._addMeta(self, atoms, metaValue)


class NewsMeta(MetaValue):
	"""A meta value representing a "news" items.

	The content is the body of the news.  In addition, they have
	date and author children.  In plain text, you would write::

	  _news: Frobnicated the quux.
	  _news.author: MD
	  _news.date: 2009-03-06
	
	In XML, you would usually write::

	  <meta name="_news" author="MD" date="2009-03-06">
	    Frobnicated the quux.
	  </meta>
	"""
	def __init__(self, url, format="plain", author=None, 
			date="Unspecified time"):
		MetaValue.__init__(self, url, format)
		self.author = author
		self.date = date

	def _getContentAsHTML(self, content):
		authorpart = ""
		if self.author:
			authorpart = " (%s)"%self.author
		return '<span class="newsitem">%s%s: %s</span>'%(self.date, authorpart,
			content)
	
	def _addMeta(self, atoms, metaValue):
		if atoms[0]=="author":
			self.author = metaValue.content
		elif atoms[0]=="date":
			self.date = metaValue.content
		else:
			MetaValue._addMeta(self, atoms, metaValue)


class InfoItem(MetaValue):
	"""A meta value for info items in VOTables.

	In addition to the content (which should be rendered as the info element's
	text content), it contains an infoName and an infoValue.
	
	They are only used internally in VOTable generation and might go away
	without notice.
	"""
	def __init__(self, content, format="plain", infoName=None, 
			infoValue=None, infoId=None):
		MetaValue.__init__(self, content, format)
		self.infoName, self.infoValue = infoName, infoValue
		self.infoId = infoId


class LogoMeta(MetaValue):
	"""A MetaItem corresponding to a small image.

	These are rendered as little images in HTML.  In XML meta, you can
	say::

	  <meta name="_somelogo" type="logo">http://foo.bar/quux.png</meta>
	"""
	def _getContentAsHTML(self, content):
		return u'<img class="metalogo" src="%s" height="16" alt="[Logo]"/>'%(
				unicode(content))


class BibcodeMeta(MetaValue):
	"""A MetaItem that may contain bibcodes, which are rendered as links
	into ADS.
	"""
	bibcodePat = re.compile("\d\d\d\d\w[^ ]{14}")
	adsMirror = "http://ads.ari.uni-heidelberg.de/"
	def _makeADSLink(self, matOb):
		return '<a href="%s">%s</a>'%(
			self.adsMirror+"cgi-bin/nph-data_query?bibcode=%s&"
				"link_type=ABSTRACT"%urllib.quote(matOb.group(0)),
			matOb.group(0))

	def _getContentAsHTML(self, content):
		return self.bibcodePat.sub(self._makeADSLink, unicode(content))


_metaTypeRegistry = {
	"link": MetaURL,
	"info": InfoItem,
	"logo": LogoMeta,
	"bibcodes": BibcodeMeta,
	"news": NewsMeta,
}

_typesForKeys = {
	"_related": "link",
	"_news": "news",
	"referenceURL": "link",
	"info": "info",
	"logo": "logo",
	"source": "bibcodes",
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
		if kwargs["type"] is not None:
			try:
				cls = _metaTypeRegistry[kwargs["type"]]
			except KeyError:
				raise MetaError("No such meta value type: %s"%kwargs["type"])
		del kwargs["type"]
	try:
		return cls(value, **kwargs)
	except TypeError:
		raise MetaError(
			"Invalid arguments for %s meta items :%s"%(cls.__name__, str(kwargs)))


def getMetaText(ob, key, propagate=False):
	"""returns the meta item key form ob in text form if present, None otherwise.
	"""
	m = ob.getMeta(key, propagate=propagate)
	if m:
		return m.getContent()
	return None


class MetaBuilder(object):
	"""A base class for meta builders.

	Builders are passed to a MetaItem's traverse method or to MetaMixin's
	buildRepr method to build representations of the meta information.

	You can either override startKey, endKey, and enterValue.  If you are
	not doing anything fancy, you can get by by just overriding enterValue
	and inspecting curAtoms[-1] (which contains the last meta key).

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
