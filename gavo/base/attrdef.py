"""
Attribute definitions for structures.

These are objects having at least the following attributes and methods:

* name -- will become the attribute name on the embedding class
* parseName -- the name of the XML/event element they can parse.  This
  usually is identical to name, but may differ for compound attributes
* default -- may be Undefined, otherwise a valid value of the
  expected type
* description -- for user documentation
* typeDesc -- describing the content; this is usually a class
  attribute and intended for user documentation
* feedObject(instance, ob) -> None -- adds ob to instance's attribute value.
  This will usually just result in setting the attribute; for compound
  attributes, this may instead append to a list, add to a set, etc.
* getCopy(instance, newParent) -> value -- returns the python value of the 
	attribute in instance, copying mutable values (deeply) in the process.
* iterParentMethods() -> iter((name, value)) -- iterates over methods
  to be inserted into the parent class.

They may have an attribute xmlName that allows parsing from xml elements
named differently from the attribute.  To keep things transparent, use
this sparingly; the classic use case is with lists, where you can call
an attribute options but have the XML element still be just "option".

AtomicAttributes, defined as those that are parsed from a unicode literal,
add methods

* feed(ctx, instance, literal) -> None -- arranges for literal to be parsed
  and passed to feedObject.  ctx is a parse context.  The built-in method
  does not expect anything from this object, but structure has a default 
  implementation containing an idmap and a propery registry.
* parse(self, value) -> anything -- returns a python value for the
  unicode literal value
* unparse(self, value) -> unicode -- returns a unicode object representing
  value and parseable by parse to that value.

This is not enough for complex attributes.  More on those in the 
base.complexattrs module.

AttributeDefs *may* have a validate(instance) method.  Structure instances
will call them when they are done building.  They should raise 
LiteralParseErrors if it turns out a value that looked right is not after
all (in a way, they could catch validity rather than well-formedness violations,
but I don't think this distinction is necessary here).

See structure on how to use all these.
"""

import os

from gavo.base import literals
from gavo.base import texttricks
from gavo.base.excs import LiteralParseError, StructureError


class UndefinedType(type):
	def __str__(self):
		raise StructureError("%s cannot be stringified"%self.__class__.__name__)

	__unicode__ = __str__

	def __repr__(self):
		return "<Undefined>"

	def __nonzero__(self):
		return False


class Undefined(object):
	"""is a sentinel class for uninitialized defaultless values.
	"""
	__metaclass__ = UndefinedType


class NotGiven(object):
	"""is a sentinel class for defaultless values that can remain undefined.
	"""
	__metaclass__ = UndefinedType

class Computed(object):
	"""is a sentinel class for computed (property) defaults.

	Use this to construct AttributeDefs with defaults that are properties
	to inhibit assigning to them.  This should only be required in calls
	of the superclass's init.
	"""


class AttributeDef(object):
	"""is the base class for all attribute definitions.

	See above.

	The data attribute names have all an underscore added to avoid name
	clashes -- structures should have about the same attributes and may
	want to have managed attributes called name or description.

	When constructing AttributeDefs, you should only use keyword
	arguments, except for name (the first argument).

	Note that an AttributeDef might be embedded by many instances.  So,
	you must *never* store any instance data in an AttributeDef (unless
	it's really a singleton, of course).
	"""

	typeDesc_ = "unspecified, invalid"

	def __init__(self, name, default=None, description="Undocumented",
			copyable=False, aliases=None, callbacks=None):
		self.name_, self.description_ = name, description
		self.copyable = copyable
		self.aliases = aliases
		self.callbacks = callbacks
		if default is not Computed:
			self.default_ = default

	def iterParentMethods(self):
		"""returns an iterator over (name, method) pairs that should be
		inserted in the parent class.
		"""
		return iter([])

	def doCallbacks(self, instance, value):
		"""should be called after feedObject has done its work.
		"""
		if self.callbacks:
			for cn in self.callbacks:
				getattr(instance, cn)(value)

	def feedObject(self, instance, value):
		raise NotImplementedError("%s doesn't implement feeding objects"%
			self.__class__.__name__)

	def feed(self, ctx, instance, value):
		raise NotImplementedError("%s doesn't implement feeding literals"%
			self.__class__.__name__)

	def getCopy(self, instance, newParent):
		raise NotImplementedError("%s cannot be copied."%
			self.__class__.__name__)


class AtomicAttribute(AttributeDef):
	"""is a base class for attributes than can be immediately parsed
	and unparsed from strings.

	They need to provide a parse method taking a unicode object and
	returning a value of the proper type, and an unparse method taking
	a value of the proper type and returning a unicode string suitable
	for parse.

	Note that you can, of course, assign to the attribute directly.
	If you assign crap, the unparse method is explicitely allowed
	to bomb in random ways; it just has to be guaranteed to work
	for values coming from parse (i.e.: user input is checked,
	programmatic input can blow up the thing; I consider this
	pythonesque :-).
	"""

	def parse(self, value):
		"""returns a typed python value for the string representation value.

		value can be expected to be a unicode string.
		"""
		raise NotImplementedError("%s does not define a parse method"%
			self.__class__.__name__)

	def unparse(self, value):
		"""returns a typed python value for the string representation value.

		value can be expected to be a unicode string.
		"""
		raise NotImplementedError("%s does not define an unparse method"%
			self.__class__.__name__)

	def feed(self, ctx, instance, value):
		self.feedObject(instance, self.parse(value))

	def feedObject(self, instance, value):
		setattr(instance, self.name_, value)
		self.doCallbacks(instance, value)

	def getCopy(self, instance, newParent):  # We assume atoms are immutable here
		return getattr(instance, self.name_)


class UnicodeAttribute(AtomicAttribute):
	"""is an attribute definition for an item containing a unicode string.
	"""

	typeDesc_ = "unicode string"

	def parse(self, value):
		if value=="__NULL__":
			return None
		return value

	def unparse(self, value):
		if value is None:
			return "__NULL__"
		return value


class RelativePathAttribute(UnicodeAttribute):
	"""is a (utf-8 encoded) path relative to some base path.
	"""
	typeDesc_ = "relative path"

	def __init__(self, name, default=None, basePath="", 
			description="Undocumented"):
		UnicodeAttribute.__init__(self, name, default, description)
		self.basePath = basePath

	def parse(self, value):
		return os.path.join(self.basePath, value).encode("utf-8")
	
	def unparse(self, value):
		return value.decode("utf-8")[len(self.basePath)+1:]


class FunctionRelativePathAttribute(UnicodeAttribute):
	"""is a (utf-8 encoded) path relative to the result of some function
	at runtime.

	This is used to make things relative to config items.
	"""
	def __init__(self, name, baseFunction, default=None,
			description="Undocumented", **kwargs):
		UnicodeAttribute.__init__(self, name, default, description, **kwargs)
		self.baseFunction = baseFunction
		self.hiddenAttName = "_real_"+self.name_

	def parse(self, value):
		return value.encode("utf-8")
	
	def unparse(self, value):
		return value.decode("utf-8")  # XXX TODO: make this relative again

	def iterParentMethods(self):
		def computePath(instance):
			relative = getattr(instance, self.hiddenAttName)
			if relative is None:
				return None
			return os.path.join(self.baseFunction(instance), relative)
		def setRelative(instance, value):
			setattr(instance, self.hiddenAttName, value)
		yield (self.name_, property(computePath, setRelative))


class EnumeratedUnicodeAttribute(UnicodeAttribute):
	"""is an attribute definition for an item that can only take on one
	of a finite set of values.
	"""
	def __init__(self, name, default, validValues, **kwargs):
		UnicodeAttribute.__init__(self, name, default, **kwargs)
		self.validValues = set(validValues)
	
	@property
	def typeDesc_(self):
		return "One of: %s"%",".join(self.validValues)

	def parse(self, value):
		value = UnicodeAttribute.parse(self, value)
		if not value in self.validValues:
			raise LiteralParseError("%s is not a valid value for %s"%(
				value, self.name_), self.name_, value)
		return value


class IntAttribute(AtomicAttribute):
	"""is an attribute definition for integer attributes.
	"""

	typeDesc_ = "integer"

	def parse(self, value):
		try:
			return int(value)
		except ValueError:
			raise LiteralParseError("Not an integer literal", self.name_, value)
	
	def unparse(self, value):
		return str(value)


class FloatAttribute(AtomicAttribute):
	"""is an attribute definition for floating point attributes.
	"""

	typeDesc_ = "float"

	def parse(self, value):
		try:
			return float(value)
		except ValueError:
			raise LiteralParseError("Not a float literal", self.name_, value)
	
	def unparse(self, value):
		return str(value)


class BooleanAttribute(AtomicAttribute):
	"""is a boolean attribute.

	Boolean literals are strings like True, false, on, Off, yes, No in
	some capitalization.
	"""
	typeDesc_ = "boolean"

	def parse(self, value):
		return literals.parseBooleanLiteral(value)
		
	def unparse(self, value):
		return {True: "True", False: "False"}[value]


class StringListAttribute(AtomicAttribute):
	"""is an attribute containing a list of comma separated strings.

	The value is a list.  This is similar to a complexattrs.ListOfAtoms
	with UnicodeAttribute items, except the literal is easier to write
	but more limited.  Use this for the user's convenience.
	"""
	realDefault = []

	def __init__(self, name, **kwargs):
		if "default" in kwargs:
			self.realDefault = kwargs.pop("default")
		AtomicAttribute.__init__(self, name, default=Computed, **kwargs)

	def parse(self, value):
		res = [str(name.strip()) 
			for name in value.split(",") if name.strip()]
		return res

	@property
	def default_(self):
		return self.realDefault[:]

	def unparse(self, value):
		return ", ".join(value)


class StringSetAttribute(StringListAttribute):
	"""is like StringListAttribute, except the result is a set.
	"""
	realDefault = set()

	def parse(self, value):
		return set(StringListAttribute.parse(self, value))
	
	@property
	def default_(self):
		return self.realDefault.copy()


class IdMapAttribute(AtomicAttribute):
	"""is an attribute allowing a quick specification of identifiers to
	identifiers.

	The literal format is <id>:<id>{,<id>:<id>} with ignored whitespace.
	"""
	def parse(self, val):
		if val is None:
			return None
		try:
			return dict((k.strip(), v.strip()) 
				for k,v in (p.split(":") for p in val.split(",")))
		except ValueError:
			raise LiteralParseError("'%s' does not have the format"
				" k:v {,k:v}"%val, self.name_, val)

	def unparse(self, val):
		if val is None:
			return None
		return ", ".join(["%s: %s"%(k, v) for k, v in val.iteritems()])


class ActionAttribute(UnicodeAttribute):
	"""is an attribute definition for attributes triggering a method call
	on the parent instance.
	
	They do create an attribute on parent which is None by default
	and the attribute value as a unicode string once the attribute
	was encountered.  This could be used to handle multiple occurrences
	but is not in this basic definition.
	"""
	def __init__(self, name, methodName, description="Undocumented",
			**kwargs):
		self.methodName = methodName
		UnicodeAttribute.__init__(self, name, None, description, **kwargs)
	
	def feedObject(self, instance, value):
		UnicodeAttribute.feedObject(self, instance, value)
		getattr(instance, self.methodName)()
			


# The public interface actually is everything.  Since it's much prettier
# in the attribute lists of the classes, let's allow from ... import *
# here.

__all__ = ["LiteralParseError", "Undefined", "UnicodeAttribute", 
	"IntAttribute", "BooleanAttribute", "AtomicAttribute", 
	"EnumeratedUnicodeAttribute", "AttributeDef", "Computed",
	"RelativePathAttribute", "FunctionRelativePathAttribute",
	"StringListAttribute", "ActionAttribute", "FloatAttribute",
	"StringSetAttribute", "NotGiven", "IdMapAttribute"]
