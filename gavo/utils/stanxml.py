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
# We do not want cElementTree here since it doesn't have the _namespaceMap
# we need to cope with shitty namespaced attribute values.
#	try:
#		import cElementTree as ElementTree
#	except ImportError:


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


class Element(object):
	"""is an element for serialization into XML.

	This is loosely modelled after nevow stan.

	Don't access the children attribute directly.  I may want to add
	data model checking later, and that would go into addChild.

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

	def __init__(self, **kwargs):
		self.children = []
		if self.name is None:
			self.name = self.__class__.__name__.split(".")[-1]
		self(**kwargs)

	def bailIfBadChild(self, child):
		if (self.childSequence is not None and 
				getattr(child, "name", None) not in self.allowedChildren and
				type(child) not in self.allowedChildren):
			raise ChildNotAllowed("No %s children in %s"%(child.name, self.name))

	def addChild(self, child):
		"""adds child to the list of children.

		Child may be an Element, a string, or a list or tuple of Elements and
		strings.  Finally, child may be None, in which case nothing will be
		added.
		"""
		if hasattr(child, "serializeToXMLStan"):
			self.children.append(child.serializeToXMLStan())
		elif child is None:
			pass
		elif isinstance(child, (basestring, Element)):
			self.bailIfBadChild(child)
			self.children.append(child)
		elif isinstance(child, (list, tuple)):
			for c in child:
				self.addChild(c)
		elif isinstance(child, _Autoconstructor):
			self.children.append(child())
		elif self.stringifyContent:
			self.children.append(str(child))
		else:
			raise Error("%s element %s cannot be added to %s node"%(
				type(child), repr(child), self.name))

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
			attname = "a_"+k
			# Only allow setting attributes already present
			getattr(self, attname)
			setattr(self, attname, v)
		return self

	def __iter__(self):
		raise NotImplementedError, "Element instances are not iterable."

	def isEmpty(self):
		if self.mayBeEmpty:  # We definitely want this item rendered.
			return False
		for c in self.children:
			if isinstance(c, basestring):
				if c.strip():
					return False
			elif not c.isEmpty():
				return False
		return True

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

	def _makeAttrDict(self):
		res = {}
		for name, attName in self.iterAttNames():
			if getattr(self, name) is not None:
				res[attName] = str(getattr(self, name))
		return res

	def getFirstChildOfType(self, type):
		"""returns the first child that is an instance of type, or None if there
		is no such child.
		"""
		for c in self.children:
			if isinstance(c, type):
				return c

	def makeChildDict(self):
		cDict = {}
		textContent = []
		for c in self.children:
			if isinstance(c, basestring):
				textContent.append(c)
			else:
				cDict.setdefault(c.name, []).append(c)
		return cDict, "".join(textContent)

	def _addChildrenAsIs(self, node):
		for child in self.children:
			if isinstance(child, basestring):
				node.text = child
			else:
				child.asETree(node)

	def _addChildrenInSequence(self, node):
		cDict, text = self.makeChildDict()
		node.text = text
		for cName in self.childSequence:
			if cName in cDict:
				for c in cDict[cName]:
					c.asETree(node)

	def getElName(self):
		"""returns the tag name of this element.

		This will be an ElementTree.QName instance unless the element is
		local.
		"""
		if self.local or isinstance(self.name, ElementTree.QName):
			return self.name
		else:
			return ElementTree.QName(self.namespace, self.name)

	def asETree(self, parent=None):
		"""returns an ElementTree instance for this node.
		"""
		try:
			if not self.mayBeEmpty and self.isEmpty():
				return
			
			elName = self.getElName()
			attrs = self._makeAttrDict()
			if parent is None:
				node = ElementTree.Element(elName, attrs)
			else:
				node = ElementTree.SubElement(parent, elName, attrs)

			if self.childSequence is None:
				self._addChildrenAsIs(node)
			else:
				self._addChildrenInSequence(node)
			return node
		except Error:
			raise
		except Exception, msg:
			msg.args = (unicode(msg)+(" while building %s node"
				" with children %s"%(self.name, self.children)),)+msg.args[1:]
			raise
	
	def render(self):
		et = self.asETree()
		if et is None:
			return ""
		return ElementTree.tostring(et)
