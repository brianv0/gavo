"""
A stan-like model for building namespaced XML trees.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

try:
	from xml.etree import ElementTree
except ImportError:
	from elementtree import ElementTree
# cElementTree has no _namespaceMap that we need to cope with shitty 
# namespaced attribute values where XSD nightmares rule.  Elsewhere,
# we can use it:
try:
	from xml.etree import cElementTree as FastElementTree
except ImportError:
	FastElementTree = ElementTree


class Error(Exception):
	pass


class ChildNotAllowed(Error):
	pass


encoding = "utf-8"
XML_HEADER = '<?xml version="1.0" encoding="%s"?>'%encoding

# That bugger is never defined and has a fixed map to xsi
XSINamespace = "http://www.w3.org/2001/XMLSchema-instance"
ElementTree._namespace_map[XSINamespace] = "xsi"


class _Autoconstructor(type):
	"""is a metaclass that constructs an instance of itself on getitem.

	We want this so we save a parentheses pair on Elements without
	attributes.
	
	As an added feature, it also checks for an attribute childSequence
	on construction.  If it is present, it generates an allowedChildren
	attribute from it.
	"""
	def __init__(cls, name, bases, dict):
		type.__init__(cls, name, bases, dict)
		if hasattr(cls, "childSequence") and cls.childSequence is not None:
			cls.allowedChildren = set(cls.childSequence)
		else:
			cls.childSequence = None

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
	name = "stub"
	text = None

	def __init__(self, dest):
		self.dest = dest
	
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


class Element(object):
	"""An element for serialization into XML.

	This is loosely modelled after nevow stan.

	Don't add to the children attribute directly, use addChild or (more
	usually) __getitem__

	When deriving from Elements, you may need attribute names that are not
	python identifiers (e.g., with dashes in them).  In that case, define
	an attribute <att>_name and point it to any string you want as the
	attribute.

	When building an ElementTree out of this, empty elements (i.e. those
	having an empty text and having no non-empty children) are usually
	discarded.  If you need such an element (e.g., for attributes), set
	mayBeEmpty to True.

	Since insane XSD mandates that local elements must not be qualified when
	elementFormDefault is unqualified, you need to set local=True on
	such local elements to suppress the namespace prefix.  Attribute names
	are never qualified here.  If you need qualified attributes, you'll
	have to use attribute name translation.

	Local elements like this will only work properly if you give the parent 
	elements the appropriate xmlns attribute.

	The contents of the DOM may be anything recognized by addChild.
	In particular, you can give objects a serializeToXMLStan method returning
	strings or an Element to make them good DOM citizens.

	Elements cannot harbour mixed content (or rather, there is only
	one piece of text).
	"""
	__metaclass__ = _Autoconstructor

	name = None
	a_id = None
	namespace = ""
	mayBeEmpty = False
	stringifyContent = False
	local = False

	a_xsi_type = None
	xsi_type_name = "xsi:type"

	# for type dispatching in addChild.
	_generator_t = type((x for x in ()))

	def __init__(self, **kwargs):
		self.__isEmpty = None
		self.children = []
		self.text = ""
		if self.name is None:
			self.name = self.__class__.__name__.split(".")[-1]
		self(**kwargs)

	def __getitem__(self, children):
		self.addChild(children)
		return self

	def __call__(self, **kw):
		if not kw:
			return self
		
		for k, v in kw.iteritems():
			if k[-1] == '_':
				k = k[:-1]
			elif k[0] == '_':
				k = k[1:]
			elif ":" in k:  # ignore namespaced attributes for now
				continue
			attname = "a_"+k
			# Only allow setting attributes already present
			getattr(self, attname)
			setattr(self, attname, v)
		return self

	def __iter__(self):
		raise NotImplementedError, "Element instances are not iterable."

	def __nonzero__(self):
		return self.isEmpty()

	def bailIfBadChild(self, child):
		if (self.childSequence is not None and 
				getattr(child, "name", None) not in self.allowedChildren and
				type(child) not in self.allowedChildren):
			raise ChildNotAllowed("No %s children in %s"%(
				getattr(child, "name", "text"), self.name))

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
			self.text = child
		elif isinstance(child, (Element, Stub)):
			self.bailIfBadChild(child)
			self.children.append(child)
		elif isinstance(child, (list, tuple, self._generator_t)):
			for c in child:
				self.addChild(c)
		elif isinstance(child, _Autoconstructor):
			self.addChild(child())
		elif self.stringifyContent:
			self.addChild(unicode(child))
		else:
			raise Error("%s element %s cannot be added to %s node"%(
				type(child), repr(child), self.name))

	def isEmpty(self):
		if self.__isEmpty is None:
			self.__isEmpty = True
			if self.mayBeEmpty or self.text.strip():
				self.__isEmpty = False
			else:
				for c in self.children:
					if not c.isEmpty():
						self.__isEmpty = False
						break
		return self.__isEmpty

	def iterAttNames(self):
		"""iterates over the defined attribute names of this node.
		
		Each element returned is a pair of the node attribute name (always
		starting with a_) and the xml name (which may include a namespace
		prefix).
		"""
		for name in dir(self):
			if name.startswith("a_"):
				xmlName = getattr(self, name[2:]+"_name", name[2:])
				yield name, xmlName

	def iterChildrenOfType(self, type):
		"""iterates over all children having type.
		"""
		for c in self.children:
			if isinstance(c, type):
				yield c

	def makeChildDict(self):
		cDict = {}
		for c in self.children:
			cDict.setdefault(c.name, []).append(c)
		return cDict

	def getElName(self):
		"""returns the tag name of this element.

		This will be an ElementTree.QName instance unless the element is
		local.
		"""
		if self.local or isinstance(self.name, ElementTree.QName):
			return self.name
		else:
			return ElementTree.QName(self.namespace, self.name)

	def traverse(self, visitor):
		"""calls visitor(name, text, attrs, childIter).

		This doesn't actually traverse; the expectation is that visitor
		does something like (c.traverse(visitor) for c in childIter).
		"""
		try:
			if self.isEmpty():
				return
			elName = self.getElName()
			attrs = self._makeAttrDict()
			if self.childSequence is None:
				childIter = iter(self.children)
			else:
				childIter = self._iterChildrenInSequence()
			return visitor(self.getElName(), self.text,
				self._makeAttrDict(), childIter)
		except Error:
			raise
		except Exception, msg:
			msg.args = (unicode(msg)+(" while building %s node"
				" with children %s"%(self.name, self.children)),)+msg.args[1:]
			raise

	def asETree(self):
		"""returns an ElementTree instance for the tree below this node.
		"""
		return self.traverse(self._eTreeVisitor)

	def render(self):
		et = self.asETree()
		if et is None:
			return ""
		return ElementTree.tostring(et)

	def _makeAttrDict(self):
		res = {}
		for name, attName in self.iterAttNames():
			if getattr(self, name) is not None:
				res[attName] = str(getattr(self, name))
		return res

	def _iterChildrenInSequence(self):
		cDict = self.makeChildDict()
		for cName in self.childSequence:
			if cName in cDict:
				for c in cDict[cName]:
					yield c

	def _eTreeVisitor(self, elName, content, attrDict, childIter):
		"""helps asETree.
		"""
		node = ElementTree.Element(elName, **attrDict)
		if content:
			node.text = content
		for child in childIter:
			childNode = child.traverse(self._eTreeVisitor)
			if childNode is not None:
				node.append(childNode)
		return node


def schemaURL(xsdName):
	"""returns the URL to the local mirror of the schema xsdName.

	This is used by the various xmlstan clients to make schemaLocations.
	"""
	return "http://vo.ari.uni-heidelberg.de/docs/schemata/"+xsdName


def xmlrender(tree):
	"""returns a unicode object containing tree in serialized forms.

	tree can be any object with a render method or some sort of string.
	If it's a byte string, it must not contain any non-ASCII.
	"""
	if hasattr(tree, "render"):
		return tree.render()
	elif isinstance(tree, str):
		return unicode(tree)
	elif isinstance(tree, unicode):
		return tree
	else:
		raise ValueError("Cannot render %s"%repr(tree))
