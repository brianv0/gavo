"""
Converting ASTs to/from STC-X.

The basic idea for conversion to STC-X is that for every ASTNode in dm, there
is a serialize_<classname> function returning some xmlstan.  In general
they should handle the case when their argument is None and return None
in that case.

Traversal is done manually (i.e., by each serialize_X method) rather than
globally to maintain the order of the children and thus keep XSD happy.
"""

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
	addId(node)
	try:
		frame = getattr(STC, node.refFrame)	
	except AttributeError:
		raise STCValueError("No such reference frame: %s"%node.refFrame)
	try:
		flavor = getattr(STC, node.flavor)(coord_naxes=strOrNull(node.nDim))
	except AttributeError:
		raise STCValueError("No such coordinate flavor: %s"%node.flavor)
	return STC.SpaceFrame(id=node.id)[
		STC.Name[node.name], 
		frame[STC.Equinox[strOrNull(node.equinox)]],
		serialize_RefPos(node.refPos),
		flavor]


def astToStan(astNode):
	"""returns xmlstan for whatever is in astNode.
	"""
	return globals()["serialize_"+astNode.__class__.__name__](astNode)
