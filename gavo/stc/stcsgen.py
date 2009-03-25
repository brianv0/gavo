"""
Converting ASTs to STC-S.

The strategy here is to first generate an STCS CST, remove defaults from it
and then flatten out the whole thing.

The AST serializers here either return a dictionary, which is then
updated to the current node's dictionary, or a tuple of key and value,
which is then added to the current dictionary.
"""

import itertools
import pprint

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

def _wiggleToCST(node, nDim):
	if node is None:
		return
	if isinstance(node, dm.CooWiggle):
		return node.values
	elif isinstance(node, dm.RadiusWiggle):
		return tuple(itertools.chain(*[(r,)*nDim for r in node.radii]))
	else:
		raise STCValueError("Cannot serialize %s wiggles into STC-S"%
			node.__class__.__name__)


def _makeCooTreeMapper(cooType):
	"""returns a function returning a CST fragment for a coordinate.
	"""
	def toCST(node):
		if node.frame is None:  # no frame, no coordinates.
			return {}
		nDim = node.frame.nDim
		return {
			"error": _wiggleToCST(node.error, nDim),
			"resolution": _wiggleToCST(node.resolution, nDim),
			"pixSize": _wiggleToCST(node.pixSize, nDim),
			"unit": node.getUnit(),
			"type": cooType,
			"pos": node.value or None,}
	return toCST


def _makeIntervalCoos(node):
	res = {}
	if node.lowerLimit or node.upperLimit:
		res["coos"] = [c for c in (node.lowerLimit, node.upperLimit) 
			if c is not None]
	return res


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
			"unit": node.getUnit(),
			"fillfactor": node.fillFactor,
			"type": areaType},
			cooMaker(node))
	return toCST


def _makePhraseTreeMapper(cooMapper, areaMapper, frameMapper,
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
		frame = coo.frame or area.frame
		return _combine(cooKeys,
			areaKeys,  # area keys come later to override cst key "type".
			frameMapper(frame))
	return toCST


def _makeASTItemsGetter(cooName, areaName):
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
			if (areas[0].getUnit() is not None and 
					coos[0].getUnit()!=areas[0].getUnit()):
				raise STCValueError("Cannot serialize ASTs with different"
					" units on positions and areas to STC-S")
		if coos:
			coo = coos[0]
		else:
			coo = areas[0].getPosition()
		if areas:
			area = areas[0]
		else:
			area = None
		return coo, area
	return getASTItems


def _spatialCooToCST(node, getBase=_makeCooTreeMapper("Position")):
	if node.frame is None:
		return {}
	cstNode = getBase(node)
	cstNode["size"] = _wiggleToCST(node.size, node.frame.nDim)
	return cstNode


_timeToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Time"), 
	_makeAreaTreeMapper("TimeInterval", _makeTimeIntervalCoos),
	_timeFrameToCST,
	_makeASTItemsGetter("times", "timeAs"))
_simpleSpatialToCST = _makePhraseTreeMapper(
	_spatialCooToCST,
	_makeAreaTreeMapper("PositionInterval"),
	_spaceFrameToCST,
	_makeASTItemsGetter("places", "areas"))
_spectralToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Spectral"),
	_makeAreaTreeMapper("SpectralInterval"),
	_spectralFrameToCST,
	_makeASTItemsGetter("freqs", "freqAs"))
_redshiftToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("Redshift"),
	_makeAreaTreeMapper("RedshiftInterval"),
	_redshiftFrameToCST,
	_makeASTItemsGetter("redshifts", "redshiftAs"))
_velocityToCST = _makePhraseTreeMapper(
	_makeCooTreeMapper("VelocityInterval"),
	_makeAreaTreeMapper("VelocityInterval"),
	lambda _: {},  # Frame provided by embedding position
	_makeASTItemsGetter("velocities", "velocityAs"))


def _makeAllSkyCoos(node):
	return {"geoCoos": ()}

def _makeCircleCoos(node):
	return {"geoCoos": node.center+(node.radius,)}

def _makeEllipseCoos(node):
	return {"geoCoos": node.center+(node.smajAxis, node.sminAxis, node.posAngle)}

def _makeBoxCoos(node):
	return {"geoCoos": node.center+node.boxsize}

def _makePolygonCoos(node):
	return {"geoCoos": tuple(itertools.chain(*node.vertices))}

def _makeConvexCoos(node):
	return {"geoCoos": tuple(itertools.chain(*node.vectors))}

_geometryMappers = dict([(n, _makePhraseTreeMapper(
		_spatialCooToCST,
		_makeAreaTreeMapper(n, globals()["_make%sCoos"%n]),
		_spaceFrameToCST,
		_makeASTItemsGetter("places", "areas")))
	for n in ["AllSky", "Circle", "Ellipse", "Box", "Polygon", "Convex"]])

def _spatialToCST(astRoot):
	args = {}
	velocityArgs = _velocityToCST(astRoot)
	if velocityArgs:
		args = {"velocity": velocityArgs}
	node = (astRoot.areas and astRoot.areas[0]) or (
		astRoot.places and astRoot.places[0])
	if not node:
		if args:  # provide frame if no position is given
			args.update(_spaceFrameToCST(astRoot.astroSystem.spaceFrame))
			args["type"] = "Position"
	elif isinstance(node, (dm.SpaceCoo, dm.SpaceInterval)):
		args.update(_simpleSpatialToCST(astRoot))
	else: # Ok, it's a geometry
		args.update(_geometryMappers[node.__class__.__name__](astRoot))
	return args


############## Flattening of the CST


def _makeSequenceFlattener(keyword, valSerializer=str):
	if keyword: 
		fmt = "%s %%s"%keyword
	else:
		fmt = "%s"
	def flatten(seq, node):
		if seq:
			return fmt%(" ".join(valSerializer(v) for v in seq))
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

def _serializeVector(v):
	return " ".join(str(c) for c in v)


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
	flatteners = {"pos": _makePosFlattener(posKey, stringifyCoo),
		"coos": _makeSequenceFlattener("", stringifyCoo)}
	flatteners.update(_commonFlatteners)
	keyList = ["type", "fillfactor"]+frameKeys+["coos", "pos", 
		"unit", "error", "resolution", "pixSize"]
	def flatten(node):
		return _joinKeysWithNull(node, keyList, flatteners)
	return flatten


_vectorFlatteners = _commonFlatteners.copy()
_vectorFlatteners.update({
	"coos": _makeSequenceFlattener("", _serializeVector),
	"error": _makeSequenceFlattener("Error", _serializeVector),
	"size": _makeSequenceFlattener("Size", _serializeVector),
	"resolution": _makeSequenceFlattener("Resolution", _serializeVector),
	"pixSize": _makeSequenceFlattener("PixSize", _serializeVector),
})

_velFlatteners = {
	"pos": _makePosFlattener("Velocity", _serializeVector),
}
_velFlatteners.update(_vectorFlatteners)


def _flattenVelocity(val, node):
	if val:
		return "VelocityInterval "+_joinKeysWithNull(val, ["fillfactor",
		"coos", "pos", "unit", "error", "resolution", "size", 
		"pixSize"], _velFlatteners)
	return ""


_posFlatteners = {
	"pos": _makePosFlattener("Position", _serializeVector),
	"geoCoos": _makeSequenceFlattener(""),
	"velocity": _flattenVelocity,
}
_posFlatteners.update(_vectorFlatteners)


def _flattenPosition(node):
	return _joinKeysWithNull(node, ["type", "fillfactor", "frame", "equinox",
		"refpos", "flavor", "coos", "geoCoos", "pos", "unit", "error", 
		"resolution", "size", "pixSize", "velocity"], _posFlatteners)


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


def getSTCS(astRoot):
	"""returns an STC-S string for an AST.
	"""
	cst = stcs.removeDefaults({
		"time": _timeToCST(astRoot),
		"space": _spatialToCST(astRoot),
		"spectral": _spectralToCST(astRoot),
		"redshift": _redshiftToCST(astRoot),
	})
	return _flattenCST(cst)
