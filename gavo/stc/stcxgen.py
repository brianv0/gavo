"""
Converting ASTs to/from STC-X.

The basic idea for conversion to STC-X is that for every ASTNode in dm, there
is a serialize_<classname> function returning some xmlstan.  In general
they should handle the case when their argument is None and return None
in that case.

Traversal is done manually (i.e., by each serialize_X method) rather than
globally since the children in the AST may not have the right order to
keep XSD happy, and also since ASTs are actually a bit more complicated
than trees (e.g., coordinate frames usually have multiple parents).
"""

import itertools
import string

from gavo.stc import dm
from gavo.stc.common import *
from gavo.stc.stcx import STC


def intToFunnyWord(anInt, translation=string.maketrans(
		"-0123456789abcdef", 
		"zaeiousmnthwblpgd")):
	"""returns a sometimes funny (but unique) word from an arbitrary integer.
	"""
	return ("%x"%anInt).translate(translation)


def addId(node):
	"""adds a synthetic id attribute to node unless it's already
	there.
	"""
	if not hasattr(node, "id") or node.id is None:
		node.id = intToFunnyWord(id(node))


def strOrNull(val):
	if val is not None:
		return str(val)


def isoformatOrNull(val):
	if val is not None:
		return val.isoformat()
	

def _getFromSTC(elName, itemDesc):
	"""returns the STC element elName or raises an STCValueError if
	it does not exist.

	itemDesc is used in the error message.  This is a helper for
	concise notation of reference frames.
	"""
	try:
		return getattr(STC, elName)
	except AttributeError:
		raise STCValueError("No such %s: %s"%(itemDesc, elName))


############ Coordinate Systems

def serialize_RefPos(node):
	if node.standardOrigin is None:
		raise STCNotImplementedError("Cannot handle reference positions other"
			" than standard origins yet.")
	try:
		return getattr(STC, node.standardOrigin)
	except AttributeError:
		raise STCValueError("No such standard origin: %s"%node.standardOrigin)


def serialize_SpaceFrame(node):
	if node is None: return
	addId(node)
	return STC.SpaceFrame(id=node.id)[
		STC.Name[node.name], 
		_getFromSTC(node.refFrame, "reference frame")[
			STC.Equinox[strOrNull(node.equinox)]],
		serialize_RefPos(node.refPos),
		_getFromSTC(node.flavor, "coordinate flavor")(
			coord_naxes=strOrNull(node.nDim))]


def serialize_TimeFrame(node):
	if node is None: return
	addId(node)
	return STC.TimeFrame(id=node.id)[
		STC.Name[node.name],
		STC.TimeScale[node.timeScale],
		serialize_RefPos(node.refPos),
	]

def serialize_SpectralFrame(node):
	if node is None: return
	addId(node)
	return STC.SpectralFrame(id=node.id)[
		STC.Name[node.name],
		serialize_RefPos(node.refPos),
	]

def serialize_RedshiftFrame(node):
	if node is None: return
	addId(node)
	return STC.RedshiftFrame(id=node.id)[
		STC.Name[node.name],
		STC.DopplerDefinition[node.dopplerDef],
		serialize_RefPos(node.refPos),
	]

def serialize_CoordSys(node):
	addId(node)
	return STC.AstroCoordSystem(id=node.id)[
		serialize_TimeFrame(node.timeFrame),
		serialize_SpaceFrame(node.spaceFrame),
		serialize_SpectralFrame(node.spectralFrame),
		serialize_RedshiftFrame(node.redshiftFrame),]


############ Coordinates

def _wrapValues(element, valSeq, mapper=str):
	"""returns the items of valSeq as children of element, mapped with mapper.
	"""
	if valSeq is None:
		return []
	return [element[mapper(v)] for v in valSeq]


def _serialize_Wiggle(node, serializer, wiggles):
	if node is None:
		return
	cooClass, radiusClass, matrixClass = wiggles
	if isinstance(node, dm.CooWiggle):
		return _wrapValues(cooClass, node.values, serializer),
	elif isinstance(node, dm.RadiusWiggle):
		return [radiusClass[str(r)] for r in node.radii]
	elif isinstance(node, dm.MatrixWiggle):
		return [matrixClass[_wrapMatrix(m)] for m in node.matrices]
	else:
		STCValueError("Cannot serialize %s errors to STC-X"%
			node.__class__.__name__)


wiggleClasses = {
	"error": [
		(STC.Error, None, None),
		(STC.Error2, STC.Error2Radius, STC.Error2Matrix),
		(STC.Error3, STC.Error3Radius, STC.Error3Matrix),],
	"resolution": [
		(STC.Resolution, None, None),
		(STC.Resolution2, STC.Resolution2Radius, STC.Resolution2Matrix),
		(STC.Resolution3, STC.Resolution3Radius, STC.Resolution3Matrix),],
	"size": [
		(STC.Size, None, None),
		(STC.Size2, STC.Size2Radius, STC.Size2Matrix),
		(STC.Size3, STC.Size3Radius, STC.Size3Matrix),],
	"pixSize": [
		(STC.PixSize, None, None),
		(STC.PixSize2, STC.PixSize2Radius, STC.PixSize2Matrix),
		(STC.PixSize3, STC.PixSize3Radius, STC.PixSize3Matrix),],
}


def _make1DSerializer(cooClass, valueSerializer):
	"""returns a serializer returning a coordinate cooClass.

	This will only work for 1-dimensional coordinates.  valueSerializer
	is a function taking the coordinate's value and returning some
	xmlstan.
	"""
	def serialize(node):
		return cooClass(unit=node.unit, vel_time_unit=node.velTimeUnit,
				frame_id=node.frame.id)[
			valueSerializer(node.value),
			_wrapValues(STC.Error, getattr(node.error, "values", ())),
			_wrapValues(STC.Resolution, getattr(node.resolution, "values", ())),
			_wrapValues(STC.PixSize, getattr(node.pixSize, "values", ())),
		]
	return serialize

serialize_TimeCoo = _make1DSerializer(STC.Time,
	lambda value: STC.TimeInstant[STC.ISOTime[isoformatOrNull(value)]])
serialize_RedshiftCoo = _make1DSerializer(STC.Redshift,
	lambda value: STC.Value[str(value)])
serialize_SpectralCoo = _make1DSerializer(STC.Spectral,
	lambda value: STC.Value[str(value)])


def _wrap2D(val):
	return [STC.C1[val[0]], STC.C2[val[1]]]

def _wrap3D(val):
	return [STC.C1[val[0]], STC.C2[val[1]], STC.C3[val[2]]]

def _wrapMatrix(val):
	for rowInd, row in enumerate(val):
		for colInd, col in enumerate(row):
			yield getattr(STC, "M%d%d"%(rowInd, colInd))[str(col)]

positionClasses = (
	(STC.Position1D, STC.Value, str),
	(STC.Position2D, STC.Value2, _wrap2D),
	(STC.Position3D, STC.Value3, _wrap3D),
)

def serialize_SpaceCoo(node):
	"""serializes a spatial coordinate.

	This is quite messy since the concrete choice of elements depends on
	the coordinate frame.
	"""
	dimInd = node.frame.nDim-1
	coo, val, serializer = positionClasses[dimInd]
	return coo(unit=node.unit, frame_id=node.frame.id)[
			val[serializer(node.value)],
			[_serialize_Wiggle(getattr(node, wiggleType), 
					serializer, wiggleClasses[wiggleType][dimInd])
				for wiggleType in ["error", "resolution", "size", "pixSize"]],
		]


############# Intervals

def _make1DIntervalSerializer(intervClass, lowerClass, upperClass,
		valueSerializer):
	"""returns a serializer returning stan for a coordinate interval.

	This will only work for 1-dimensional coordinates.  valueSerializer
	is a function taking the coordinate's value and returning some
	xmlstan.

	Currently, error, resolution, and pixSize information is discarded
	for lack of a place to put them.
	"""
	def serialize(node):
		if isinstance(node.frame, dm.TimeFrame):
			unit = None  # time intervals have no units
		else:
			unit = node.unit
		return intervClass(unit=unit, vel_time_unit=node.velTimeUnit, 
				frame_id=node.frame.id, fill_factor=strOrNull(node.fillFactor))[
			lowerClass[valueSerializer(node.lowerLimit)],
			upperClass[valueSerializer(node.upperLimit)],
		]
	return serialize


serialize_TimeInterval = _make1DIntervalSerializer(STC.TimeInterval,
	STC.StartTime, STC.StopTime, lambda val: STC.ISOTime[isoformatOrNull(val)])
serialize_SpectralInterval = _make1DIntervalSerializer(STC.SpectralInterval,
	STC.LoLimit, STC.HiLimit, lambda val: str(val))
serialize_RedshiftInterval = _make1DIntervalSerializer(STC.RedshiftInterval,
	STC.LoLimit, STC.HiLimit, lambda val: str(val))


_posIntervalClasses = [
	(STC.PositionScalarInterval, STC.LoLimit, STC.HiLimit, str),
	(STC.Position2VecInterval, STC.LoLimit2Vec, STC.HiLimit2Vec,
		_wrap2D),
	(STC.Position3VecInterval, STC.LoLimit3Vec, STC.HiLimit3Vec,
		_wrap3D),]

def serialize_SpaceInterval(node):
	intervClass, lowerClass, upperClass, valueSerializer = \
		_posIntervalClasses[node.frame.nDim-1]
	return intervClass(unit=node.unit, vel_time_unit=node.velTimeUnit, 
				frame_id=node.frame.id, fill_factor=node.fillFactor)[
			lowerClass[valueSerializer(node.lowerLimit)],
			upperClass[valueSerializer(node.upperLimit)],
		]



############# Regions

def _makeBaseRegion(cls, node):
	return cls(unit=node.unit, frame_id=node.frame.id, 
		fill_factor=strOrNull(node.fillFactor))


def serialize_AllSky(node):
	return _makeBaseRegion(STC.AllSky, node)

def serialize_Circle(node):
# would you believe that the sequence of center and radius is swapped
# in sphere and circle?  Oh boy.
	if node.frame.nDim==2:
		return _makeBaseRegion(STC.Circle, node)[
			STC.Center[_wrap2D(node.center)],
			STC.Radius[node.radius],
		]
	elif node.frame.nDim==3:
		return _makeBaseRegion(STC.Sphere, node)[
			STC.Radius[node.radius],
			STC.Center[_wrap3D(node.center)],
		]
	else:
		raise STCValueError("Spheres are only defined in 2 and 3D")


def serialize_Ellipse(node):
	if node.frame.nDim==2:
		cls, wrap = STC.Ellipse, _wrap2D
	else:
		raise STCValueError("Ellipses are only defined in 2D")
	return _makeBaseRegion(cls, node)[
		STC.Center[wrap(node.center)],
		STC.SemiMajorAxis[node.smajAxis],
		STC.SemiMinorAxis[node.sminAxis],
		STC.PosAngle[node.posAngle],
	]


def serialize_Box(node):
	if node.frame.nDim!=2:
		raise STCValueError("Boxes are only available in 2D")
	return _makeBaseRegion(STC.Box, node)[
		STC.Center[_wrap2D(node.center)],
		STC.Size[_wrap2D(node.boxsize)]]


def serialize_Polygon(node):
	if node.frame.nDim!=2:
		raise STCValueError("Polygons are only available in 2D")
	return _makeBaseRegion(STC.Polygon, node)[
		[STC.Vertex[STC.Position[_wrap2D(v)]] for v in node.vertices]]


def serialize_Convex(node):
	return _makeBaseRegion(STC.Convex, node)[
		[STC.Halfspace[STC.Vector[_wrap3D(v[:3])], STC.Offset[v[3]]]
		for v in node.vectors]]


############# Toplevel

def makeAreas(rootNode):
	"""serializes the areas contained in rootNode.

	This requires all kinds of insane special handling.
	"""
	if not rootNode.areas:
		return
	elif len(rootNode.areas)==1:
		return nodeToStan(rootNode.areas[0])
	else:  # implicit union
		return STC.Region[
			STC.Union[
				[nodeToStan(n) for n in rootNode.areas]]]


def nodeToStan(astNode):
	"""returns xmlstan for whatever is in astNode.
	"""
	return globals()["serialize_"+astNode.__class__.__name__](astNode)


def astToStan(rootNode, stcRoot):
	"""returns STC stan for the AST rootNode wrapped in the stcRoot element.

	The first coordinate system defined in the AST is always used for
	the embedded coordinates and areas.
	"""
	return stcRoot[[nodeToStan(n) for n in rootNode.systems],
		STC.AstroCoords(coord_system_id=rootNode.systems[0].id)[
			[nodeToStan(n) for n in itertools.chain(rootNode.times,
				rootNode.places, rootNode.freqs, rootNode.redshifts)]
		],
		STC.AstroCoordArea(coord_system_id=rootNode.systems[0].id)[
			[nodeToStan(n) for n in rootNode.timeAs],
			makeAreas(rootNode),
			[nodeToStan(n) for n in 
				itertools.chain(rootNode.freqAs, rootNode.redshiftAs)]],
	]
