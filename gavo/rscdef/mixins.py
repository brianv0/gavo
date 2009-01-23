"""
RMixins are resource descriptor fragments rooted in tables.  They
can, in principle, manipulate the entire parse tree.  The name RMixin
should distinguish them from mixins for python classes, which they are
not.

They are used to define and implement certain behaviours components of
the DC software want to see:

* products want to be added into their table, and certain fields are required
  within tables describing products
* tables containing positions need some basic machinery to support scs.
* siap needs quite a bunch of fields

etc.

Technically, rmixins are implemented as objects having two methods,
processEarly(tableDef) -> None and processLate(tableDef) -> None.  The first is
called as soon as the mixin element is encountered, the second when the
enclosing resource descriptor is finished.

You should, in general, base rmixins on resource descriptors as far as
possible.  RMixins are defined near the components that need them and
registred here.

You can check if a certain table mixes in something by calling its
mixesIn method.
"""

from gavo import base

class MixinAttribute(base.ListOfAtomsAttribute):
	"""is an attribute listing the mixins of a table.

	The attribute relies on the parent being a table.

	It takes care of calling the processEarly callback.  For calling
	the processLate callback it relies on the resource descriptor's
	cooperation.
	"""
	name_ = "mixin"

	def __init__(self, **kwargs):
		base.ListOfAtomsAttribute.__init__(self, "mixins", 
			itemAttD=base.UnicodeAttribute("mixin", default=base.Undefined), 
			description="Mixins for this table", **kwargs)
	
	def feed(self, ctx, instance, mixinName):
		if mixinName not in _mixinRegistry:
			raise base.LiteralParseError("No such mixin defined: %s"%mixinName,
				"mixin", mixinName)
		getMixin(mixinName).processEarly(instance)
		base.ListOfAtomsAttribute.feedObject(self, instance, mixinName)

	def iterParentMethods(self):
		def mixesIn(instance, mixinName):
			return mixinName in instance.mixins
		yield "mixesIn", mixesIn


class RMixinBase(object):
	"""is a base class for RD-based mixins.

	There's no reason to actually inherit from this for your mixins, but
	for RD-based mixins, it's more convenient.

	It is constructed with an id of a resource descriptor and the id of
	a table therein.  Certain attributes of the table will be moved over
	in processEarly.  Everything else is still up to you.
	"""
	def __init__(self, rdId, interfaceTable):
		self.rd = base.caches.getRD(rdId)
		self.mixinTable = self.rd.getTableDefById(interfaceTable)

	def processLate(self, tableDef):
		pass
	
	def processEarly(self, tableDef):
		tableDef.feedFrom(self.mixinTable)


_mixinRegistry = {}

def registerRMixin(mixin):
	_mixinRegistry[mixin.name] = mixin

def getMixin(mixinName):
	return _mixinRegistry[mixinName]
