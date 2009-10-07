"""
Attributes with structure (i.e., containing structures or more than one
atom.

These come with parsers of their own, in some way or other.

Structure attributes, which do not have string literals and have some sort
of internal structure, add methods

* create(instance, name) -> structure -- creates a new object of the required 
  type and returns it.  This is what should later be fed to feedObject and
  must have a getParser attribute.  The name argument gives the name of
  the element that caused the create call, allowing for polymorphic attrs.
* getParser(instance) -> callable -- returns a callable that receives
  parse events to fill instance
* replace(instance, oldVal, newVal) -> None -- replaces oldVal with newVal; this
  works like feedObject, except that an old value is overwritten.  We
	need such functionality with structure.RefAttribute and 
	structure.CopyAttribute.
* iterEvents(instance) -> events -- yields events to recreate its value
  on another instance.
"""

from gavo.base import structure
from gavo.base.attrdef import *
from gavo.utils.excs import *


class CollOfAtomsAttribute(AtomicAttribute):
	"""is a base class for simple collections of atomic
	attributes.
	"""
	def __init__(self, name, default=[], itemAttD=UnicodeAttribute("listItem"), 
			**kwargs):
		AttributeDef.__init__(self, name, default=Computed, **kwargs)
		self.xmlName_ = itemAttD.name_
		self.itemAttD = itemAttD
		self.realDefault = default

	def iterEvents(self, instance):
		for item in getattr(instance, self.name_):
			yield ("start", self.xmlName_, None)
			yield ("value", self.xmlName_, self.itemAttD.unparse(item))
			yield ("end", self.xmlName_, None)


class ListOfAtomsAttribute(CollOfAtomsAttribute):
	"""is an attribute definition for an item containing many elements
	of the same type.

	It is constructed with an AttributeDef for the items.  Note that it's
	safe to pass in lists as defaults since they are copied before being
	added to the instances, so you won't (and can't) have aliasing here.
	"""

	@property
	def default_(self):
		return self.realDefault[:]

	@property
	def typeDesc_(self):
		return "List of %ss"%self.itemAttD.typeDesc_

	def feed(self, ctx, instance, value):
		getattr(instance, self.name_).append(self.itemAttD.parse(value))

	def feedObject(self, instance, value):
		if isinstance(value, list):
			for item in value:
				self.feedObject(instance, item)
		else:
			getattr(instance, self.name_).append(value)
			self.doCallbacks(instance, value)

	def getCopy(self, instance, newParent):
		return getattr(instance, self.name_)[:]

	def unparse(self, value):
		return unicode(value)


class SetOfAtomsAttribute(CollOfAtomsAttribute):
	"""is an attribute definition for an item containing many elements
	of the same type, when order doesn't matter but lookup times do.

	It is constructed with an AttributeDef for the items.  Note that it's
	safe to pass in lists as defaults since they are copied before being
	added to the instances, so you won't (and can't) have aliasing here.
	"""
	@property
	def default_(self):
		return set(self.realDefault)

	@property
	def typeDesc_(self):
		return "Set of %ss"%self.itemAttD.typeDesc_

	def feed(self, ctx, instance, value):
		getattr(instance, self.name_).add(self.itemAttD.parse(value))

	def feedObject(self, instance, value):
		if isinstance(value, set):
			for item in value:
				self.feedObject(instance, value)
		else:
			getattr(instance, self.name_).add(value)
			self.doCallbacks(instance, value)

	def getCopy(self, instance, newParent):
		return set(getattr(instance, self.name_))


class DictParser(structure.Parser):
	def __init__(self, dict, nextParser, parseValue, keyName):
		self.dict, self.nextParser, self.parseValue = dict, nextParser, parseValue
		self.key, self.keyName = Undefined, keyName

	def value(self, ctx, name, value):
		if name==self.keyName:
			self.key = value
		elif name=="content_":
			if self.key is Undefined:
				raise StructureError("Content '%s' has no %s attribute"%(
					value, self.keyName))
			self.dict[self.key] = self.parseValue(value)
			self.key = Undefined
		else:
			raise StructureError("No %s attributes on mappings"%name)
		return self
	
	def start(self, ctx, name, value):
		raise StructureError("No %s elements in mappings"%name)
	
	def end(self, ctx, name, value):
		if self.key is not Undefined:
			self.dict[self.key] = None
			self.key = Undefined
		return self.nextParser


class DictAttribute(AttributeDef):
	"""defines defaults on the input keys the mapper receives.
	"""
	def __init__(self, name, description="Undocumented", 
			itemAttD=UnicodeAttribute("value"), keyName="key", **kwargs):
		AttributeDef.__init__(self, name, Computed, description, **kwargs)
		self.xmlName_ = itemAttD.name_
		self.itemAttD = itemAttD
		self.keyName = keyName

	@property
	def typeDesc_(self):
		return "Dict mapping strings to %s"%self.itemAttD.typeDesc_

	@property
	def default_(self):
		return {}

	def feedObject(self, instance, value):
		setattr(instance, self.name_, value)
		self.doCallbacks(instance, value)

	def getParser(self, instance):
		return DictParser(getattr(instance, self.name_), 
			instance.getParser(instance), self.itemAttD.parse, keyName=self.keyName)

	def create(self, parent, name):
		return self

	def iterEvents(self, instance):
		for key, value in getattr(instance, self.name_).iteritems():
			yield ("start", self.xmlName_, None)
			yield ("value", self.keyName, key)
			yield ("value", "content_", self.itemAttD.unparse(value))
			yield ("end", self.xmlName_, None)
	
	def getCopy(self, instance, newParent):
		return getattr(instance, self.name_).copy()

	def makeUserDoc(self):
		return "**%s** (mapping; the key is given in the %s attribute) -- %s"%(
			self.itemAttD.name_, self.keyName, self.description_)


class PropertyAttribute(DictAttribute):
	"""adds the property protocol to the parent instance.

	The property protocol is just two methods, setProperty(name, value),
	and getProperty(name, default=Undefined), where getProperty works like
	dict.get, except it will raise a KeyError without a default.

	This is provided for user information and, to some extent, some 
	DC-internal purposes.
	"""
	def __init__(self, description="Properties (i.e., user-defined"
			" key-value pairs) for the element.", **kwargs):
		DictAttribute.__init__(self, "properties", description=description, 
			keyName="name", **kwargs)
		self.xmlName_ = "property"
	
	def iterParentMethods(self):
		def setProperty(self, name, value):
			self.properties[name] = value
		yield "setProperty", setProperty

		def getProperty(self, name, default=Undefined):
			if default is Undefined:
				return self.properties[name]
			else:
				return self.properties.get(name, default)
		yield "getProperty", getProperty

	def makeUserDoc(self):
		return ("**property** (mapping of user-defined keywords in the"
			" name attribute to string values) -- %s"%self.description_)


class StructAttribute(AttributeDef):
	"""describes an attribute containing a Structure

	These are constructed with a childFactory that must have a feedEvent
	method.  Otherwise, they are normal structs, i.e., the receive a
	parent as the first argument and keyword arguments for values.
	
	In addition, you can pass a onParentCompleted callback that
	are collected in the completedCallback list by the struct decorator.
	ParseableStruct instances call these when they receive their end
	event during XML deserialization.
	"""
	def __init__(self, name, childFactory, default=Undefined, 
			description="Undocumented", **kwargs):
		AttributeDef.__init__(self, name, default, description, **kwargs)
		self.childFactory = childFactory
		self.xmlName_ = self.childFactory.name_

	@property
	def typeDesc_(self):
		return self.childStruct.name_

	def feedObject(self, instance, value):
		if value is not None and value.parent is None:  # adopt if necessary
			value.parent = instance
		setattr(instance, self.name_, value)
		self.doCallbacks(instance, value)

	def feed(self, ctx, instance, value):
		raise LiteralParseError("%s items have no literals"%self.name_,
			self.name_, value)

	def create(self, structure, name):
		return self.childFactory(structure)

	def getCopy(self, instance, newParent):
		val = getattr(instance, self.name_)
		if val is not None:
			return val.copy(newParent)
	
	def replace(self, instance, oldStruct, newStruct):
		setattr(instance, self.name_, newStruct)

	def iterEvents(self, instance):
		val = getattr(instance, self.name_)
		if val is None:
			return
		yield ("start", val.name_, None)
		for ev in val.iterEvents():
			yield ev
		yield ("end", val.name_, None)

	def iterChildren(self, instance):
		if getattr(instance, self.name_) is not None:
			yield getattr(instance, self.name_)

	def onParentCompleted(self, val):
		if hasattr(val, "onParentCompleted"):
			val.onParentCompleted()

	def makeUserDoc(self):
		return "%s (contains `Element %s`_) -- %s"%(
			self.name_, self.childFactory.name_, self.description_)


class StructListAttribute(StructAttribute):
	"""describes an attribute containing a homogeneous list of structures.
	"""
	def __init__(self, name, childFactory, description="Undocumented",
			**kwargs):
		StructAttribute.__init__(self, name, childFactory, Computed,
			description, **kwargs)

	@property
	def default_(self):
		return []

	@property
	def typeDesc_(self):
		return "List of %s"%self.childStruct.name_
	
	def feedObject(self, instance, value):
		if isinstance(value, list):
			for item in value:
				self.feedObject(instance, item)
		else:
			if value.parent is None:  # adopt if necessary
				value.parent = instance
			getattr(instance, self.name_).append(value)
			self.doCallbacks(instance, value)
	
	def getCopy(self, instance, newParent):
		res = [c.copy(newParent) for c in getattr(instance, self.name_)]
		return res

	def replace(self, instance, oldStruct, newStruct):
		# This will only replace the first occurrence of oldStruct if
		# multiple identical items are in the list.  Any other behaviour
		# would be about as useful, so let's leave it at this for now.
		curContent = getattr(instance, self.name_)
		ind = curContent.index(oldStruct)
		curContent[ind] = newStruct

	def iterEvents(self, instance):
		for val in getattr(instance, self.name_):
			yield ("start", self.xmlName_, None)
			for ev in val.iterEvents():
				yield ev
			yield ("end", self.xmlName_, None)

	def iterChildren(self, instance):
		return iter(getattr(instance, self.name_))

	def onParentCompleted(self, val):
		if val:
			for item in val:
				if hasattr(item, "onParentCompleted"):
					item.onParentCompleted()

	def makeUserDoc(self):
		return ("%s (contains `Element %s`_ and may be repeated zero or more"
			" times) -- %s")%(self.name_, self.childFactory.name_, self.description_)


__all__ = ["ListOfAtomsAttribute", "DictAttribute", "StructAttribute",
	"StructListAttribute", "SetOfAtomsAttribute", "PropertyAttribute"]
