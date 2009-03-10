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
	if not hasattr(node, "id"):
		node.id = intToFunnyWord(id(node))


def strOrNull(val):
	if val is not None:
		return str(val)


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


def _make1DSerializer(cooClass, valueSerializer):
	"""returns a serializer returning a coordinate cooClass.

	This will only work for 1-dimensional coordinates.  valueSerializer
	is a function taking the coordinate's value and returning some
	xmlstan.
	"""
	def serialize(node):
		return cooClass(unit=node.unit, frame_id=node.frame.id)[
			valueSerializer(node.value),
			_wrapValues(STC.Error, node.error),
			_wrapValues(STC.Resolution, node.resolution),
			_wrapValues(STC.PixSize, node.pixSize),
		]
	return serialize

serialize_TimeCoo = _make1DSerializer(STC.Time,
	lambda value: STC.TimeInstant[STC.ISOTime[value.isoformat()]])
serialize_RedshiftCoo = _make1DSerializer(STC.Redshift,
	lambda value: STC.Value[str(value)])
serialize_SpectralCoo = _make1DSerializer(STC.Spectral,
	lambda value: STC.Value[str(value)])


def _wrap2D(val):
	return [STC.C1[val[0]], STC.C2[val[1]]]

def _wrap3D(val):
	return [STC.C1[val[0]], STC.C2[val[1]], STC.C3[val[2]]]


positionClasses = (
	(STC.Position1D, STC.Value, STC.Error, STC.Resolution, 
		STC.Size, STC.PixSize, str),
	(STC.Position2D, STC.Value2, STC.Error2, STC.Resolution2, 
		STC.Size2, STC.PixSize2, _wrap2D),
	(STC.Position3D, STC.Value3, STC.Error3, STC.Resolution3, 
		STC.Size3, STC.PixSize, _wrap3D),
)

def serialize_SpaceCoo(node):
	"""serializes a spatial coordinate.

	This is quite messy since the concrete choice of elements depends on
	the coordinate frame.
	"""
	coo, val, err, res, siz, psz, serializer = positionClasses[node.frame.nDim-1]
	return coo(unit=node.unit, frame_id=node.frame.id)[
			val[serializer(node.value)],
			_wrapValues(err, node.error, serializer),
			_wrapValues(res, node.resolution, serializer),
			_wrapValues(siz, node.size, serializer),
			_wrapValues(psz, node.pixSize, serializer),
		]


############# Toplevel

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
	]
