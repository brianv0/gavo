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


_unitKeys = ["pos_angle_unit", "pos_unit", "spectral_unit", "time_unit",
	"vel_time_unit"]


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


def _makeKwFloatBuilder(kwName, multiple=True):
	"""returns a builder that returns float(node.text) under kwName.

	The builder will also yield unit keys if units are present.

	If multiple is True, the keys will be returned in tuples, else as
	simple values.
	"""
	if multiple:
		def buildNode(node, buildArgs, context):
			yield kwName, (float(node.text),)
			for unitKey in _unitKeys:
				if unitKey in node.attrib:
					yield unitKey, (node.get(unitKey),)
	else:
		def buildNode(node, buildArgs, context):
			yield kwName, float(node.text)
			for unitKey in _unitKeys:
				if unitKey in node.attrib:
					yield unitKey, node.get(unitKey)
	return buildNode


def _makeNodeBuilder(kwName, astObject):
	"""returns a builder that makes astObject with the current buildArgs
	and returns the thing under kwName.
	"""
	def buildNode(node, buildArgs, context):
		buildArgs["id"] = node.get("id", None)
		yield kwName, astObject(**buildArgs)
	return buildNode


def _fixSpectralUnits(node, buildArgs, context):
	unit = None
	if "unit" in node.attrib:
		unit = node.get("unit")
	if "unit" in buildArgs:
		unit = buildArgs["unit"]
	if "spectral_unit" in buildArgs:
		unit = buildArgs["spectral_unit"]
		del buildArgs["spectral_unit"]
	buildArgs["unit"] = unit


def _fixTimeUnits(node, buildArgs, context):
	unit = None
	if "unit" in node.attrib:
		unit = node.get("unit")
	if "unit" in buildArgs:
		unit = buildArgs["unit"]
	if "time_unit" in buildArgs:
		unit = buildArgs["time_unit"]
		del buildArgs["time_unit"]
	buildArgs["unit"] = unit


def _fixRedshiftUnits(node, buildArgs, context):
	sUnit = node.get("unit")
	if "unit" in buildArgs:
		sUnit = buildArgs["unit"]
	if "pos_unit" in buildArgs:
		sUnit = buildArgs["pos_unit"]
		del buildArgs["pos_unit"]
	vUnit = node.get("vel_time_unit")
	if "vel_time_unit" in buildArgs:
		vUnit = buildArgs["vel_time_unit"]
		del buildArgs["vel_time_unit"]
	buildArgs["unit"] = sUnit
	buildArgs["velTimeUnit"] = vUnit


def _fixSpatialUnits(node, buildArgs, context):
	nDim = 1
	# Incredible hack to figure out the number of units we expect.
	if "2" in _localname(node.tag):
		nDim = 2
	if "3" in _localname(node.tag):
		nDim = 3
	unit, units = node.get("unit"), None
	if "units" in buildArgs:
		units = buildArgs["units"]
	if "pos_unit" in buildArgs:
		units = buildArgs["pos_unit"]
		del buildArgs["pos_unit"]
	if units is None and unit is not None:
		parts = unit.split()
		if len(parts)==nDim:
			units = tuple(parts)
		else:
			units = (unit,)*nDim
	buildArgs["units"] = units


_unitFixers = {
	"spectralFrame": _fixSpectralUnits,
	"redshiftFrame": _fixRedshiftUnits,
	"timeFrame": _fixTimeUnits,
	"spaceFrame": _fixSpatialUnits,
}

def _fixUnits(frameName, node, buildArgs, context):
	"""changes the keys in buildArgs to match the requirements of node.

	This fans out to frame type-specific helper functions.  The principle is:
	Attributes inherited from lower-level items (i.e. the specific values)
	override a unit specification on node.
	"""
	return _unitFixers[frameName](node, buildArgs, context)


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
		yield "frame", IdProxy(idref=node.get("frame_id"))
	elif "coord_system_id" in node.attrib:
		yield "frame", IdProxy(idref=node.get("frame_id"), useAttr=frameName)
	else:
		yield "frame", IdProxy(idref=context.sysIdStack[-1], 
			useAttr=frameName)
	if "fill_factor" in node.attrib and node.get("fill_factor"):
		yield "fillFactor", float(node.get("fill_factor"))
	if "id" in node.attrib and node.get("id"):
		yield "id", node.get("id")


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
		_fixUnits(frameName, node, buildArgs, context)
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
		_fixUnits(frameName, node, buildArgs, context)
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
	yield "astroSystem", newEl


def _buildRefpos(node, buildArgs, context):
	yield 'refPos', dm.RefPos(standardOrigin=_localname(node.tag))

def _buildFlavor(node, buildArgs, context):
	yield 'flavor', _localname(node.tag)
	yield 'nDim', int(node.get("coord_naxes"))

def _buildRefFrame(node, buildArgs, context):
	yield 'refFrame', _localname(node.tag)
	for item in buildArgs.iteritems():
		yield item

def _buildRedshiftFrame(node, buildArgs, context):
	if "value_type" in node.attrib:
		buildArgs["type"] = node.get("value_type")
	buildArgs["id"] = node.get("id")
	yield "redshiftFrame", dm.RedshiftFrame(**buildArgs)


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
	if "pos_unit" in buildArgs:
		yield "units", tuple(buildArgs["pos_unit"])


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
		_fixSpatialUnits(node, buildArgs, context)
		yield 'areas', (astClass(**buildArgs),)
	return buildGeo


################# Toplevel

def _buildToplevel(node, buildArgs, context):
	yield 'stcSpec', (dm.STCSpec(**buildArgs),)

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


def resolveProxies(asf):
	"""replaces IdProxies in the AST sequence asf with actual references.
	"""
	map = {}
	for ast in asf:
		ast.buildIdMap()
		map.update(ast.idMap)
	for ast in asf:
		for node in ast.iterNodes():
			for attName, value in node.iterAttributes(skipEmpty=True):
				if isinstance(value, IdProxy):
					setattr(node, attName, value.resolve(map))


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

	(_buildToplevel, ["ObservatoryLocation", "ObservationLocation",
		"STCResourceProfile"]),
	(_passthrough, ["ObsDataLocation", "AstroCoords", "TimeInstant",
		"AstroCoordArea", "Position"]),
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
		_n("Equinox"): _makeKeywordBuilder("equinox"),
		_n("Value"): _makeKwFloatBuilder("vals"),

		_n("Radius"): _makeKwFloatBuilder("radius", multiple=False),
		_n("Center"): _makeKwValueBuilder("center", tuplify=True), 
		_n("SemiMajorAxis"): _makeKwFloatBuilder("smajAxis", multiple=False),
		_n("SemiMinorAxis"): _makeKwFloatBuilder("sminAxis", multiple=False),
		_n("PosAngle"): _makeKwFloatBuilder("posAngle", multiple=False),
		_n("Vertex"): _makeKwValuesBuilder("vertices", tuplify=True), 
		_n("Vector"): _makeKwValueBuilder("vector", tuplify=True),
		_n("Offset"): _makeKwFloatBuilder("offset"),
		_n("Halfspace"): _buildHalfspace,
	
		_n('TimeFrame'): _makeNodeBuilder('timeFrame', dm.TimeFrame),
		_n('SpaceFrame'): _makeNodeBuilder('spaceFrame', dm.SpaceFrame),
		_n('SpectralFrame'): _makeNodeBuilder('spectralFrame', dm.SpectralFrame),
		_n('RedshiftFrame'): _buildRedshiftFrame,


		_n("DopplerDefinition"): _makeKeywordBuilder("dopplerDef"),
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
	"""returns a sequence of ASTs for the STC specifications in the STC-X literal.
	"""
	context = STCXContext(elementHandlers=getHandlers(),
		activeTags=getActiveTags())
	asf = dict(buildTree(ElementTree.fromstring(stcxLiteral), context)
		)["stcSpec"]
	resolveProxies(asf)
	return asf
