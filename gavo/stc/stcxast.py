"""
Building ASTs from STC-X trees.
"""

from gavo.stc import dm
from gavo.stc import times
from gavo.stc.common import *


_xlinkHref = str(ElementTree.QName(XlinkNamespace, "href"))


####################### Helpers

def _n(name):
	return ElementTree.QName(STCNamespace, name)


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


def _makeKwValuesBuilder(kwName, tuplify=False):
	"""returns a builder that takes vals from the buildArgs and
	returns a tuple of them under kwName.

	The vals key is left by builders like _buildVector.
	"""
	if tuplify:
		def buildNode(node, buildArgs, context):
			yield kwName, (tuple(buildArgs["vals"]),)
	else:
		def buildNode(node, buildArgs, context):
			yield kwName, (buildArgs["vals"],)
	return buildNode


def _makeKwVectorBuilder(kwName):
	"""returns a builder that takes vals from the buildArgs and
	returns them as a vector in a tuple under kwName.

	The vals key is left by builders like _buildVector.
	"""
	def buildNode(node, buildArgs, context):
		yield kwName, (tuple(buildArgs["vals"]),)
	return buildNode


def _makeKwValueBuilder(kwName, tuplify=False):
	"""returns a builder that takes vals from the buildArgs and
	returns a single value under kwName.

	The vals key is left by builders like _buildVector.
	"""
	if tuplify:
		def buildNode(node, buildArgs, context):
			yield kwName, tuple(buildArgs["vals"]),
	else:
		def buildNode(node, buildArgs, context):
			yield kwName, buildArgs["vals"],
	return buildNode


def _makeKwFloatBuilder(kwName, unitKey="pos_unit", multiple=True):
	"""returns a builder that returns float(node.text) under kwName.

	The builder will also add a <kwName>Unit key if appropriate.

	If multiple is True, the keys will be returned in tuples, else as
	simple values.
	"""
	if multiple:
		def buildNode(node, buildArgs, context):
			yield kwName, (float(node.text),)
			if unitKey in node.attrib:
				yield kwName+'Unit', (node.get(unitKey),)
	else:
		def buildNode(node, buildArgs, context):
			yield kwName, float(node.text)
			if unitKey in node.attrib:
				yield kwName+'Unit', node.get(unitKey)
	return buildNode


def _makeNodeBuilder(kwName, astObject):
	"""returns a builder that makes astObject with the current buildArgs
	and returns the thing under kwName.
	"""
	def buildNode(node, buildArgs, context):
		buildArgs["id"] = node.get(id, None)
		yield kwName, astObject(**buildArgs)
	return buildNode


def _iterCooMeta(node, context, frameName):
	"""yields various meta information for coordinate-like objects.
	
	For frame, it returns a proxy for a coordinate's reference frame.
	For unit, if one is given on the element, override whatever we may 
	have got from downtree.

	Rules for inferring the frame:

	If there's a frame id on node, use it. 
	
	Else see if there's a coo sys id on the frame.  If it's missing, take 
	it from the context, then make a proxy to the referenced system's 
	spatial frame.
	"""
	if "frame_id" in node.attrib:
		yield "frame", IdProxy(idref=node["frame_id"])
	elif "coord_system_id" in node.attrib:
		yield "frame", IdProxy(idref=node["frame_id"], useAttr=frameName)
	else:
		yield "frame", IdProxy(idref=context.sysIdStack[-1], 
			useAttr=frameName)
	if "unit" in node.attrib and node.get("unit"):
		yield "unit", node.get("unit")
	if "fill_factor" in node.attrib and node.get("fill_factor"):
		yield "fillFactor", float(node.get("fill_factor"))


def _makeIntervalBuilder(kwName, astClass, frameName):
	"""returns a builder that makes astObject with the current buildArgs
	and fixes its frame reference.
	"""
	def buildNode(node, buildArgs, context):
		for key, value in _iterCooMeta(node, context, frameName):
			buildArgs[key] = value
		if "lowerLimit" in buildArgs:
			buildArgs["lowerLimit"] = buildArgs["lowerLimit"][0]
		if "upperLimit" in buildArgs:
			buildArgs["upperLimit"] = buildArgs["upperLimit"][0]
		yield kwName, (astClass(**buildArgs),)
	return buildNode


def _fixWiggles(buildArgs):
	"""modifies buildArgs so all wiggles are properly wrapped in their
	classes.
	"""
	for wiggleType in ["error", "resolution", "size", "pixSize"]:
		if wiggleType in buildArgs:
			buildArgs[wiggleType] = dm.CooWiggle(values=tuple(buildArgs[wiggleType]))
		if wiggleType+"Radius" in buildArgs:
			buildArgs[wiggleType] = dm.RadiusWiggle(
				radii=buildArgs[wiggleType+"Radius"])
			del buildArgs[wiggleType+"Radius"]
		if wiggleType+"Matrix" in buildArgs:
			buildArgs[wiggleType] = dm.MatrixWiggle(
				matrices=buildArgs[wiggleType+"Matrix"])
			del buildArgs[wiggleType+"Matrix"]


def _makePositionBuilder(kw, astClass, frameName):
	"""returns a builder for a coordinate of astClass to be added with kw.
	"""
	def buildPosition(node, buildArgs, context):
		if buildArgs.get("vals"):
			buildArgs["value"] = buildArgs["vals"][0]
			del buildArgs["vals"]
		for key, value in _iterCooMeta(node, context, frameName):
			buildArgs[key] = value
		_fixWiggles(buildArgs)
		yield kw, (astClass(**buildArgs),)
	return buildPosition


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

class CooSysActions(ContextActions):
	"""Actions for containers of coordinates.

	The actions push and pop the system ids of the containers.  If
	no system ids are present, None is pushed.
	"""
	def start(self, context, node):
		context.sysIdStack.append(node.get("coord_system_id", None))
	
	def stop(self, context, node):
		context.sysIdStack.pop()


def _buildTime(node, buildArgs, context):
	"""adds vals from the time node.

	node gets introspected to figure out what kind of time we're talking
	about.  The value always is a datetime instance.
	"""
	parser = {
		"ISOTime": times.parseISODT,
		"JDTime": lambda v: times.jdnToDateTime(float(v)),
		"MJDTime": lambda v: times.mjdToDateTime(float(v)),
	}[_localname(node.tag)]
	yield "vals", (parser(node.text),)

_buildFloat = _makeKwFloatBuilder("vals")

def _buildVector(node, buildArgs, context):
	yield 'vals', (tuple(buildArgs["vals"]),)
	if "valsUnit" in buildArgs:
		yield "unit", " ".join(buildArgs["valsUnit"])


################# Geometries

class BoxActions(ContextActions):
	"""Context actions for Boxes: register a special handler for Size.
	"""
	boxHandlers = {
		_n("Size"): _makeKwValueBuilder("boxsize", tuplify=True),
	}
	def start(self, context, node):
		context.specialHandlerStack.append(self.boxHandlers)
	def stop(self, context, node):
		context.specialHandlerStack.pop()


def _buildHalfspace(node, buildArgs, context):
	yield "vectors", (tuple(buildArgs["vector"])+tuple(buildArgs["offset"]),)


def _makeGeometryBuilder(astClass):
	"""returns a builder for STC-S geometries.
	"""
	def buildGeo(node, buildArgs, context):
		for key, value in _iterCooMeta(node, context, "spaceFrame"):
			buildArgs[key] = value
		yield 'areas', (astClass(**buildArgs),)
	return buildGeo


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
	if context.getHandler(csNode.tag) is None:
		return
	if csNode.tag in context.activeTags:
		context.startTag(csNode)
	for child in csNode:
		for res in buildTree(child, context):
			if res is None:  # ignored child
				continue
			k, v = res
			if isinstance(v, (tuple, list)):
				resDict[k] = resDict.get(k, ())+v
			else:
				if k in resDict:
					raise STCInternalError("Attempt to overwrite key '%s', old"
						" value %s, new value %s (this should probably have been"
						" a tuple)"%(k, resDict[k], v))
				resDict[k] = v
	for res in context.getHandler(csNode.tag)(csNode, resDict, context):
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
		self.specialHandlerStack = [{}]
		self.elementHandlers = elementHandlers
		self.idMap = {}
		self.activeTags = activeTags
		for k, v in kwargs.iteritems():
			setattr(self, k, v)

	def getHandler(self, elementName):
		"""returns a builder for the qName elementName.

		If no such handler exists, we return None.
		"""
		if elementName in self.specialHandlerStack[-1]:
			return self.specialHandlerStack[-1][elementName]
		return self.elementHandlers.get(elementName)

	def startTag(self, node):
		self.activeTags[node.tag].start(self, node)

	def endTag(self, node):
		self.activeTags[node.tag].stop(self, node)


# A sequence of tuples (dict builder, [stcxElementNames]) to handle
# STC-X elements by calling functions
_stcBuilders = [
	(_buildFloat, ["C1", "C2", "C3"]),
	(_buildTime, ["ISOTime", "JDTime", "MJDTime"]),
	(_buildVector, ["Value2", "Value3"]),
	(_buildRefpos, stcRefPositions),
	(_buildFlavor, stcCoordFlavors),
	(_buildRefFrame, stcSpaceRefFrames),

	(_makePositionBuilder('places', dm.SpaceCoo, "spaceFrame"), 
		["Position3D", "Position2D"]),

	(_makeKwValuesBuilder("resolution", tuplify=True), 
		["Resolution2", "Resolution3"]),
	(_makeKwValuesBuilder("pixSize", tuplify=True), 
		["PixSize2", "PixSize3"]),
	(_makeKwValuesBuilder("error", tuplify=True), 
		["Error2", "Error3"]),
	(_makeKwValuesBuilder("size", tuplify=True), 
		["Size2", "Size3"]),

	(_makeKwFloatBuilder("resolutionRadius"), 
		["Resolution2Radius", "Resolution3Radius"]),
	(_makeKwFloatBuilder("pixSizeRadius"), 
		["PixSize2Radius", "PixSize3Radius"]),
	(_makeKwFloatBuilder("errorRadius"), ["Error2Radius", "Error3Radius"]),
	(_makeKwFloatBuilder("sizeRadius"), ["Size2Radius", "Size3Radius"]),

	(_makeKwValuesBuilder("resolutionMatrix"), 
		["Resolution2Matrix", "Resolution3Matrix"]),
	(_makeKwValuesBuilder("pixSizeMatrix"), 
		["PixSize2Matrix", "PixSize3Matrix"]),
	(_makeKwValuesBuilder("errorMatrix"), ["Error2Matrix", "Error3Matrix"]),
	(_makeKwValuesBuilder("sizeMatrix"), ["Size2Matrix", "Size3Matrix"]),

	(_makeKwVectorBuilder("upperLimit"), ["HiLimit2Vec", "HiLimit3Vec"]),
	(_makeKwVectorBuilder("lowerLimit"), ["LoLimit2Vec", "LoLimit3Vec"]),

	(_makeIntervalBuilder("areas", dm.SpaceInterval, "spaceFrame"),
		["PositionScalarInterval", "Position2VecInterval",
			"Position3VecInterval"]),
	(_makeGeometryBuilder(dm.AllSky), ["AllSky", "AllSky2"]),
	(_makeGeometryBuilder(dm.Circle), ["Circle", "Circle2"]),
	(_makeGeometryBuilder(dm.Ellipse), ["Ellipse", "Ellipse2"]),
	(_makeGeometryBuilder(dm.Box), ["Box", "Box2"]),
	(_makeGeometryBuilder(dm.Polygon), ["Polygon", "Polygon2"]),
	(_makeGeometryBuilder(dm.Convex), ["Convex", "Convex2"]),

	(_passthrough, ["ObsDataLocation", "ObservatoryLocation",
		"ObservationLocation", "AstroCoords", "TimeInstant",
		"AstroCoordArea", "STCResourceProfile"]),
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
		_n("Error"): _makeKwFloatBuilder("error"),
		_n("PixSize"): _makeKwFloatBuilder("pixSize"),
		_n("Redshift"): _makePositionBuilder('redshifts', dm.RedshiftCoo, "redshiftFrame"), 
		_n("Resolution"): _makeKwFloatBuilder("resolution"),
		_n("Size"): _makeKwFloatBuilder("size"),
		_n("Spectral"): _makePositionBuilder('freqs', dm.SpectralCoo, "spectralFrame"), 
		_n("StartTime"): _makeKwValueBuilder("lowerLimit"),
		_n("StopTime"): _makeKwValueBuilder("upperLimit"),
		_n("LoLimit"): _makeKwFloatBuilder("lowerLimit"),
		_n("HiLimit"): _makeKwFloatBuilder("upperLimit"),
		_n("Time"): _makePositionBuilder('times', dm.TimeCoo, "timeFrame"),
		_n("Timescale"): _makeKeywordBuilder("timeScale"),
		_n("TimeScale"): _makeKeywordBuilder("timeScale"),
		_n("Value"): _makeKwFloatBuilder("vals"),

		_n("Radius"): _makeKwFloatBuilder("radius", multiple=False, 
			unitKey="unit"), 
		_n("Center"): _makeKwValueBuilder("center", tuplify=True), 
		_n("SemiMajorAxis"): _makeKwFloatBuilder("smajAxis", multiple=False,
			unitKey="unit"),
		_n("SemiMinorAxis"): _makeKwFloatBuilder("sminAxis", multiple=False,
			unitKey="unit"),
		_n("PosAngle"): _makeKwFloatBuilder("posAngle", multiple=False,
			unitKey="unit"),
		_n("Vertex"): _makeKwValuesBuilder("vertices", tuplify=True), 
		_n("Vector"): _makeKwValueBuilder("vector", tuplify=True),
		_n("Offset"): _makeKwFloatBuilder("offset"),
		_n("Halfspace"): _buildHalfspace,

		_n("TimeInterval"): _makeIntervalBuilder("timeAs", dm.TimeInterval,
			"timeFrame"),
		_n("SpectralInterval"): _makeIntervalBuilder("freqAs", dm.SpectralInterval,
			"spectralFrame"),
		_n("RedshiftInterval"): _makeIntervalBuilder("redshiftAs", 
			dm.RedshiftInterval, "redshiftFrame"),
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
		_n("AstroCoordArea"): CooSysActions(),
		_n("Box"): BoxActions(),
	}

getActiveTags = CachedGetter(_getActiveTags)


def parseSTCX(stcxLiteral):
	context = STCXContext(elementHandlers=getHandlers(),
		activeTags=getActiveTags())
	ast = dm.STCSpec(**dict(buildTree(
		ElementTree.fromstring(stcxLiteral), context)))
	resolveProxies(ast)
	return ast
