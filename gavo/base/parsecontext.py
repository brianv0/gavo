"""
ParseContexts for parsing into structures.

A Context is a scratchpad from XML.  It always provides an idmap, but
you're free to insert additional attributes.

Based on this, we provide some attribute definitions.
"""


from gavo.base import attrdef
from gavo.base import caches
from gavo.base.excs import StructureError, LiteralParseError


def assertType(id, ob, forceType):
	"""raises a StructureError if forceType is not None and ob is not of
	type forceType, returns ob otherwise.
	"""
	if forceType:
		if not isinstance(ob, forceType):
			raise StructureError("Reference to '%s' yielded object of type"
				" %s, expected %s"%(id, ob.__class__.__name__, 
				forceType.__name__))
	return ob


def resolveCrossId(id, forceType):
	"""resolves id, where id is of the form rdId#id.
	"""
	rdId, rest = id.split("#")
	srcRd = caches.getRD(rdId)
	return resolveId(srcRd, rest, forceType)


def resolveComplexId(ctx, id, forceType=None):
	"""resolves a dotted id.

	See resolveId.
	"""
	try:
		pId, name = id.split(".")
	except ValueError:
		raise LiteralParseError("%s is not a valid id"%id, "id", id)
	container = ctx.getById(pId)
	for ob in container:
		if hasattr(ob, "name") and ob.name==name:
			return assertType(id, ob, forceType)
	raise StructureError("Element %s has no child with name %s"%(
		pId, name))


def resolveId(ctx, id, instance=None, forceType=None):
	"""tries to resolve id in context.

	The rules for id are as follows:

	(#) if id has a # in it, split it and take the first part to be
	an RD id, the second and id built according to the rest of this spec.

	(#) if id has a dot in it, split at the first dot to get a pair of
	id and name.  Iterate over the element with id, and look for something
	with a "name" attribute valued name.  If this fails, raise a 
	StructureError.

	(#) if instance is not None, has a parent, and that parent has a resolveName
	method, pass id to it.  If it does not raise a structure error, return the
	result.  This is for parents with a rscdef.NamePathAttribute.

	(#) ask the ParseContext ctx's getById method to resolve id, not
	catching the StructureError this will raise if the id is not known.
	"""
	if "#" in id:
		return resolveCrossId(id, forceType)
	if "." in id:
		return resolveComplexId(ctx, id, forceType)
	srcOb = None
	if (instance and instance.parent and 
			hasattr(instance.parent, "resolveName")):
		try:
			srcOb = instance.parent.resolveName(ctx, id)
		except StructureError:  # no such named element, try element with id
			pass
	if srcOb is None and ctx is not None:
		srcOb = ctx.getById(id, forceType)
	return assertType(id, srcOb, forceType)


class IdAttribute(attrdef.UnicodeAttribute):
	"""is an attribute that registers its parent in the context's id map
	in addition to setting its id attribute.
	"""
	def feed(self, ctx, parent, literal):
		attrdef.UnicodeAttribute.feed(self, ctx, parent, literal)
		ctx.registerId(parent.id, parent)
	
	def getCopy(self, parent, newParent):
		return None  # ids may not be copied


class OriginalAttribute(attrdef.AtomicAttribute):
	"""is an attribute that resolves an item 	copies over the managed 
	attributes from the referenced item.
	
	The references may be anything resolveId can cope with.

	You can pass a forceType argument to make sure only references to
	specific types are allowable.  In general, this will be the class
	itself of a base class.  If you don't do this, you'll probably get
	weird AttributeErrors for certain inputs.

	To work reliably, these attributes have to be known to the XML
	parser so it makes sure they are processed first.  This currently
	works by name, and "original" is reserved for this purpose.  Other
	names will raise an AssertionError right now.
	"""
	computed_ = True

	def __init__(self, name="original", description="Undocumented", 
			forceType=None, **kwargs):
		assert name=='original'
		attrdef.AtomicAttribute.__init__(self, name, None, description,
			**kwargs)
		self.forceType = forceType

	def feed(self, ctx, instance, literal):
		if isinstance(literal, basestring):
			srcOb = resolveId(ctx, literal, instance, self.forceType)
		else: # You can feed references programmatically if you like
			srcOb = literal
		instance._originalObject = srcOb
		for att in set(srcOb.managedAttrs.values()):
			if att.copyable:
				if getattr(srcOb, att.name_) is not None:
					copy = att.getCopy(srcOb, instance)
					att.feedObject(instance, copy)


class ReferenceAttribute(attrdef.AtomicAttribute):
	"""is an attribute that enters reference to some other structure into
	the attribute.

	Do not confuse this with structure.RefAttribute -- here, the parent remains
	unscathed, and it's much less messy overall.
	"""
	def __init__(self, name="ref", default=attrdef.Undefined,
			description="Uncodumented", forceType=None, **kwargs):
		attrdef.AtomicAttribute.__init__(self, name, default,
			description, **kwargs)
		self.forceType = forceType

	def feed(self, ctx, instance, literal):
		if literal is None: # ref attribute empty during a copy
			return            # do nothing, since nothing was ref'd in original
		self.feedObject(instance,
			resolveId(ctx, literal, instance, self.forceType))

	def unparse(self, value):
		if value is None:  # ref attribute was empty
			return None
		return value.id


class ParseContext(object):
	"""is a scratchpad for any kind of data parsers want to pass to feed
	methods.

	These objects are available to the feed methods as their
	first objects.  This may be overridden, but the id map should
	remain.
	"""
	def __init__(self):
		self.idmap = {}
	
	def registerId(self, elId, value):
		"""enters a value in the id map.

		We allow overriding in id.  That should not happen while parsing
		and XML document because of their uniqueness requirement, but
		might come in handy for programmatic manipulations.
		"""
		self.idmap[elId] = value
	
	def getById(self, id, forceType=None):
		if id not in self.idmap:
			raise StructureError("Reference to unknown item '%s'.  Note that"
				" elements referenced must occur lexically before the referring"
				" element"%id)
		res = self.idmap[id]
		return assertType(id, res, forceType)

	def getLocator(self):
		if hasattr(self, "parser") and hasattr(self.parser, "locator"):
			return self.parser.locator
		
	def getLocation(self):
		"""returns a current position if it has the necessary information.
		"""
		src = getattr(self, "srcPath", "<internal source>")
		locator = self.getLocator()
		if locator:
			row, col = locator.getLineNumber(), locator.getColumnNumber()
			if col is None: # locator doesn't tell us where the parser is.
				if hasattr(self, "lastRow"):
					posStr = "last known position: %d, %d"%(self.lastRow, self.lastCol)
				else:
					posStr = "unknown position"
			else:
				posStr = "%d, %d"%(row, col)
		else:
			posStr = "unknown position"
		return "%s, %s"%(src, posStr)
