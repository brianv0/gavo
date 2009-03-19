"""
Converting ASTs to STC-S.

The strategy here is to first generate an STCS CST, remove defaults from it
and then flatten out the whole thing.

The AST serializers here either return a dictionary, which is then
updated to the current node's dictionary, or a tuple of key and value,
which is then added to the current dictionary.
"""

import itertools

from gavo.stc import dm
from gavo.stc import stcs
from gavo.stc.common import *


def _combine(*dicts):
	"""updates the first dictionary with all further ones and returns it.

	If duplicate keys exist, later arguments will overwrite values set
	by earlier arguments.
	"""
	res = dicts[0]
	for d in dicts[1:]:
		res.update(d)
	return res


############## Reference Frames to CST

def refPosToCST(node):
	if node.standardOrigin is None:
		raise STCNotImplementedError("Cannot handle reference positions other"
			" than standard origins yet.")
	return {"refpos": node.standardOrigin}

stcsFlavors = {
	(2, "SPHERICAL"): "SPHER2",
	(3, "SPHERICAL"): "SPHER3",
	(3, "UNITSPHERE"): "UNITSPHER",
	(1, "CARTESIAN"): "CART1",
	(2, "CARTESIAN"): "CART2",
	(3, "CARTESIAN"): "CART3",
}

def _computeFlavor(node):
	try:
		return stcsFlavors[(node.nDim, node.flavor)]
	except KeyError:
		raise STCValueError("Coordinate Frame %s cannot be represented it STC-S"%
			node)

def _spaceFrameToCST(node):
	return _combine({
		"flavor": _computeFlavor(node),
		"frame": node.refFrame,
		"equinox": node.equinox,},
		refPosToCST(node.refPos))

def _timeFrameToCST(node):
	return _combine({
		"timescale": node.timeScale,},
		refPosToCST(node.refPos))

def _spectralFrameToCST(node):
	return refPosToCST(node.refPos)

def _redshiftFrameToCST(node):
	return _combine({
		"redshiftType": node.type,
		"dopplerdef": node.dopplerDef,},
		refPosToCST(node.refPos))


############### Coordinates to CST

def _makeUnit(node):
	"""returns unit/velTimeUnit if velTimeUnit is defined, unit otherwise.
	"""
	if node.velTimeUnit:
		return "%s/%s"%(node.unit, node.velTimeUnit)
	return node.unit


def _flattenVectors(aList):
	"""flattens aList if it is made up of tuples, returns it unchanged otherwise.
	"""
	if not aList:
		return aList
	elif isinstance(aList[0], tuple):
		return list(itertools.chain(*aList))
	else:
		return aList


def _wiggleToCST(node, nDim):
	if node is None:
		return
	if isinstance(node, dm.CooWiggle):
		return node.values
	elif isinstance(node, dm.RadiusWiggle):
		return tuple(itertools.chain(*[(r,)*nDim for r in node.radii]))
	else:
		raise STCValueError("Cannot serialize %s errors into STC-S"%
			node.__class__.__name__)


def _makeBasicCooMaker(frameMaker):
	def toCST(node):
		nDim = node.frame.nDim
		return _combine({
			"error": _wiggleToCST(node.error, nDim),
			"resolution": _wiggleToCST(node.resolution, nDim),
			"pixSize": _wiggleToCST(node.pixSize, nDim),
			"unit": _makeUnit(node),},
			frameMaker(node.frame))
	return toCST


def _makeCooTreeMapper(cooType):
	def toCST(node):
		return {
			"type": cooType,
			"coos": (node.value,),}
	return toCST


def _makeAreaTreeMapper(intervalType, cooMaker):
	def toCST(node, positions):
		coos, pos = cooMaker(node, positions)
		return {
			"type": intervalType,
			"coos": coos,
			"pos": pos,}
	return toCST


def _makeIntervalTreeMapper(intervalType):
	def makeCoos(node, positions):
		if node.lowerLimit and node.upperLimit:
			coos = [c for c in (node.lowerLimit, node.upperLimit) if c is not None]
		pos = None
		if positions:
			pos = positions[0]
		return coos, pos
	return _makeAreaTreeMapper(intervalType, makeCoos)


def _timeIntervalToCST(node, times):
# Special-cased since these have (Start|Stop)Time
	if node.lowerLimit and node.upperLimit:
		type, coos = "TimeInterval", (node.lowerLimit, node.upperLimit)
	elif node.lowerLimit:
		type, coos = "StartTime", (node.lowerLimit,)
	elif node.upperLimit:
		type, coos = "StopTime", (node.upperLimit,)
	else:
		type, coos = "TimeInterval", ()
	pos = None
	if times:
		pos = times[0]
	return {
		"type": type,
		"coos": coos,
		"pos": pos}


def _makePhraseTreeMapper(cooMapper, areaMapper, basicArgsMaker):
	def toCST(coos, areas):
		if areas:
			node = areas[0]
			res = areaMapper(areas[0], coos)
		elif coos:
			node = coos[0]
			res = cooMapper(coos[0])
		else:
			return {}
		return _combine(res,
			basicArgsMaker(node))
	return toCST


def _basicSpatialCoosToCST(node, getBase=_makeBasicCooMaker(_spaceFrameToCST)):
	cstNode = getBase(node)
	cstNode["size"] = _wiggleToCST(node.size, node.frame.nDim)
	return cstNode


_timeToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Time"),
	_timeIntervalToCST,
	_makeBasicCooMaker(_timeFrameToCST))
_simpleSpatialToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Position"),
	_makeIntervalTreeMapper("PositionInterval"),
	_basicSpatialCoosToCST)
_spectralToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Spectral"),
	_makeIntervalTreeMapper("SpectralInterval"),
	_makeBasicCooMaker(_spectralFrameToCST))
_redshiftToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Redshift"),
	_makeIntervalTreeMapper("RedshiftInterval"),
	_makeBasicCooMaker(_redshiftFrameToCST))


def _makeGeometryMapper(intervalType, cooMaker):
	plainMapper = _makeAreaTreeMapper(intervalType, cooMaker)
	def toCST(node, positions):
		return _combine(plainMapper(node, positions),
			_basicSpatialCoosToCST(node))
	return toCST


# refactor those geometries.  I'm fed up right now and cut'n'paste
def _makeAllSkyCoos(node, positions):
	coos = ()
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

def _makeCircleCoos(node, positions):
	coos = node.center+(node.radius,)
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

def _makeEllipseCoos(node, positions):
	coos = node.center+(node.smajAxis, node.sminAxis, node.posAngle)
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

def _makeBoxCoos(node, positions):
	coos = node.center+node.boxsize
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

def _makePolygonCoos(node, positions):
	coos = tuple(itertools.chain(*node.vertices))
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

def _makeConvexCoos(node, positions):
	coos = tuple(itertools.chain(*node.vectors))
	pos = None
	if positions:
		pos = positions[0]
	return coos, pos

_geometryMappers = dict([(n, _makeGeometryMapper(n,
		globals()["_make%sCoos"%n]))
	for n in ["AllSky", "Circle", "Ellipse", "Box", "Polygon", "Convex"]])

def _spatialToCST(coos, areas):
	node = (areas and areas[0]) or (coos and coos[0])
	if not node:
		return {}
	if isinstance(node, (dm.SpaceCoo, dm.SpaceInterval)):
		return _simpleSpatialToCST(coos, areas)
	else: # Ok, it's a geometry
		return _geometryMappers[areas[0].__class__.__name__](areas[0], coos)


############## Flattening of the CST


def _makeSequenceFlattener(keyword):
	if keyword:
		def flatten(seq):
			if seq:
				return "%s %s"%(keyword, " ".join(str(v) for v in seq))
	else:
		def flatten(seq):
			if seq:
				return " ".join(str(v) for v in seq)
	return flatten


def _makeKeywordFlattener(keyword):
	def flatten(val):
		if val is not None:
			return "%s %s"%(keyword, val)
	return flatten


# Keyword based flattening
_commonFlatteners = {
	"fillfactor": _makeKeywordFlattener("fillfactor"),
	"unit": _makeKeywordFlattener("unit"),
	"error": _makeSequenceFlattener("Error"),
	"resolution": _makeSequenceFlattener("Resolution"),
	"pixSize": _makeSequenceFlattener("PixSize"),
}


def _make1DCooFlattener(stringifyCoo, posKey, frameKeys):
	def posFlattener(val):
		if val is not None:
			return "%s %s"%(posKey, stringifyCoo(val.value))
	flatteners = {"pos": posFlattener}
	flatteners.update(_commonFlatteners)
	keyList = ["type", "fillfactor"]+frameKeys+["coos", "pos", 
		"unit", "error", "resolution", "pixSize"]
	def flatten(node):
		node["coos"] = " ".join(map(stringifyCoo, node.get("coos", ())))
		return _joinKeysWithNull(node, keyList, flatteners)
	return flatten


def _flattenSpacePos(val):
	if val is not None:
		return "Position %s"%" ".join(str(v) for v in _flattenVectors([val.value]))

_posFlatteners = _commonFlatteners.copy()
_posFlatteners["pos"] = _flattenSpacePos
_posFlatteners["size"] = _makeSequenceFlattener("Size")
_posFlatteners["coos"] = _makeSequenceFlattener("")

def _flattenPosition(node):
	for key in ["error", "resolution", "size", "pixSize", "coos"]:
		if key in node and node[key] is not None:
			node[key] = [str(v) for v in _flattenVectors(node[key])]
	return _joinKeysWithNull(node, ["type", "fillfactor", "frame", "equinox",
		"refpos",
		"flavor", "coos", "pos", "unit", "error", "resolution", "size", 
		"pixSize"], _posFlatteners)


_flattenTime = _make1DCooFlattener(lambda v: v.isoformat(), "Time",
	["timescale", "refpos"])
_flattenSpectral = _make1DCooFlattener(str, "Spectral",
	["refpos"])
_flattenRedshift = _make1DCooFlattener(str, "Redshift",
	["refpos", "redshiftType", "dopplerdef"])

def _joinWithNull(strList):
	return " ".join(s for s in strList if s is not None)


def _joinKeysWithNull(node, kwList, flatteners):
	"""returns a string made up of the non-null values in kwList in node.

	To make things a bit more flexible, you can give lists in kwList.
	Their elements will be inserted into the result as-is.
	"""
	res = []
	for key in kwList:
		if isinstance(key, list):
			res.extend(key)
		elif key not in node:
			pass
		elif key in flatteners:
			res.append(flatteners[key](node[key]))
		else:
			res.append(node[key])
	return _joinWithNull(res)


def _flattenCST(cst):
	"""returns a flattened string for an STCS CST.

	Flattening destroys the tree.
	"""
	return "\n".join([s for s in (
			_flattenTime(cst.get("time", {})),
			_flattenPosition(cst.get("space", {})),
			_flattenSpectral(cst.get("spectral", {})),
			_flattenRedshift(cst.get("redshift", {})),)
		if s])


_len1Attrs = ["times", "places", "freqs", "redshifts",
	"timeAs", "areas", "freqAs", "redshiftAs"]

def getSTCS(astRoot):
	"""returns an STC-S string for an AST.
	"""
	for name in _len1Attrs:
		val = getattr(astRoot, name)
		if val is not None and len(val)>1:
			raise STCValueError("STC-S does not support STC specifications of"
				" length>1, but %s has length %d"%(name, len(val)))
	cst = stcs.removeDefaults({
		"time": _timeToCST(astRoot.times, astRoot.timeAs),
		"space": _spatialToCST(astRoot.places, astRoot.areas),
		"spectral": _spectralToCST(astRoot.freqs, astRoot.freqAs),
		"redshift": _redshiftToCST(astRoot.redshifts, astRoot.redshiftAs),
	})
	return _flattenCST(cst)
