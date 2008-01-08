"""
This module contains various helper functions and classes for processing
GAVO resources.
"""

import copy
import datetime
import math
import os
import re
import shutil
import sys
import tempfile
import time

from xml.sax.handler import ContentHandler

from mx import DateTime

from twisted.python.failure import Failure

import gavo
from gavo import logger


class Error(gavo.Error):
	pass


def _iterDerivedClasses(baseClass, objects):
	"""iterates over all subclasses of baseClass in the sequence objects.
	"""
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				yield cand
		except TypeError:  # issubclass wants a class
			pass


def buildClassResolver(baseClass, objects, instances=False):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to support static getName methods.

	objects would usually be something like globals().values()

	If instances is True the function will return instances instead
	of classes.
	"""
	registry = {}
	for cls in _iterDerivedClasses(baseClass, objects):
		if instances:
			registry[cls.getName()] = cls()
		else:
			registry[cls.getName()] = cls
	def resolve(name, registry=registry):
		return registry[name]
	return resolve


def formatDocs(docItems, underliner):
	"""returns RST-formatted docs for docItems.

	docItems is a list of (title, doc) tuples.  doc is currently
	rendered in a preformatted block.
	"""
	def formatDocstring(docstring):
		"""returns a docstring with a consistent indentation.

		Rule (1): any whitespace in front of the first line is discarded.
		Rule (2): if there is a second line, any whitespace at its front
		  is the "governing whitespace"
		Rule (3): any governing whitespace in front of the following lines
		  is removed
		Rule (4): All lines are indented by 2 blanks.
		"""
		lines = docstring.split("\n")
		newLines = [lines.pop(0).lstrip()]
		if lines:
			whitespacePat = re.compile("^"+re.match(r"\s*", lines[0]).group())
			for line in lines:
				newLines.append(whitespacePat.sub("", line))
		return "  "+("\n  ".join(newLines))

	docLines = []
	for title, body in docItems:
		docLines.extend([title, underliner*len(title), "", "::", "",
			formatDocstring(body), ""])
	docLines.append("\n.. END AUTO\n")
	return "\n".join(docLines)


def makeClassDocs(baseClass, objects):
	"""prints hopefully RST-formatted docs for all subclasses
	of baseClass in objects.

	The function returns True if it finds arguments it expects ("docs"
	and optionally a char to build underlines from) in the command line,
	False if not (and it doesn't print anything in this case) if not.

	Thus, you'll usually use it like this:

	if __name__=="__main__":	
		if not utils.makeClassDocs(Macro, globals().values()):
			_test()
	"""
	if len(sys.argv) in [2,3] and sys.argv[1]=="docs":
		if len(sys.argv)==3:
			underliner = sys.argv[2][0]
		else:
			underliner = "."
	else:
		return False
	docs = []
	for cls in _iterDerivedClasses(baseClass, objects):
		try:
			title = cls.getName()
		except AttributeError:
			title = cls.__name__
		docs.append((title, cls.__doc__))
	docs.sort()
	print formatDocs(docs, underliner)
	return True


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


class NodeBuilder(ContentHandler):
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
		raise raiseTb(gavo.Error, msg)
	
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
			children = self._cleanTextNodes(children)
			newNode = getattr(self, "_make_"+name)(name, attrs, children)
			if newNode!=None:
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

	def getContent(self, children):
		"""returns the entire text content of the node in a string.

		This proabably won't do what you want in mixed-content models.
		"""
		return "".join([n[1] for n in children if n[0]==None]).strip()

	def _cleanTextNodes(self, children):
		"""joins adjacent text nodes and prunes whitespace-only nodes.
		"""
		cleanedChildren, text = [], []
		for type, node in children:
			if type==None:
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
				if not ignoreUnknownElements:
					raise Error("%s elements may not have %s children"%(
						name, childName))
		return parent


class DummyClass:
	"""is a class that just prints out all method calls with their arguments.

	>>> l = DummyClass()
	Dummy class instantiated: () {}
	>>> l.foo()
	Called foo, (), {}
	>>> l.baz(1, 2, 3)
	Called baz, (1, 2, 3), {}
	>>> l.bar(2, val=3)
	Called bar, (2,), {'val': 3}
	"""
	def __init__(self, *args, **kwargs):
		print "Dummy class instantiated:", args, kwargs

	def __getattr__(self, key):
		return lambda *args, **kwargs: sys.stdout.write("Called %s, %s, %s\n"%(
			key, args, kwargs))


class Conversions:
	"""is a container for converters from parsed literals to python
	values.

	A converter has the signature

	convert_to_type(val) -> val_of_type

	It must be a no-op if val already has type.  They should accept
	strings as val, and they must return a value of their promised
	type or raise an exception.

	We should support the standard VOTable types here.  XXX missing:
	bit, range checking for integer types, complex numbers XXX

	In addition, we do Strings (XXX think about distinction of
	unicode and bytestrings).

	This is a singleton class that should not be instanciated but
	instead be accessed through the convert class method.

	The conversions themselves are used without binding, thus no "self"
	argument.
	"""
	def _convertToFloat(val):
		if val.startswith("+"):
			val = val[1:]
		return float(val.replace(" ", ""))

	def _convertToInt(val):
		return int(val)
	
	def _convertToBoolean(val):
		return bool(val)

	def _convertToString(val):
		return str(val)

	def _convert(self, type, val, nullvalue):
		if val==nullvalue:
			return None
		else:
			return self.registry[type](val)

	@classmethod
	def convert(cls, targetType, val, nullvalue):
		instance = cls()
		cls.convert = instance._convert
		return instance.convert(targetType, val, nullvalue)

	registry = {
		"float": _convertToFloat,
		"double": _convertToFloat,
		"int": _convertToInt,
		"short": _convertToInt,
		"long": _convertToInt,
		"unsignedByte": _convertToInt,
		"str": _convertToString,
	}


class NameMap:
	"""is a name mapper fed from a simple text file.

	The text file format simply is:

	<target-id> "TAB" <src-id>{whitespace <src-id>}

	src-ids have to be encoded quoted-printable when they contain whitespace
	or other "bad" characters ("="!).  You can have #-comments and empty
	lines.
	"""
	def __init__(self, src):
		self._parseSrc(src)
	
	def _parseSrc(self, src):
		self.namesDict = {}
		try:
			for ln in open(src).readlines():
				if ln.startswith("#") or not ln.strip():
					continue
				ob, names = re.split("\t+", ln)
				for name in names.lower().split():
					self.namesDict[name.decode("quoted-printable")] = ob
		except ValueError:
			raise gavo.Error("Syntax error in %s: Line %s not understood."%(
				src, repr(ln)))
	
	def resolve(self, name):
		return self.namesDict[name.lower()]


def degToRad(deg):
	"""returns the angle deg (in degrees) in radians.
	"""
	return deg/360.*2*math.pi


def radToDeg(rad):
	"""returns the angle rad (in radians) in degrees.
	"""
	return rad/2./math.pi*360


def silence(fun, *args, **kwargs):
	"""executes fun(*args, **kwargs) with stdout redirected to /dev/null.

	This would be a classic for context managers once we have python 2.5.

	This is necessary to shut up silly output from libraries like pyparsing
	and pyfits.
	"""
	realstdout = sys.stdout
	sys.stdout = open("/dev/null", "w")
	try:
		res = fun(*args, **kwargs)
	finally:
		sys.stdout.close()
		sys.stdout = realstdout
	return res


def getMatchingTuple(tupList, key, matchIndex):
	"""returns the first tuple from tupList that hat tuple[matchIndex]=key.
	"""
	for t in tupList:
		if t[matchIndex]==key:
			return t
	raise KeyError(key)


def raiseTb(exCls, msg, *args):
	"""raises an exception exCls(*args) furnished with the current traceback

	This is supposed to be used when re-raising exceptions.  It's bad that
	this function shows up in the traceback, but without macros, there's
	little I can do about it.

	msg may be a twisted Failure instance.  In that case, the traceback
	and the message are taken from it.
	"""
	if isinstance(msg, Failure):
		raise exCls, (msg.getErrorMessage(),)+args, msg.tb
	else:
		raise exCls, (msg,)+args, sys.exc_info()[-1]


def getErrorField():
	"""returns the field attribute of the current exception or "<unknown>"
	if it does not have one.

	This is for use when re-raising gavo.ValidationErrors.
	"""
	_, val, _ = sys.exc_info()
	return getattr(val, "fieldName", "<unknown>")


def getRelativePath(fullPath, rootPath):
	"""returns rest if fullPath has the form rootPath/rest and raises an
	exception otherwise.
	"""
	if not fullPath.startswith(rootPath):
		raise Error("Full path %s does not start with resource root %s"%
			(fullPath, rootPath))
	return fullPath[len(rootPath):].lstrip("/")


def runInSandbox(setUp, func, tearDown, *args, **kwargs):
	"""runs func in a temporary ("sandbox") directory.

	func is called with args and kwargs.  setUp and tearDown are
	two functions also called with args and kwargs; in addition, they
	are passed the path of the tempdir (setUp) or the path of the
	original directory (teardown) in the first argument.
	
	setUp is called after the directory has been created,
	but the process is still in the current WD.
	
	tearDown is called before the temp dir is deleted and in this directory.
	Its return value is the return value of runInSandbox, which is the
	preferred way of getting data out of the sandbox.

	If any of the handlers raise exceptions, the following handlers will not
	be called.  The sandbox will be torn down, though.
	"""
	owd = os.getcwd()
	wd = tempfile.mkdtemp("sandbox")
	try:
		if setUp:
			setUp(wd, *args, **kwargs)
		os.chdir(wd)
		func(*args, **kwargs)
		result = tearDown(owd, *args, **kwargs)
	finally:
		os.chdir(owd)
		shutil.rmtree(wd)
	return result


def _test():
	import doctest, utils
	doctest.testmod(utils)


if __name__=="__main__":
	_test()
