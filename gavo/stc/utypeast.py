"""
Parse utype sets into ASTs.

The rough plan is to build an ElementTree from a pair of dictionaries,
systemDict and columnDict, as returned by utypegen.getUtypes.  This
ElementTree can then be used to build an AST using stcxast.  The ElementTree
contains common.ColRefs and thus cannot be serialized to an XML string.

Most of the magic happens in utypeParseToTree, where the utypes are
dissected; it is important that the utypes sequence passed to this
is sorted such that utypes for things below an STC-X node are actually
immediately below the utype pair for their parent.
"""

import itertools

from gavo import utils
from gavo.stc import common
from gavo.stc import stcxast
from gavo.utils import ElementTree


def parseUtype(utype):
	if utype is None:
		return None
	return tuple(utype.split(":")[-1].split("."))


class _Attribute(object):
	"""a "value" for utypePairsToTree that causes an attribute to be set
	on an element.

	This is something a morph function would return.
	"""
	def __init__(self, name, value):
		self.name, self.value = name, value


def _unifyTuples(fromTuple, toTuple):
	"""returns a pair fromTail, toTail of tuples to bring fromTuple to toTuple.

	This is done such that fromTuple-fromTuple+toTail=toTuple for "appending"
	semantics.
	"""
	if toTuple is None:
		return (), ()
	prefixLen = utils.commonPrefixLength(fromTuple, toTuple)
	return fromTuple[prefixLen:], toTuple[prefixLen:]


def _replaceLastWithValue(utype, value):
	yield ".".join(parseUtype(utype)[:-1])+"."+value, None

def _makeCoordFlavor(utype, value):
	# in addition to fixing syntax, we give a default for coord_naxis.
	# User settings would overwrite that.
	for pair in _replaceLastWithValue(utype, value):
		yield pair
	yield None, _Attribute("coord_naxes", "2")

def _makeAttributeMaker(attName):
	def makeAttribute(utype, value):
		yield None, _Attribute(attName, value)
	return makeAttribute

def _makeParentAttributeMaker(attName):
	def makeAttribute(utype, value):
		yield ".".join(parseUtype(utype)[:-1]), _Attribute(attName, value)
	return makeAttribute

def _replaceUtype(utype):
	def replacer(_, value):
		yield utype, value
	return replacer


_utypeMorphers = {
	'AstroCoordSystem.RedshiftFrame.ReferencePosition': _replaceLastWithValue,
	'AstroCoordSystem.RedshiftFrame.value_type': 
		_makeParentAttributeMaker("value_type"),
	'AstroCoordSystem.SpaceFrame.CoordFlavor': _makeCoordFlavor,
	'AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes': 
		_makeAttributeMaker("coord_naxes"),
	'AstroCoordSystem.SpaceFrame.CoordRefFrame': _replaceLastWithValue,
	'AstroCoordSystem.SpaceFrame.CoordRefFrame.Equinox': 
		_replaceUtype('AstroCoordSystem.SpaceFrame.Equinox'),
	'AstroCoordSystem.SpaceFrame.ReferencePosition': _replaceLastWithValue,
	'AstroCoordSystem.SpectralFrame.ReferencePosition': _replaceLastWithValue,
	'AstroCoordSystem.TimeFrame.ReferencePosition': _replaceLastWithValue,
}

def utypePairsToTree(utypes, nameQualifier=stcxast.STCElement):
	"""returns an ElementTree from a sequence of (utype, value) pairs.

	nameQualifier(str) -> anything is a function producing element names.

	The utypes are processed as they come in.  In practice this means
	you should sort them (or similar).

	The utype can be none, meaning "Use last node".
	"""
	root = ElementTree.Element(nameQualifier("STCSpec"))
	curParts, elementStack = (), [root]
	for parts, val in ((parseUtype(u), v) for u, v in utypes):
		toClose, toOpen = _unifyTuples(curParts, parts)
		if toClose or toOpen:  # move in utype tree
			curParts = parts

		for elName in toClose:
			elementStack.pop()
		for elName in toOpen:
			elementStack.append(
				ElementTree.SubElement(elementStack[-1], nameQualifier(elName)))

		# _Attributes get special handling
		if isinstance(val, _Attribute):
			elementStack[-1].attrib[val.name] = val.value

		# All other values go to the element content; if nothing was
		# opened or closed, add another node rather than clobbering the
		# last one.
		else: 
			if not toClose and not toOpen:
				elementStack.pop()
				elementStack.append(ElementTree.SubElement(
					elementStack[-1], nameQualifier(curParts[-1])))
			elementStack[-1].text = val
	return root


def morphUtypes(morphers, utypeSeq):
	"""returns a morphed sequence of utype/value pairs.

	morphers is a dictionary of utypes to handling generators.  Each of
	those most take a utype and a value and generate utype/value pairs.

	This is used here to fix the abominations where system elements become
	values in utype representation.
	"""
	for index, (k, v) in enumerate(utypeSeq):
		if k in morphers:
			for pair in morphers[k](k, v):
				yield pair
		else:
			yield (k, v)


def _utypeDictsToUtypeSeq(sysDict, colDict):
	"""returns a sorted sequence of utype, value pairs from sys/colDict.

	The keys of colDict get wrapped into ColRefs while doing that.
	"""
	colIter = ((v, common.ColRef(k)) for k, v in colDict.iteritems())
#	colIter = ((v, k) for k, v in colDict.iteritems())
	return sorted(itertools.chain(sysDict.iteritems(), colIter))


def parseFromUtypes(sysDict, colDict):
	eTree = utypePairsToTree(
		morphUtypes(_utypeMorphers,
			_utypeDictsToUtypeSeq(sysDict, colDict)))
	return stcxast.parseFromETree(eTree)[0][1]
