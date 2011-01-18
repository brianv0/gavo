"""
A stan-like model for building namespaced XML trees.

The main reason for this module is that much of the VO's XML mess is based
on XML schema and thus has namespaced attributes.  This single design
decision ruins the entire XML design.  To retain some rests of
sanity, I treat the prefixes themselves as namespaces and maintain
a single central registry from prefixes to namespaces in this module.

Then, the elements only use these prefixes, and this module makes sure
that during serialization the instance document's root element contains
the namespace mapping (and the schema locations) required.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

try:
	from xml.etree import cElementTree as ElementTree
except ImportError:
	from elementtree import ElementTree

from gavo.utils import autonode

class Error(Exception):
	pass


class ChildNotAllowed(Error):
	pass


encoding = "utf-8"
XML_HEADER = '<?xml version="1.0" encoding="%s"?>'%encoding


class _Autoconstructor(autonode.AutoNodeType):
	"""A metaclass used for Elements.

	On the one hand, it does autonode's constructor magic with _a_<attrname>
	attributes, on the other, it will instanciate itself when indexed
	-- that we want for convenient stan-like notation.
	"""
	def __init__(cls, name, bases, dict):
		autonode.AutoNodeType.__init__(cls, name, bases, dict)
		if hasattr(cls, "_childSequence") and cls._childSequence is not None:
			cls._allowedChildren = set(cls._childSequence)
		else:
			cls._childSequence = None

	def __getitem__(cls, items):
		return cls()[items]


class Stub(object):
	"""A sentinel class for embedding objects not yet existing into
	stanxml trees.

	These have a single opaque object and need to be dealt with by the
	user.  One example of how these can be used is the ColRefs in stc to
	utype conversion.

	Stubs are equal to each othter if their handles are identical.
	"""
	name_ = "stub"
	text_ = None

	def __init__(self, dest):
		self.dest = dest

	def __repr__(self):
		return "%s(%s)"%(self.__class__.__name__, repr(self.dest))

	def __eq__(self, other):
		return self.dest==getattr(other, "dest", Stub)
	
	def __ne__(self, other):
		return not self==other

	def __hash__(self):
		return hash(self.dest)

	def isEmpty(self):
		return False
	
	def makeChildDict(self):
		return {}

	def iterAttNames(self):
		if False:
			yield


class Element(object):
	"""An element for serialization into XML.

	This is loosely modelled after nevow stan.

	Don't add to the children attribute directly, use addChild or (more
	usually) __getitem__.

	Elements have attributes and children.  The attributes are defined,
	complete with defaults, in _a_<name> attributes as in AutoNodes.
	Attributes are checked.

	Children are not usually checked, but you can set a _childSequence
	attribute containing a list of (unqualified) element names.  These
	children will be emitted in the sequence given.
	
	When deriving from Elements, you may need attribute names that are not
	python identifiers (e.g., with dashes in them).  In that case, define
	an attribute _name_a_<att> and point it to any string you want as the
	attribute.

	When building an ElementTree out of this, empty elements (i.e. those
	having an empty text and having no non-empty children) are usually
	discarded.  If you need such an element (e.g., for attributes), set
	mayBeEmpty to True.

	Since insane XSD mandates that local elements must not be qualified when
	elementFormDefault is unqualified, you need to set _local=True on
	such local elements to suppress the namespace prefix.  Attribute names
	are never qualified here.  If you need qualified attributes, you'll
	have to use attribute name translation.

	Local elements like this will only work properly if you give the parent 
	elements the appropriate xmlns attribute.

	The content of the DOM may be anything recognized by addChild.
	In particular, you can give objects a serializeToXMLStan method returning
	strings or an Element to make them good DOM citizens.

	Elements cannot harbor mixed content (or rather, there is only
	one piece of text).
	"""
	__metaclass__ = _Autoconstructor

	name_ = None
	_a_id = None
	_prefix = ""
	_additionalPrefixes = frozenset()
	_mayBeEmpty = False
	_local = False
	_stringifyContent = False

	# should probably do this in the elements needing it (quite a lot of them
	# do, however...)
	_name_a_xsi_type = "xsi:type"

	# for type dispatching in addChild.
	_generator_t = type((x for x in ()))

	# see _setupNode below for __init__

	def __getitem__(self, children):
		self.addChild(children)
		return self

	def __call__(self, **kw):
		if not kw:
			return self
	
		# XXX TODO: namespaced attributes?
		for k, v in kw.iteritems():
			# Only allow setting attributes already present
			getattr(self, k)
			setattr(self, k, v)
		return self

	def __iter__(self):
		raise NotImplementedError("Element instances are not iterable.")

	def __nonzero__(self):
		return self.isEmpty()

	def _setupNodeNext(self, cls):
		try:
			pc = super(cls, self)._setupNode
		except AttributeError:
			pass
		else:
			pc()

	def _setupNode(self):
		self.__isEmpty = None
		self._children = []
		self.text_ = ""
		if self.name_ is None:
			self.name_ = self.__class__.__name__.split(".")[-1]
		self._setupNodeNext(Element)

	def _makeAttrDict(self):
		res = {}
		for name, attName in self.iterAttNames():
			if getattr(self, name) is not None:
				res[attName] = unicode(getattr(self, name))
		return res

	def _iterChildrenInSequence(self):
		cDict = self.makeChildDict()
		for cName in self._childSequence:
			if cName in cDict:
				for c in cDict[cName]:
					yield c

	def bailIfBadChild(self, child):
		if (self._childSequence is not None 
				and getattr(child, "name_", None) not in self._allowedChildren 
				and type(child) not in self._allowedChildren):
			raise ChildNotAllowed("No %s children in %s"%(
				getattr(child, "name_", "text"), self.name_))

	def addChild(self, child):
		"""adds child to the list of children.

		Child may be an Element, a string, or a list or tuple of Elements and
		strings.  Finally, child may be None, in which case nothing will be
		added.
		"""
		self.__isEmpty = None
		if hasattr(child, "serializeToXMLStan"):
			self.addChild(child.serializeToXMLStan())
		elif child is None:
			pass
		elif isinstance(child, basestring):
			self.bailIfBadChild(child)
			self.text_ = child
		elif isinstance(child, (Element, Stub)):
			self.bailIfBadChild(child)
			self._children.append(child)
		elif isinstance(child, (list, tuple, self._generator_t)):
			for c in child:
				self.addChild(c)
		elif isinstance(child, _Autoconstructor):
			self.addChild(child())
		elif self._stringifyContent:
			self.addChild(unicode(child))
		else:
			raise Error("%s element %s cannot be added to %s node"%(
				type(child), repr(child), self.name_))

	def isEmpty(self):
		if self.__isEmpty is None:
			self.__isEmpty = True
			if self._mayBeEmpty or self.text_.strip():
				self.__isEmpty = False
			else:
				for c in self._children:
					if not c.isEmpty():
						self.__isEmpty = False
						break
		return self.__isEmpty


	def iterAttNames(self):
		"""iterates over the defined attribute names of this node.
		
		Each element returned is a pair of the node attribute name and the 
		xml name (which may be translated via _a_name_<att>
		"""
		for name, default in self._nodeAttrs:
			xmlName = getattr(self, "_name_a_"+name, name)
			yield name, xmlName

	def addAttribute(self, attName, attValue):
		"""adds attName, attValue to this Element's attributes when instanciated.

		You cannot add _a_<attname> attributes to instances.  Thus, when
		in a pinch, use this.
		"""
		attName = str(attName)
		self._nodeAttrs.append((attName, attValue))
		setattr(self, attName, attValue)

	def iterChildrenOfType(self, type):
		"""iterates over all children having type.
		"""
		for c in self._children:
			if isinstance(c, type):
				yield c

	def iterChildren(self):
		return iter(self._children)

	def makeChildDict(self):
		cDict = {}
		for c in self._children:
			cDict.setdefault(c.name_, []).append(c)
		return cDict

	def apply(self, func):
		"""calls func(name, text, attrs, childIter).

		This is a building block for tree traversals; the expectation is that 
		func does something like (c.apply(visitor) for c in childIter).
		"""
		try:
			if self.isEmpty():
				return
			attrs = self._makeAttrDict()
			if self._childSequence is None:
				childIter = iter(self._children)
			else:
				childIter = self._iterChildrenInSequence()
			return func(self, self.text_,
				self._makeAttrDict(), childIter)
		except Error:
			raise
		except Exception, msg:
			msg.args = (unicode(msg)+(" while building %s node"
				" with children %s"%(self.name_, self._children)),)+msg.args[1:]
			raise

	def asETree(self, emptyPrefix=None):
		"""returns an ElementTree instance for the tree below this node.
		"""
		return DOMMorpher(emptyPrefix, NSRegistry).getMorphed(self)

	def render(self, emptyPrefix=None):
		et = self.asETree(emptyPrefix=emptyPrefix)
		if et is None:
			return ""
		return ElementTree.tostring(et)


class NSRegistry(object):
	"""A container for a registry of namespace prefixes to namespaces.

	This is used to have fixed namespace prefixes (IMHO the only way
	to have namespaced attributes and retain sanity).  The
	class is never instanciated.  It is used through the module-level
	method registerPrefix and by DOMMorpher.
	"""
	_registry = {}
	_reverseRegistry = {}
	_schemaLocations = {}

	@classmethod
	def registerPrefix(cls, prefix, ns, schemaLocation):
		if prefix in cls._registry:
			if ns!=cls._registry[prefix]:
				raise ValueError("Prefix %s is already allocated for namespace %s"%
					(prefix, ns))
		cls._registry[prefix] = ns
		cls._reverseRegistry[ns] = prefix
		cls._schemaLocations[prefix] = schemaLocation

	@classmethod
	def getPrefixForNS(cls, ns):
		try:
			return cls._reverseRegistry[ns]
		except KeyError:
			raise excs.NotFoundError(ns, "XML namespace",
				"registry of XML namespaces.", hint="The registry is filled"
				" by modules as they are imported -- maybe you need to import"
				" the right module?")

	@classmethod
	def getNSForPrefix(cls, prefix):
		try:
			return cls._registry[prefix]
		except KeyError:
			raise excs.NotFoundError(ns, "XML namespace prefix",
				"registry of prefixes.", hint="The registry is filled"
				" by modules as they are imported -- maybe you need to import"
				" the right module?")

	@classmethod
	def addNamespaceDeclarations(cls, root, prefixes):
		schemaLocations = []
		if prefixes:  # we'll need xsi for schemaLocation if we declare some
			prefixes.add("xsi")
		for pref in prefixes:
			root.attrib["xmlns:%s"%pref] = cls._registry[pref]
			if cls._schemaLocations[pref]:
				schemaLocations.append("%s %s"%(
					cls._registry[pref],
					cls._schemaLocations[pref]))
		if schemaLocations:
			root.attrib["xsi:schemaLocation"] = " ".join(schemaLocations)

	@classmethod
	def getPrefixInfo(cls, prefix):
		return (cls._registry[prefix], cls._schemaLocations[prefix])


registerPrefix = NSRegistry.registerPrefix
getPrefixInfo = NSRegistry.getPrefixInfo

def schemaURL(xsdName):
	"""returns the URL to the local mirror of the schema xsdName.

	This is used by the various xmlstan clients to make schemaLocations.
	"""
	return "http://vo.ari.uni-heidelberg.de/docs/schemata/"+xsdName


registerPrefix("xsi","http://www.w3.org/2001/XMLSchema-instance",  None)
# convenience for _additionalPrefixes of elements needing the xsi prefix
# (and no others) in their attributes.
xsiPrefix = frozenset(["xsi"])


class DOMMorpher(object):
	"""An object encapsulating the process of turning a stanxml.Element
	tree into an ElementTree.

	Discard instances after single use.
	"""
	def __init__(self, emptyPrefix=None, nsRegistry=NSRegistry):
		self.emptyPrefix, self.nsRegistry = emptyPrefix, nsRegistry
		self.prefixesUsed = set()
	
	def _morphNode(self, stanEl, content, attrDict, childIter):
		name = stanEl.name_
		if stanEl._prefix:
			self.prefixesUsed.add(stanEl._prefix)
			if not (stanEl._local or stanEl._prefix==self.emptyPrefix):
				name = "%s:%s"%(stanEl._prefix, stanEl.name_)
		if stanEl._additionalPrefixes:
			self.prefixesUsed.update(stanEl._additionalPrefixes)

		node = ElementTree.Element(name, **attrDict)
		if content:
			node.text = content
		for child in childIter:
			childNode = child.apply(self._morphNode)
			if childNode is not None:
				node.append(childNode)
		return node

	def getMorphed(self, stan):
		root = stan.apply(self._morphNode)
		self.nsRegistry.addNamespaceDeclarations(root, self.prefixesUsed)
		if self.emptyPrefix:
			root.attrib["xmlns"] = self.nsRegistry.getNSForPrefix(
				self.emptyPrefix)
		return root


def xmlrender(tree, prolog=None, emptyPrefix=None):
	"""returns a unicode object containing tree in serialized forms.

	tree can be any object with a render method or some sort of string.
	If it's a byte string, it must not contain any non-ASCII.

	If prolog is given, it must be a string that will be prepended to the
	serialization of tree.  The way ElementTree currently is implemented,
	you can use this for xml declarations or stylesheet processing 
	instructions.
	"""
	if hasattr(tree, "render"):
		res = tree.render(emptyPrefix=emptyPrefix)
	elif hasattr(tree, "getchildren"):  # hopefully an xml.etree Element
		res = ElementTree.tostring(tree)
	elif isinstance(tree, str):
		res = unicode(tree)
	elif isinstance(tree, unicode):
		res = tree
	else:
		raise ValueError("Cannot render %s"%repr(tree))
	if prolog:
		res = prolog+res
	return res
