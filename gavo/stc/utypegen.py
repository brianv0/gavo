"""
Generating a utype/value sequence for ASTs.

Yet another insane serialization for an insane data model.  Sigh.

In what's documented about the utype serialization, there are subtle
deviations from what STC-X does.  Thus, we hack around it using 
transformations, and we use some markup to signify what nodes we
want returned.
"""

from gavo import utils
from gavo.stc import common
from gavo.stc import stcxgen
from gavo.stc.stcx import STC


#################### utype maker definition

def handles(seq):
	"""is a decorator for UtypeMaker methods.

	It adds a "handles" attribute as evaluated by AutoUtypeMaker.
	"""
	def deco(meth):
		meth.handles = seq
		return meth
	return deco


class UtypeMaker_t(type):
	"""A metaclass to facilite easy definition of UtypeMakers.

	This metaclass primarily operates on the handles hints left by the
	decorator.
	"""
	def __init__(cls, name, bases, dict):
		type.__init__(cls, name, bases, dict)
		cls._createHandlesMethods(dict.values())
	
	def _createHandlesMethods(cls, items):
		for item in items:
			for name in getattr(item, "handles", ()):
				setattr(cls, "_gener_"+name, item)


class UtypeMaker(object):
	"""An object encapsulating information on how to turn a stanxml node
	into a sequence of utype/value pairs.

	This is an abstract base.  Concrete objects must fill out at least
	the rootType attribute, giving the utype at which this UtypeMaker should
	kick in.
	
	By default, utype/value pairs are only returned for nonempty element
	content.  To change this, define _gener_<name>(node, prefix) -> iterator
	methods.

	The actual pairs are retrieved by calling iterUtypes(node, parentPrefix).
	"""
	__metaclass__ = UtypeMaker_t

	rootType = None

	def _gener__colRef(self, name, child, prefix):
		for item in child:
			yield prefix, item.dest

	def _generPlain(self, name, child, prefix):
		childType = utypejoin(prefix, name)
		maker = _getUtypeMaker(childType)
		for item in child:
			for pair in maker.iterUtypes(item, childType):
				yield pair

	def iterUtypes(self, node, prefix):
		children = node.makeChildDict()
		if node.text:
			yield prefix, node.text
		for name, child in children.iteritems():
			handler = getattr(self, "_gener_"+name, self._generPlain)
			for pair in handler(name, child, prefix):
				yield pair


class _NotImplementedUtypeMaker(UtypeMaker):
	def _generPlain(self, name, child, prefix):
		raise common.STCNotImplementedError("Cannot create utypes for %s yet."%
			self.utypeFrag)


#################### utype specific makers


class _CoordFrameMaker(UtypeMaker):
	@handles(common.stcRefPositions)
	def _refPos(self, name, child, prefix):
		yield utypejoin(prefix, "ReferencePosition"), name


class TimeFrameMaker(_CoordFrameMaker):
	rootType = "AstroCoordSystem.TimeFrame"
	@handles(common.stcTimeScales)
	def _timeScale(self, name, child, prefix):
		yield utypejoin(prefix, "TimeScale"), name


class SpaceFrameMaker(_CoordFrameMaker):
	rootType = "AstroCoordSystem.SpaceFrame"

	@handles(common.stcSpaceRefFrames)
	def _coordFrame(self, name, child, prefix):
		myPrefix = utypejoin(prefix, "CoordRefFrame")
		yield myPrefix, name
		for pair in self._generPlain(None, child, myPrefix):
			yield pair

	@handles(common.stcCoordFlavors)
	def _coordFlavor(self, name, child, prefix):
		prefix = utypejoin(prefix, "CoordFlavor")
		yield prefix, name
		if child:
			if child[0].a_coord_naxes!="2":
				yield utypejoin(prefix, "coord_naxes"), child[0].a_coord_naxes
			yield utypejoin(prefix, "handedness"), child[0].a_handedness


class RedshiftFrameMaker(_CoordFrameMaker):
	rootType = "AstroCoordSystem.RedshiftFrame"
	
	def iterUtypes(self, node, prefix):
		yield utypejoin(prefix, "value_type"), node.a_value_type
		for pair in _CoordFrameMaker.iterUtypes(self, node, prefix):
			yield pair


class SpectralFrameMaker(_CoordFrameMaker):
	rootType = "AstroCoordSystem.SpectralFrame"


#################### toplevel code

def utypejoin(*utypes):
	return ".".join(u for u in utypes if u)


_getUtypeMaker = utils.buildClassResolver(UtypeMaker, globals().values(),
	instances=True, key=lambda obj:obj.rootType, default=UtypeMaker())


def _makeDicts(pairIter):
	"""generates the system and column dictionaries from the raw pair 
	iterator.

	It also filters out utype/value-pairs with None values.  For the
	definition of the two dictionaries, see, getUtypes.
	"""
	sysDict, cooDict = {}, {}
	for utype, val in pairIter:
		if val is None or val=='':
			continue
		if utype.startswith("AstroCoordSystem"):
			sysDict[utype] = val
		else:
			cooDict[val] = utype
	return sysDict, cooDict


def getUtypes(ast):
	"""returns utype dictionaries for an STCSpec ast.

	The utype dictionaries are

	* the system dict, containing a mapping of utypes to values defining
	  coordinate systems,
	* the column dictitionary, containing a mapping of column names to
	  the pertaining utype.
	"""
	ctx = stcxgen.Context(ast)
	cst = stcxgen.astToStan(ast, STC.STCSpec)
	return _makeDicts(_getUtypeMaker(None).iterUtypes(cst, None))


def iterUtypesForSystem(systemTree):
	"""returns a utype dictionary for a dm.CoordSys object.
	"""
	ctx = stcxgen.Context(systemTree)
	cst = stcxgen.nodeToStan(systemTree)
	for utype, val in  _getUtypeMaker("AstroCoordSystem").iterUtypes(cst, 
			"AstroCoordSystem"):
		if val is None or val=='':
			continue
		yield utype, val
