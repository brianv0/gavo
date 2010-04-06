"""
Generating a utype/value sequence for ASTs.

Yet another insane serialization for an insane data model.  Sigh.

The way we come up with the STC utypes here is described in an IVOA note.
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
	"""An object encapsulating information on how to turn a stanxml
	node into a sequence of utype/value pairs.

	This is an "universal" base, serving as a simple default.
	Any class handling specific node types must fill out at least
	the rootType attribute, giving the utype at which this UtypeMaker
	should kick in.

	By default, utype/value pairs are only returned for nonempty
	element content.  To change this, define _gener_<name>(node,
	prefix) -> iterator methods.

	The actual pairs are retrieved by calling iterUtypes(node,
	parentPrefix).
	"""
	__metaclass__ = UtypeMaker_t

	rootType = None

	def _generPlain(self, name, child, prefix):
		childType = utypejoin(prefix, name)
		maker = _getUtypeMaker(childType)
		for item in child:
			for pair in maker.iterUtypes(item, childType):
				yield pair

	def _gener__colRef(self, name, child, prefix):
		yield prefix, child[0]

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


# A resolver of element names to their handling classes.  For most
# elements, this is just a plain UtypeMaker.
_getUtypeMaker = utils.buildClassResolver(
	UtypeMaker, 
	globals().values(),
	default=UtypeMaker(),
	instances=True, 
	key=lambda obj:obj.rootType)


def getUtypes(ast):
	"""returns a lists of utype/value pairs for an STC AST.
	"""
	cst = stcxgen.astToStan(ast, STC.STCSpec)
	utypes = []
	for utype, val in _getUtypeMaker("").iterUtypes(cst, ""):
		if val is None or val=='':
			continue
		utypes.append(("stc:"+utype, val))
	return utypes
