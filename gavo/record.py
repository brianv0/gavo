"""
This module defines the Record class, a general class providing
(somewhat) controlled attribute access.  It's used within gavo
when stuff is parsed.
"""


import new
import copy

import gavo


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
	"""is a sentinel class to signal a field that is a list and
	cannot be assigned, just added to.

	They have a getter returning a list, and an addto_<key> method
	that appends data to the list.

	Do not instantiate it.	Instances of the class are *never* used.
	"""
	pass


class DictField:
	"""is a sentinel class to signal a "registry field".

	Registries are really dicts.  You have a register_<key> method taking
	a name and a value, and a get_<key> method returning the value for
	a key.  get_<key> returns an empty string for non-existing keys.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class BooleanField:
	"""is a sentinel class to signal a field that only takes 
	boolean values, defaulting to False.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class TrueBooleanField:
	"""is a sentinel class to signal a field that only takes 
	boolean values, defaulting to True.

	Do not instantiate it.  Instances of the class are *never* used.
	"""
	pass


class TristateBooleanField:
	"""is a sentinel class to signal a field that takes 
	boolean values, defaulting to undefined (None).

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

	Records also have a slightly silly inheritance mechanism.  If you
	call setExtensionFlag(True) on a Record, you mark it as an extension.
	When, later, this record would be overrwriting a value in an existing
	record, it will not replace it but instead create a copy of the original
	one and just overwrite the fields defined in the new one.  Confusing?
	Sure.  I don't like it either.

	>>> r = Record({"a": 7, "b": ListField, "c": RequiredField})
	>>> r.addto_b(4); r.get_a(), r.get_b()
	(7, [4])
	>>> r.get_c()
	Traceback (most recent call last):
	KeyError: 'c'
	>>> r.get_anything()
	Traceback (most recent call last):
	AttributeError: 'Record' object has no attribute 'get_anything'
	>>> s = r.copy(); s.addto_b(5); s.get_b()
	[4, 5]
	>>> r.get_b()
	[4]
	"""
	def __init__(self, legalKeys, initvals={}):
		self.dataStore = {}
		self.specialTypeHandlers = {
			ComputedField: lambda key, val: [],
			ListField: self._getListMethods,
			DictField: self._getDictMethods,
			BooleanField: self._getBooleanMethods,
			TrueBooleanField: self._getBooleanMethods,
			TristateBooleanField: self._getBooleanMethods,
		}
		# We need to remember which methods we created to support copying
		self.createdMethods = []
		self.keys = legalKeys
		for key, default in self.keys.iteritems():
			self._createMethods(key, default)
		for key, value in initvals.iteritems():
			self.set(key, value)
		self.extensionFlag = False

	def __str__(self):
		return "<%s %s>"%(self.__class__.__name__, str(self.dataStore))
	
	def __repr__(self):
		return "<%s %s>"%(self.__class__.__name__, str(self.dataStore)[:30])

	def setExtensionFlag(self, extensionFlag):
		self.extensionFlag = extensionFlag

	def isExtension(self):
		return self.extensionFlag

	def copy(self):
		"""returns a semi-shallow copy of the record.

		It's an incredible hack, but we need to replace the access methods,
		since they contain lexical bindings, and we can't really call
		a constructor since we don't know their arguments...

		semi-shallow means that if you have mutable atomic values, these
		will not be copied.  ListFields and DictFields are copied (shallowly),
		though.
		"""
		theCopy = copy.copy(self)
		theCopy.dataStore = self.dataStore.copy()
		for key, value in self.keys.iteritems():
			if value is ListField:
				theCopy.dataStore[key] = list(self.dataStore[key])
			if value is DictField:
				theCopy.dataStore[key] = self.dataStore[key].copy()
		for name, callable in self.createdMethods:
			setattr(theCopy, name, new.instancemethod(callable, theCopy))
		return theCopy

	def _createMethods(self, key, value):
		for prefix, callable in self.specialTypeHandlers.get(
				value, self._getAtomicMethods)(key, value):
			if not hasattr(self, prefix+key):
				self.createdMethods.append((prefix+key, callable))
				setattr(self, prefix+key, new.instancemethod(callable, self))

	def _getAtomicMethods(self, key, default):
		"""returns methods to manage normal atomic attributes.
		"""
		if default is not RequiredField:
			self.dataStore[key] = default
		def getter(self):
			return self.dataStore[key]
		def setter(self, value):
			if isinstance(value, Record) and isinstance(
					self.dataStore.get(key), Record):
				if value.isExtension():
					self.dataStore[key] = self.dataStore[key].copy()
					self.dataStore[key].updateFrom(value)
			self.dataStore[key] = value
		return [("get_", getter), ("set_", setter)]

	def _getListMethods(self, key, _):
		self.dataStore[key] = []
		def getter(self):
			return self.dataStore[key]
		def adder(self, value, infront=False):
			if infront:
				self.dataStore[key].insert(0, value)
			else:
				self.dataStore[key].append(value)
		def setter(self, value):
			self.dataStore[key] = value[:]
		def prepender(self, value):
			self.dataStore[key].insert(0, value)
		return [("get_", getter), ("addto_", adder), ("set_", setter),
			("prependto_", prepender)]

	def _getDictMethods(self, key, _):
		self.dataStore[key] = {}
		def getter(self, regKey, default=""):
			return self.dataStore[key].get(regKey, default)
		def setter(self, regKey, value):
			self.dataStore[key][regKey] = value
		def checker(self, regKey):
			return self.dataStore[key].has_key(regKey)
		def counter(self):
			return len(self.dataStore[key])
		def itemgetter(self):
			return self.dataStore[key].keys()
		return [("get_", getter), ("register_", setter), ("has_", checker),
			("count_", counter), ("itemsof_", itemgetter)]

	def _getBooleanMethods(self, key, default):
		if default is BooleanField:
			self.dataStore[key] = False
		elif default is TrueBooleanField:
			self.dataStore[key] = True
		elif default is TristateBooleanField:
			self.dataStore[key] = None
		else:
			assert(False)
		def setter(self, value):
			self.dataStore[key] = parseBooleanLiteral(value)
		def getter(self):
			return self.dataStore[key]
		return [("get_", getter), ("set_", setter)]

	def _extendFields(self, newFields):
		"""adds new fields to the record.

		This is for excusive use in constructors of derived classes.
		"""
		self.keys.update(newFields)
		for key, default in newFields.iteritems():
			self._createMethods(key, default)

	def updateFrom(self, other):
		"""tries to update self from the other record's data store.

		Updating works by extending lists and overwriting everything
		else.
		"""
		for key, val in other.dataStore.iteritems():
			if isinstance(self.dataStore.get(key), list):
				self.dataStore[key].extend(other.dataStore[key])
			else:
				self.dataStore[key] = other.dataStore[key]

	def immutilize(self):
		"""makes this record "read-only".

		In other words, all setters are deleted.
		"""
		for name in self.__dict__.keys():
			if name.startswith("set_") or name.startswith("addto_"):
				delattr(self, name)

	def isValid(self):
		"""returns true if all mandatory (non-default) fields have been set.
		"""
		for key, default in self.keys.iteritems():
			if default==RequiredField and not self.dataStore.has_key(key):
				return False
		return True

	def get(self, key):
		return getattr(self, "get_"+key)()
	
	def set(self, key, value):
		getattr(self, "set_"+key)(value)


def parseBooleanLiteral(literal):
	"""returns a boolean from some string.

	It parses true, false, yes, no, on, off in any capitalization to booleans.
	If literal already is a boolean, it is handed back.
	It also allows "None" or None as literal, which makes it return None (so,
	this really is tristate).
	"""
	if isinstance(literal, bool):
		return literal
	if literal==None:
		return None
	if literal.lower() in ["true", "yes", "on"]:
		return True
	elif literal.lower() in ["false", "no", "off"]:
		return False
	elif literal.lower()=="none":
		return None
	raise gavo.Error("%s is an invalid expression for a boolean"%literal)


def _test():
	import doctest, record
	doctest.testmod(record)


if __name__=="__main__":
	_test()
