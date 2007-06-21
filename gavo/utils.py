"""
This module contains various helper functions and classes for processing
GAVO resources.
"""

import sys
import re
import weakref
from xml.sax.handler import ContentHandler
import math

import gavo
from gavo import logger


class RequiredField:
	"""is a sentinel class used to signal a defaultless field must be set
	for a class to become valid.

	Required fields have not defaults.  A Record is not valid if no
	value has been assigned to a RequiredField, and using such a
	record will raise AttributeErrors oder KeyErrors.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class ComputedField:
	"""is a sentinel class used to signal a field that cannot be written
	to.

	A computed field has no memory in a Record's data store.  It just
	exists in a method get_<key> that is provided by the class inheriting
	from Record.  In other words, having a ComputedField in legalKeys
	is just a declaration that the subclass defines a get_key method.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class ListField:
	"""is a sentinel class to signal a field that is a list and cannot
	be assigned, just added to.

	List fields have no setter. They have a getter returning a list, and
	an addto_<key> method that appends data to the list.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class BooleanField:
	"""is a sentinel class to signal a field that only takes 
	boolean values, defaulting to False.

	The setters of boolean fields parse true, false, yes, no, on, off
	in any capitalization to booleans.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class TrueBooleanField:
	"""is a sentinel class to signal a field that only takes 
	boolean values, defaulting to True.

	The setters of boolean fields parse true, false, yes, no, on, off
	in any capitalization to booleans.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class Record(object):
	"""is a container for structured data.

	The structure is, well, that of a dictionary.  However, Records
	know which keys are legal and which are even required.	Also,
	classes deriving from record may set "setters" (called set_<name>)
	and "getters" (called get_<name>) for certain keys to do some
	computation.  They may directly access the dataStore dictionary
	If they don't, the getters and setters are just the dictionary
	getters and setters.

	Records are constructed with a dictionary legalKeys, the keys
	of which give the fields of the records.  The value for a key
	may have a magic value, which always is a class as defined above
	(RequiredField, ComputedField ListField).  Otherwise, this value
	is used as a default.

	You access the fields of the record through get_<name> and
	set_<name>.  This may raise an AttributeError if you try to set
	or get a field not defined at construction time or a KeyError
	if you try to get a non-default field that has not yet been set.

	Alternatively, you can use the set and get methods.  Their
	interface is identical to the [sg]et_<name> methods (except
	for the additional key, of course), that is, illegal keys raise
	AttributeErrors.

	>>> r = Record({"a": 7, "b": [4, 4], "c": RequiredField})
	>>> r.get_a()
	7
	>>> r.get_c()
	Traceback (most recent call last):
	KeyError: 'c'
	>>> r.get_anything()
	Traceback (most recent call last):
	AttributeError: 'Record' object has no attribute 'get_anything'
	"""
	def __init__(self, legalKeys, initvals={}):
		self.dataStore = {}
		self.specialTypeHandlers = {
			ComputedField: lambda key, val: [],
			ListField: self._getListMethods,
			BooleanField: self._getBooleanMethods,
			TrueBooleanField: self._getBooleanMethods,
		}
		self.keys = legalKeys
		for key, default in self.keys.iteritems():
			self._createMethods(key, default)
		for key, value in initvals.iteritems():
			self.set(key, value)

	def __str__(self):
		return "<%s %s>"%(self.__class__.__name__, str(self.dataStore))
	
	def __repr__(self):
		return "<%s %s>"%(self.__class__.__name__, str(self.dataStore)[:30])

	def _createMethods(self, key, value):
		for prefix, callable in self.specialTypeHandlers.get(
				value, self._getAtomicMethods)(key, value):
			if not hasattr(self, prefix+key):
				setattr(self, prefix+key, callable)

	def _getAtomicMethods(self, key, default):
		"""returns methods to manage normal atomic attributes.
		"""
		if default is not RequiredField:
			self.dataStore[key] = default
		def getter():
			return self.dataStore[key]
		def setter(value):
			self.dataStore[key] = value
		return [("get_", getter), ("set_", setter)]

	def _getListMethods(self, key, _):
		self.dataStore[key] = []
		def getter():
			return self.dataStore[key]
		def adder(value):
			self.dataStore[key].append(value)
		return [("get_", getter), ("addto_", adder)]

	def _getBooleanMethods(self, key, default):
		if default is BooleanField:
			self.dataStore[key] = False
		elif default is TrueBooleanField:
			self.dataStore[key] = True
		else:
			assert(False)
		def setter(value):
			if isinstance(value, bool):
				self.dataStore[key] = value
			else:
				if value.lower() in ["true", "yes", "on"]:
					self.dataStore[key] = True
				elif value.lower() in ["false", "no", "off"]:
					self.dataStore[key] = False
				else:
					raise Error("%s is an invalid expression for a boolean"%value)
		def getter():
			return self.dataStore[key]
		return [("get_", getter), ("set_", setter)]

	def isValid(self):
		"""returns true if all mandatory (non-default) fields have been set.
		"""
		for key, default in self.keys.iteritems():
			if default==RequiredField and not self.dataStore.has_key(key):
				return False
		return True

	def get(self, key):
		getattr(self, "get_"+key)()
	
	def set(self, key, value):
		getattr(self, "set_"+key)(value)


def _buildClassResolver(baseClass, objects):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to support static getName methods.

	objects would usually be something like globals().values()
	"""
	registry = {}
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				registry[cand.getName()] = cand
		except TypeError:  # issubclass wants a class
			pass
	def resolve(name, registry=registry):
		return registry[name]
	return resolve


def fatalError(message, exc_info=True):
	logger.critical(message, exc_info=exc_info)
	sys.exit("Fatal: %s"%message)


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
	"""is a container for converters from parsed literals to real
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


def _test():
	import doctest, utils
	doctest.testmod(utils)


if __name__=="__main__":
	_test()
