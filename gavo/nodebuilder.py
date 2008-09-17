"""
NodeBuilders are convenient mechanisms to parse XML.
"""

import re
import sys
import traceback
from xml.sax.handler import ContentHandler

import gavo

class Error(gavo.Error):
	pass


class StartEndHandler(ContentHandler):
	"""is a ContentHandler that translates certain Sax events to method
	calls.

	When an opening tag is seen, we look of a _start_<element name>
	method and, if present, call it with the name and the attributes. 
	When a closing tag is seen, we try to call _end_<element name> with
	name, attributes and contents.	If the _end_xxx method returns a
	string (or similar), this value will be added to the content of the
	enclosing element.

	Both startElement and endElement try to call a _default(Start|End)
	method if no specific handler is found.  You *may* want to use
	them for primitive input validation (no unknown tags), but you'll
	probably be better off by using external validation.

	If you need to process namespaces, you'll need to override the
	cleanupName method (the default nukes namespaces).  The trouble
	here is that you'll have to figure out a way to do name munging, 
	because colons are not allowed in python names.
	"""
	def __init__(self):
		ContentHandler.__init__(self)
		self.elementStack = []
		self.contentsStack = [[]]

	def cleanupName(self, name, 
			cleanupPat=re.compile(".*:")):  #Nuke namespaces
		return cleanupPat.sub("", name).replace("-", "_")

	def startElement(self, name, attrs):
		self.contentsStack.append([])
		name = self.cleanupName(name)
		self.elementStack.append((name, attrs))
		if hasattr(self, "_start_%s"%name):
			getattr(self, "_start_%s"%name)(name, attrs)
		elif hasattr(self, "_defaultStart"):
			self._defaultStart(name, attrs)

	def endElement(self, name):
		contents = "".join(self.contentsStack.pop())
		name = self.cleanupName(name)
		_, attrs = self.elementStack.pop()
		res = None
		if hasattr(self, "_end_%s"%name):
			res = getattr(self,
				"_end_%s"%name)(name, attrs, contents)
		elif hasattr(self, "_defaultEnd"):
			res = self._defaultEnd(name, attrs, contents)
		if isinstance(res, basestring):
			self.contentsStack[-1].append(res)

	def characters(self, chars):
		self.contentsStack[-1].append(chars)


class NamedNode:
	"""is a helper class for NodeBuilder to change node names from
	handling functions.
	"""
	def __init__(self, name, node):
		self.name, self.node = name, node


class BaseNodeBuilder(ContentHandler):
	"""a node builder is a content handler working more along the lines
	of conventional parse tree builders.

	This means that for every element we want handled, there is a method
	_make_<elementname>(name, attrs, children) that receives the name
	of the element (so you can reuse implementations for elements
	behaving analogously), the attributes of the element and a list
	of children.  The children come in a list of tuples (name, content),
	where name is the element name and content is whatever the _build_x
	method returned for that element.  Text nodes have a name of None.

	NodeBuilders support a limited id/idref mechanism.  Nodes with
	id will get entered in a dictionary and can be retrieved
	(as name/node pairs) via getById.  However, this only is
	possible after the element with the id has been closed.  There
	is no forward declaration.

	In general, text children are deleted when they are whitespace only,
	and they are joined to form a single one.  However, you can define
	a set keepWhitespaceNames containing the names of elements for
	which this is not wanted.

	In some cases, you want parents provide information to their children
	while they are constructed.  This is a bit clumsy, but for such cases,
	you can define a _start_<element> method that can leave something
	in a dictionary through the pushProperty method that can be retrieved
	by children through the getProperty method.  When constructing the
	parent node, you must call popProperty on this.

	As an added hack, you can register nodes for addition to the nearest
	enclosing element of a type via registerDelayedChildren.  This is
	provided to allow methods change the tree higher up if necessary;
	in the context of gavo, this is used by interfaces.  Here's an
	example:  You have <foo><bar><baz/></bar></foo>, and the handler
	for baz decides it wants to have a Bla sibling.  It can then
	call registerDelayedChild("bar", Bla()).

	On errors during node construction, the class will call a handleError
	method with a sys.exc_info tuple.
	"""
	keepWhitespaceNames = set()

	def __init__(self):
		ContentHandler.__init__(self)
		self.elementStack = []
		self.childStack = [[]]
		self.delayedChildren = {}
		self.properties = {}
		self.locator = None
		self.elementsById = {}

	def registerDelayedChild(self, parentName, child, atfront=False):
		"""adds child for addition to the next enclosing parentName element.
		"""
		if not self.delayedChildren.has_key(parentName):
			self.delayedChildren[parentName] = ([], [])
		if atfront:
			self.delayedChildren[parentName][0].append(child)
		else:
			self.delayedChildren[parentName][1].append(child)

	def pushProperty(self, propName, value):
		"""makes value available to node constructors under the name propName.

		It is recommended to use <element>.<name> as propname.
		"""
		self.properties.setdefault(propName, []).append(value)
	
	def popProperty(self, propName):
		"""retrieves (and removes) the last value pushed as propName.
		"""
		return self.properties[propName].pop()
	
	def getProperty(self, propName):
		"""returns the current value of the property propName.

		Non-existing properties will be signalled by raising an IndexError.
		"""
		try:
			return self.properties[propName][-1]
		except (IndexError, KeyError):
			raise IndexError("Property %s is not set"%propName)
	
	def handleError(self, exc_info):
		msg = ("Error while parsing XML at"
			" %d:%d (%s)"%(self.locator.getLineNumber(), 
				self.locator.getColumnNumber(), exc_info[1]))
		raise gavo.raiseTb(gavo.Error, msg)
	
	def setDocumentLocator(self, locator):
		self.locator = locator

	def startElement(self, name, attrs):
		self.elementStack.append((name, attrs))
		self.childStack.append([])
		if hasattr(self, "_start_"+name):
			getattr(self, "_start_"+name)(name, attrs)

	def _enterNewNode(self, name, attrs, newNode):
			if isinstance(newNode, NamedNode):
				newChild = (newNode.name, newNode.node)
			else:
				newChild = (name, newNode)
			self.childStack[-1].append(newChild)
			if attrs.has_key("id"):
				if attrs["id"] in self.elementsById:
					raise Error("Duplicate id: %s"%attrs["id"])
				self.elementsById[attrs["id"]] = newChild

	def endElement(self, name):
		_, attrs = self.elementStack.pop()
		try:
			children = self.childStack.pop()
			if self.delayedChildren.has_key(name):
				children[:0] = self.delayedChildren[name][0]
				children.extend(self.delayedChildren[name][1])
				del self.delayedChildren[name]
			if name not in self.keepWhitespaceNames:
				children = self._cleanTextNodes(children)
			newNode = getattr(self, "_make_"+name)(name, attrs, children)
			if newNode is not None:
				self._enterNewNode(name, attrs, newNode)
		except:
			self.handleError(sys.exc_info())

	def characters(self, content):
		self.childStack[-1].append((None, content))

	def getById(self, id):
		return self.elementsById[id]

	def getResult(self):
		return self.childStack[0][0][1]
	
	def getNodesDict(self, children):
		"""returns children as a dictionary of lists.

		children is a list of the type passed to the _make_xxx methods.
		"""
		res = {}
		for name, val in children:
			res.setdefault(name, []).append(val)

	def getContentWS(self, children):
		"""returns the entire text content of the node in a string without doing
		whitespace normalization.
		"""
		return "".join([n[1] for n in children if n[0] is None])

	def getContent(self, children):
		"""returns the entire text content of the node in a string.

		This probably won't do what you want in mixed-content models.
		"""
		return self.getContentWS(children).strip()

	def getWaitingChild(self, nodeName, maxLevels=100, startLevel=-1):
		"""returns the first child with nodeName waiting to be adopted in the
		childStack.

		maxLevels gives a maximum number of childStack levels we descend
		before giving up.

		If no matching child can be found, a NoWaitingChild exception is raised.
		"""
		if maxLevels==0:
			raise NoWaitingChild(nodeName)
		for name, element in self.childStack[startLevel]:
			if name==nodeName:
				return element
		return getWaitingChild(nodeName, maxLevels-1, startLevel-1)

	def _cleanTextNodes(self, children):
		"""joins adjacent text nodes and prunes whitespace-only nodes.
		"""
		cleanedChildren, text = [], []
		for type, node in children:
			if type is None:
				text.append(node)
			else:
				if text:
					chars = "".join(text)
					if chars.strip():
						cleanedChildren.append((None, chars))
					text = []
				cleanedChildren.append((type, node))
		chars = "".join(text)
		if chars.strip():
			cleanedChildren.append((None, chars))
		return cleanedChildren

	def filterChildren(self, children, targetNode):
		"""returns a list of children that are of type targetNode, and a
		list of all other children.
		"""
		return [child for child in children if child[0]==targetNode
			], [child for child in children if child[0]!=targetNode]

	def _processChildren(self, parent, name, childMap, children, 
			ignoreUnknownElements=False):
		"""adds children to parent.

		Parent is some class (usually a record.Record instance),
		childMap maps child names to methods to call the children with,
		and children is a sequence as passed to the _make_xxx methods.

		The function returns parent for convenience.
		"""
		for childName, val in children:
			try:
				childMap[childName](val)
			except KeyError:
				traceback.print_exc()
				if not ignoreUnknownElements:
					raise Error("%s elements may not have %s children"%(
						name, childName))
		return parent


class NodeBuilder(BaseNodeBuilder):
	"""is a BaseNodeBuilder that in addition knows how to handle 
	ElementGenerators.

	An ElementGenerator is a python generator that yields element descriptions.
	Each item yielded can be:

	* a tuple ("start", <Element Name>, <attributes>)
	* a tuple ("end", <Element Name>)
	* a tuple ("empty", <Element Name>, <attributes>)
	* a tuple ("addChild", (<ElementName, DOM node>))
	* string (which is delivered as character data)
	"""
	def _makeGenerator(self, code):
		try:
			exec "def gen():\n%s\n"%code in locals()
		except SyntaxError, msg:
			raise gavo.Error("Bad ElementGenerator source %s: %s"%(code, msg))
		return gen

	knownActions = set(["start", "end", "empty", "addChild"])

	def _handleTupleItem(self, tuple):
		action = tuple[0]
		if not action in self.knownActions:
			raise Error("Bad action from element generator: %s"%action)
		if action=="start" or action=="empty":
			self.startElement(tuple[1], tuple[2])
		if action=="end" or action=="empty":
			self.endElement(tuple[1])
		if action=="addChild":
			self.childStack[-1].append(tuple[1])

	def _make_ElementGenerator(self, name, attrs, children):
		generator = self._makeGenerator(children[0][1])
		self.runGenerator(generator())
	
	def runGenerator(self, generator):
		for item in generator:
			if isinstance(item, basestring):
				self.characters(item)
			elif isinstance(item, tuple) and len(item)>0:
				self._handleTupleItem(item)
			else:
				raise Error("Bad item from element generator: %s"%repr(item))
