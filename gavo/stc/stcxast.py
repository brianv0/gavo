"""
Building ASTs from STC-X trees.
"""

from gavo.stc import dm
from gavo.stc.common import *


_xlinkHref = str(ElementTree.QName(XlinkNamespace, "href"))


def _localname(qName):
	"""hacks the local tag name from a {ns}-serialized qName.
	"""
	return qName[qName.find("}")+1:]


def _passthrough(node, buildArgs, context):
	"""yields the items of buildArgs.

	This can be used for "no-op" elements.
	"""
	return buildArgs.iteritems()


def _makeKeywordBuilder(kw):
	"""returns a builder that returns the node's text content under kw.
	"""
	def buildKeyword(node, buildArgs, context):
		yield kw, node.text
	return buildKeyword


def _makeKWValueBuilder(kwName):
	"""returns a builder that takes vals from the buildArgs and
	returns a tuple of them under kwName.

	The vals key is left by builders like _buildVector.
	"""
	def buildNode(node, buildArgs, context):
		yield kwName, (buildArgs["vals"],)
	return buildNode


def _makeNodeBuilder(kwName, astObject):
	"""returns a builder that makes astObject with the current buildArgs
	and returns the thing under kwName.
	"""
	def buildNode(node, buildArgs, context):
		buildArgs["id"] = node.get(id, None)
		yield kwName, astObject(**buildArgs)
	return buildNode


class ContextActions(object):
	"""A specification of context actions for certain elements.

	You will want to override both start and stop.  The methods
	should not change node.
	"""
	def start(self, context, node):
		pass

	def stop(self, context, node):
		pass


################ Coordinate systems

def _buildAstroCoordSystem(node, buildArgs, context):
	if _xlinkHref in node.attrib:
		raise STCNotImplementedError("Cannot evaluate hrefs yet")
	buildArgs["id"] = node.get("id", None)
	newEl = dm.CoordSys(**buildArgs)
	yield "systems", (newEl,)


def _buildRefpos(node, buildArgs, context):
	yield 'refPos', dm.RefPos(standardOrigin=_localname(node.tag))

def _buildFlavor(node, buildArgs, context):
	yield 'flavor', _localname(node.tag)
	yield 'nDim', int(node.get("coord_naxes"))

def _buildRefFrame(node, buildArgs, context):
	yield 'refFrame', _localname(node.tag)


################# Coordinates

class CooSysActions(object):
	"""Actions for containers of coordinates.

	The actions push and pop the system ids of the containers.  If
	no system ids are present, None is pushed.
	"""
	def start(self, context, node):
		context.sysIdStack.append(node.get("coord_system_id", None))
	
	def stop(self, context, node):
		context.sysIdStack.pop()

def _buildFloat(node, buildArgs, context):
	yield 'vals', (float(node.text),)
	if 'pos_unit' in node.attrib:
		yield 'pos_unit', (node.get('pos_unit'),)

def _buildVector(node, buildArgs, context):
	yield 'vals', (tuple(buildArgs["vals"]),)
	if "pos_unit" in buildArgs:
		yield "unit", " ".join(buildArgs["pos_unit"])

def _buildPosition(node, buildArgs, context):
	if len(buildArgs.get("vals", ()))!=1:
		raise STCValueError("Need exactly one value to build position")
	buildArgs["value"] = buildArgs["vals"][0]
	del buildArgs["vals"]
	# Fill in frame: If there's a frame id, use it, else see if there's
	# a coo sys id.  If it's missing, take it from the context, then make
	# a proxy to the referenced system's spatial frame.
	if "frame_id" in node.attrib:
		buildArgs["frame"] = IdProxy(idref=node["frame_id"])
	elif "coord_system_id" in node.attrib:
		buildArgs["frame"] = IdProxy(idref=node["frame_id"], useAttr="spaceFrame")
	else:
		buildArgs["frame"] = IdProxy(idref=context.sysIdStack[-1], 
			useAttr="spaceFrame")
	# Figure out the unit -- if one is given on the element, override
	# whatever we may have got from downtree.
	if "unit" in node.attrib and node.get("unit"):
		buildArgs["unit"] = node.get("unit")
	yield 'places', (dm.SpaceCoo(**buildArgs),)


################# Toplevel

def buildTree(csNode, context):
	"""traverses the ElementTree cst, trying handler functions for
	each node.

	The handler functions are taken from the context.elementHandler
	dictionary that maps QNames to callables.  These callables have
	the signature handle(STCNode, context) -> iterator, where the
	iterator returns key-value pairs for inclusion into the argument
	dictionaries for STCNodes.

	Unknown nodes are simply ignored.  If you need to bail out on certain
	nodes, raise explicit exceptions in handlers.
	"""
	resDict = {}
	if csNode.tag not in context.elementHandlers:
		return
	if csNode.tag in context.activeTags:
		context.startTag(csNode)
	for child in csNode:
		for res in buildTree(child, context):
			if res is None:  # ignored child
				continue
			k, v = res
			if isinstance(v, (tuple, list)):
				resDict.setdefault(k, []).extend(v)
			else:
				if k in resDict:
					raise STCInternalError("Attempt to overwrite key '%s', old"
						" value %s, new value %s (this should probably have been"
						" a tuple)"%(k, resDict[k], v))
				resDict[k] = v
	for res in context.elementHandlers[csNode.tag](csNode, resDict, context):
		yield res
	if csNode.tag in context.activeTags:
		context.endTag(csNode)


class IdProxy(ASTNode):
	"""A stand-in for a coordinate system during parsing.

	We do this to not depend on ids being located before positions.  STC
	should have that in general, but let's be defensive here.
	"""
	_a_idref = None
	_a_useAttr = None
	
	def resolve(self, idMap):
		ob = idMap[self.idref]
		if self.useAttr:
			return getattr(ob, self.useAttr)
		return ob


def resolveProxies(astRoot):
	"""replaces IdProxies in astRoot with the real objects.
	"""
	astRoot.buildIdMap()
	for node in astRoot.iterNodes():
		for attName, value in node.iterAttributes(skipEmpty=True):
			if isinstance(value, IdProxy):
				setattr(node, attName, value.resolve(astRoot.idMap))


class STCXContext(object):
	"""A parse context containing handlers, stacks, etc.

	A special feature is that there are "context-active" tags.  For those
	the context gets notified by buildTree when their processing is started
	or ended.  We use this to note the active coordinate systems during, e.g.,
	AstroCoords parsing.
	"""
	def __init__(self, elementHandlers, activeTags, **kwargs):
		self.sysIdStack = []
		self.elementHandlers = elementHandlers
		self.idMap = {}
		self.activeTags = activeTags
		for k, v in kwargs.iteritems():
			setattr(self, k, v)

	def startTag(self, node):
		self.activeTags[node.tag].start(self, node)

	def endTag(self, node):
		self.activeTags[node.tag].stop(self, node)


def _n(name):
	return ElementTree.QName(STCNamespace, name)


# A sequence of tuples (dict builder, [stcxElementNames]) to handle
# STC-X elements by calling functions
_stcBuilders = [
	(_buildFloat, ["C1", "C2", "C3"]),
	(_buildVector, ["Value2", "Value3"]),
	(_buildRefpos, stcRefPositions),
	(_buildFlavor, stcCoordFlavors),
	(_buildRefFrame, stcSpaceRefFrames),
	(_buildPosition, ["Position3D", "Position2D"]),
	(_makeKWValueBuilder("resolution"), ["Resolution", "Resolution2",
		"Resolution3"]),
	(_makeKWValueBuilder("pixSize"), ["PixSize", "PixSize2",
		"PixSize3"]),
	(_passthrough, ["ObsDataLocation", "ObservatoryLocation",
		"ObservationLocation", "AstroCoords"]),
]

# A sequence of (stcElementName, kw, AST class) to handle
# STC-X elements by constructing an AST node and adding it to the
# parent's build dict under kw.
_stcNodeBuilders = [
	('TimeFrame', 'timeFrame', dm.TimeFrame),
	('SpaceFrame', 'spaceFrame', dm.SpaceFrame),
	('SpectralFrame', 'spectralFrame', dm.SpectralFrame),
	('RedshiftFrame', 'redshiftFrame', dm.RedshiftFrame),
]

def _getHandlers():
	handlers = {
		_n("AstroCoordSystem"): _buildAstroCoordSystem,
		_n("TimeScale"): _makeKeywordBuilder("timeScale"),
		_n("Timescale"): _makeKeywordBuilder("timeScale"),
	}
	for builder, stcEls in _stcBuilders:
		for el in stcEls:
			handlers[_n(el)] = builder
	for stcxName, astKey, astClass in _stcNodeBuilders:
		handlers[_n(stcxName)] = _makeNodeBuilder(astKey, astClass)
	return handlers

getHandlers = CachedGetter(_getHandlers)


def _getActiveTags():
	return {
		_n("AstroCoords"): CooSysActions(),
	}

getActiveTags = CachedGetter(_getActiveTags)


def parseSTCX(stcxLiteral):
	context = STCXContext(elementHandlers=getHandlers(),
		activeTags=getActiveTags())
	ast = dm.STCSpec(**dict(buildTree(
		ElementTree.fromstring(stcxLiteral), context)))
	resolveProxies(ast)
	return ast
