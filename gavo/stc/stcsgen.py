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


def _makeCooTreeMapper(cooType, frameMaker):
	"""returns a function returning a CST fragment for a coordinate.
	"""
	def toCST(node):
		nDim = node.frame.nDim
		return _combine({
			"error": _wiggleToCST(node.error, nDim),
			"resolution": _wiggleToCST(node.resolution, nDim),
			"pixSize": _wiggleToCST(node.pixSize, nDim),
			"unit": _makeUnit(node),
			"type": cooType,
			"pos": node.value or None,},
			frameMaker(node.frame))
	return toCST


def _makeIntervalCoos(node):
	if node.lowerLimit and node.upperLimit:
		coos = [c for c in (node.lowerLimit, node.upperLimit) if c is not None]
	return {"coos": coos}


def _makeTimeIntervalCoos(node):
# Special-cased since these have (Start|Stop)Time
	if node.lowerLimit and node.upperLimit:
		type, coos = "TimeInterval", (node.lowerLimit, node.upperLimit)
	elif node.lowerLimit:
		type, coos = "StartTime", (node.lowerLimit,)
	elif node.upperLimit:
		type, coos = "StopTime", (node.upperLimit,)
	else:
		type, coos = "TimeInterval", ()
	return {
		"type": type,
		"coos": coos}


def _makeAreaTreeMapper(areaType, cooMaker=_makeIntervalCoos):
	"""returns a CST fragment for an area.

	areaType this CST type of the node returned, cooMaker is a function
	that receives the node and returns a dictionary containing at least
	a coos key.  It can set other keys as well (e.g. 
	_makeTimeIntervalCoos needs to override the type key).
	"""
	def toCST(node):
		return _combine({
			"type": areaType},
			cooMaker(node))
	return toCST


def _makePhraseTreeMapper(cooMapper, areaMapper,
		getASTItems):
	"""returns a mapper building a CST fragment for a subphrase.

	cooMapper and areaMapper are functions returning CST fragments
	for coordinates and areas of this type, respectively.

	getASTItems is a function that receives the AST root and has to
	return either None (no matching items found in AST) or a pair
	of coordinate and area, where area may be None.  Use _makeASTItemsGetter
	to build these functions.

	The function returned expects the root of the AST as argument.
	"""
	def toCST(astRoot):
		items = getASTItems(astRoot)
		if items is None:
			return {}
		coo, area = items
		areaKeys = {}
		if area:
			areaKeys = areaMapper(area)
		cooKeys = cooMapper(coo)
		return _combine(cooKeys,
			areaKeys,  # area keys come later to override posKey type.
			)
	return toCST


def _makeASTItemsGetter(cooName, areaName, positionClass):
	"""returns a function that extracts coordinates and areas of
	a certain type from an AST.

	The function does all kinds of sanity checks and raises STCValueErrors
	if those fail.

	If all goes well, it will return a pair coo, area.  coo is always
	non-None, area may be None.
	"""
	def getASTItems(astRoot):
		areas, coos = getattr(astRoot, areaName), getattr(astRoot, cooName)
		if not areas and not coos:
			return None
		if len(areas)>1:
			raise STCValueError("STC-S does not support more than one area"
				" but %s has length %d"%(areaName, len(areas)))
		if len(coos)>1:
			raise STCValueError("STC-S does not support more than one coordinate,"
				" but %s has length %d"%(areaName, len(coos)))
		if areas and coos:
			if coos[0].unit is None:
				coos[0].unit = areas[0].unit
			if coos[0].unit!=areas[0].unit:
				raise STCValueError("Cannot serialize ASTs with different"
					" units on positions and areas to STC-S")
		if coos:
			coo = coos[0]
		else:
			coo = positionClass(unit=areas[0].unit)
		if areas:
			area = areas[0]
		else:
			area = None
		return coo, area
	return getASTItems


def _spatialCooToCST(node, getBase=_makeCooTreeMapper("Position",
		_spaceFrameToCST)):
	cstNode = getBase(node)
	cstNode["size"] = _wiggleToCST(node.size, node.frame.nDim)
	return cstNode


_timeToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Time", _timeFrameToCST),
	_makeAreaTreeMapper("TimeInterval", _makeTimeIntervalCoos),
	_makeASTItemsGetter("times", "timeAs", dm.TimeCoo))
_simpleSpatialToCST = _makePhraseTreeMapper(
	_spatialCooToCST,
	_makeAreaTreeMapper("PositionInterval"),
	_makeASTItemsGetter("places", "areas", dm.SpaceCoo))
_spectralToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Spectral", _spectralFrameToCST),
	_makeAreaTreeMapper("SpectralInterval"),
	_makeASTItemsGetter("freqs", "freqAs", dm.SpectralCoo))
_redshiftToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Redshift", _redshiftFrameToCST),
	_makeAreaTreeMapper("RedshiftInterval"),
	_makeASTItemsGetter("redshifts", "redshiftAs", dm.RedshiftCoo))


def _makeAllSkyCoos(node):
	return {"coos": ()}

def _makeCircleCoos(node):
	return {"coos": node.center+(node.radius,)}

def _makeEllipseCoos(node):
	return {"coos": node.center+(node.smajAxis, node.sminAxis, node.posAngle)}

def _makeBoxCoos(node):
	return {"coos": node.center+node.boxsize}

def _makePolygonCoos(node):
	return {"coos": tuple(itertools.chain(*node.vertices))}

def _makeConvexCoos(node):
	return {"coos": tuple(itertools.chain(*node.vectors))}

_geometryMappers = dict([(n, _makePhraseTreeMapper(
		_spatialCooToCST,
		_makeAreaTreeMapper(n, globals()["_make%sCoos"%n]),
		_makeASTItemsGetter("places", "areas", dm.SpaceCoo)))
	for n in ["AllSky", "Circle", "Ellipse", "Box", "Polygon", "Convex"]])

def _spatialToCST(astRoot):
	node = (astRoot.areas and astRoot.areas[0]) or (
		astRoot.places and astRoot.places[0])
	if not node:
		return {}
	if isinstance(node, (dm.SpaceCoo, dm.SpaceInterval)):
		return _simpleSpatialToCST(astRoot)
	else: # Ok, it's a geometry
		return _geometryMappers[node.__class__.__name__](astRoot)


############## Flattening of the CST


def _makeSequenceFlattener(keyword):
	if keyword:
		def flatten(seq, node):
			if seq:
				return "%s %s"%(keyword, " ".join(str(v) for v in seq))
	else:
		def flatten(seq, node):
			if seq:
				return " ".join(str(v) for v in seq)
	return flatten


def _makeKeywordFlattener(keyword):
	def flatten(val, node):
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


def _makePosFlattener(key, stringify):
	def flatten(val, node):
		if val is not None:
			val = stringify(val)
			if node["type"]==key:
				return val
			else:
				return "%s %s"%(key, val)
	return flatten


def _make1DCooFlattener(stringifyCoo, posKey, frameKeys):
	posFlattener = _makePosFlattener(posKey, stringifyCoo)
	flatteners = {"pos": posFlattener}
	flatteners.update(_commonFlatteners)
	keyList = ["type", "fillfactor"]+frameKeys+["coos", "pos", 
		"unit", "error", "resolution", "pixSize"]
	def flatten(node):
		if "coos" in node:
			node["coos"] = " ".join(map(stringifyCoo, node["coos"]))
		return _joinKeysWithNull(node, keyList, flatteners)
	return flatten


_flattenSpacePos = _makePosFlattener("Position",
	lambda val: " ".join(str(v) for v in _flattenVectors([val])))

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
			res.append(flatteners[key](node[key], node))
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
		"time": _timeToCST(astRoot),
		"space": _spatialToCST(astRoot),
		"spectral": _spectralToCST(astRoot),
		"redshift": _redshiftToCST(astRoot),
	})
	return _flattenCST(cst)
