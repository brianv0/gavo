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
		serialize_RefPos(node.refPos),
		STC.TimeScale[node.timeScale],
	]

def serialize_SpectralFrame(node):
	if node is None: return
	addId(node)
	return STC.TimeFrame(id=node.id)[
		STC.Name[node.name],
		serialize_RefPos(node.refPos),
	]

def serialize_RedshiftFrame(node):
	if node is None: return
	addId(node)
	return STC.TimeFrame(id=node.id)[
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


def serialize_TimeCoo(node):
	return STC.Time(frame_id=node.frame.id)[
		STC.TimeInstant[
			STC.ISOTime[
				node.value.isoformat()]],
		_wrapValues(STC.Error, node.error),
		_wrapValues(STC.Resolution, node.resolution),
		_wrapValues(STC.Size, node.size),
		_wrapValues(STC.PixSize, node.pixSize),
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
			[nodeToStan(n) for n in itertools.chain(rootNode.times)]
		],
	]
