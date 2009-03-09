"""
Transformation of STC-S CSTs to STC ASTs.
"""

from gavo.stc import dm
from gavo.stc import stcs
from gavo.stc.common import *


def buildTree(tree, context, pathFunctions={}, nameFunctions={},
		typeFunctions={}):
	"""traverses tree, calling functions on nodes.

	pathFunctions is a dictionary mapping complete paths (i.e., tuples
	of node labels) to handler functions, nameFunctions name a single
	label and are called for nodes that don't match a pathFunction if
	the last item of their paths is the label.  If none of those
	match, if a node has a type value, it will be checked against
	typeFuncitons.

	The handler functions must be iterators.  If they yield anything,
	it must be key-value pairs.

	All key-value pairs are collected in a dictionary that is then
	returned.  If value is a tuple, it is appended to the current value
	for the key.

	Context is an arbitrary object containing ancillary information for
	building nodes.  What's in there and what's not is up to the functions
	and their callers.
	"""
	resDict = {}
	for path, node in stcs.iterNodes(tree):
		if path in pathFunctions:
			handler = pathFunctions[path]
		elif path and path[-1] in nameFunctions:
			handler = nameFunctions[path[-1]]
		elif node.get("type") in typeFunctions:
			handler = typeFunctions[node["type"]]
		else: # No handler, ignore this node
			continue
		for res in handler(node, context):
			k, v = res
			if isinstance(v, tuple):
				resDict.setdefault(k, []).extend(v)
			else:
				if k in resDict:
					raise STCInternalError("Attempt to overwrite key '%s', old"
						" value %s, new value %s (this should probably have been"
						" a tuple)"%(k, resDict[k], v))
				resDict[k] = v
	return resDict


class GenericContext(object):
	"""is an object that can be used for context.

	It simply exposes all its constructor arguments as attributes.
	"""
	def __init__(self, **kwargs):
		for k, v in kwargs.iteritems():
			setattr(self, k, v)


############## Coordinate systems

def _makeRefpos(refposName):
	return dm.RefPos(standardOrigin=refposName)

def _buildRedshiftFrame(node, context):
	yield "redshiftFrame", dm.RedshiftFrame(dopplerDef=node["dopplerdef"], 
		type=node["redshiftType"], refPos=_makeRefpos(node["refpos"]))

def _buildSpaceFrame(node, context):
	nDim, flavor = stcs.stcsFlavors[node["flavor"]]
	yield "spaceFrame", dm.SpaceFrame(refPos=_makeRefpos(node["refpos"]),
		flavor=flavor, nDim=nDim, refFrame=node["frame"])

def _buildSpectralFrame(node, context):
	yield "spectralFrame", dm.SpectralFrame(refPos=_makeRefpos(node["refpos"]))

def _buildTimeFrame(node, context):
	yield "timeFrame", dm.TimeFrame(refPos=_makeRefpos(node["refpos"]),
		timeScale=node["timescale"])

def getCoordSys(cst):
	"""returns constructor arguments for a CoordSys from an STC-S CST.
	"""
	args = buildTree(cst, None, nameFunctions={
		'redshift': _buildRedshiftFrame,
		'space': _buildSpaceFrame,
		'spectral': _buildSpectralFrame,
		'time': _buildTimeFrame,
	})
	return "system", dm.CoordSys(**args)


############## Coordinates


def iterVectors(values, dim):
	"""iterates over dim-dimensional vectors made of values.

	The function does not check if the last vector is actually complete.
	"""
	if dim==1:
		for v in values:
			yield v
	else:
		for index in range(0, len(values), dim):
			yield tuple(values[index:index+dim])


def iterIntervals(coos, dim):
	"""iterates over pairs dim-dimensional vectors.

	It will always return at least one empty (i.e., None, None) pair.
	The last pair returned may be incomplete (specifying a start
	value only, supposedly) but not empty.
	"""
	first, startValue = True, None
	for item in iterVectors(coos, dim):
		if startValue is None:
			if first:
				first = False
			startValue = item
		else:
			yield (startValue, item)
			startValue = None
	if startValue is None:
		if first:
			yield (None, None)
	else:
		yield (startValue, None)


def _makeBasicCooArgs(node, frame):
	"""returns a dictionary containing constructor arguments common to
	all items dealing with coordinates.
	"""
	nDim = getattr(frame, "nDim", 1)
	return {
		"error": _makeCooValues(nDim, node.get("error"), 
			cooParse=float, maxItems=2),
		"resolution": _makeCooValues(nDim, node.get("resolution"), 
			cooParse=float, maxItems=2),
		"size": _makeCooValues(nDim, node.get("size"), cooParse=float,
			maxItems=2),
		"pixSize": _makeCooValues(nDim, node.get("pixSize"), cooParse=float,
			maxItems=2),
		"units": node.get("unit"),
		"frame": frame,
	}


def _validateCoos(values, nDim, minItems, maxItems):
	"""makes sure values is valid a source of between minItems and maxItems
	nDim-dimensional tuples.

	minItems and maxItems may both be None so signify no limit.
	"""
	numItems = len(values)/nDim
	if numItems*nDim!=len(values):
		raise STCSParseError("%s is not valid input to create %d-dimensional"
			" coordinates"%(values, nDim))
	if minItems is not None and numItems<minItems:
		raise STCSParseError("Expected at least %d coordinates in %s."%(
			minItems, values))
	if maxItems is not None and numItems>maxItems:
		raise STCSParseError("Expected not more than %d coordinates in %s."%(
			maxItems, values))


def _makeCooValues(nDim, values, cooParse=float, minItems=None, maxItems=None):
	"""returns a list of nDim-Tuples made up of values.

	If values does not contain an integral multiple of nDim items,
	the function will raise an STCSParseError.  You can also optionally
	give a minimally or maximally expected number of tuples.  If the 
	constraints are violated, again an STCSParseError is raised.
	"""
	if values is None:
		if minItems:
			raise STCSParseError("Expected at least %s coordinate items but"
				" found none."%minItems)
		else:
			return
	_validateCoos(values, nDim, minItems, maxItems)
	return tuple(v for v in iterVectors(map(cooParse, values), nDim))


def _makeCooBuilder(frameName, realBuilder):
	def builder(node, context):
		frame = getattr(context.system, frameName)
		args = _makeBasicCooArgs(node, frame)
		return realBuilder(node, context, args, node.get("coos", []),
			frame.nDim)
	return builder


def _makeCooRealBuilder(resKey, argKey, cooClass, cooParse=float):
	def realBuilder(node, context, args, coos, nDim):
		args[argKey] = _makeCooValues(nDim, coos, cooParse=cooParse, 
			maxItems=1)[0]
		yield resKey, (cooClass(**args),)
	return realBuilder


def _makeIntervalRealBuilder(resKey, posResKey, 
		intervalClass, posClass, cooParse=float):
	def realBuilder(node, context, args, coos, nDim):
		coos = map(cooParse, coos)
		_validateCoos(coos, nDim, None, None)
		if "pos" in node:
			args["value"] = _makeCooValues(nDim, node["pos"], cooParse=cooParse,
				minItems=1, maxItems=1)[0]
			yield posResKey, (posClass(**args),)
			del args["value"]
		for interval in iterIntervals(coos, nDim):
			args["lowerLimit"], args["upperLimit"] = interval
			yield resKey, (intervalClass(**args),)
	return realBuilder


def _id(x):
	return x


def getCoords(cst, system):
	"""returns an argument dict for constructing STCSpecs for plain coordinates.
	"""
	context = GenericContext(system=system)

	return buildTree(cst, context, typeFunctions = {
		"Time": _makeCooBuilder("timeFrame", 
			_makeCooRealBuilder("times", "value", dm.TimeCoo, cooParse=_id)),
		"StartTime": _makeCooBuilder("timeFrame", 
			_makeCooRealBuilder("timeAs", "lowerLimit", dm.TimeCoo, cooParse=_id)),
		"StopTime": _makeCooBuilder("timeFrame", 
			_makeCooRealBuilder("timeAs", "upperLimit", dm.TimeCoo, cooParse=_id)),
		"TimeInterval": _makeCooBuilder("timeFrame",
			_makeIntervalRealBuilder("timeAs", "times",
				dm.TimeInterval, dm.TimeCoo, cooParse=lambda x: x)),

		"Position": _makeCooBuilder("spaceFrame",
			_makeCooRealBuilder("places", "value", dm.SpaceCoo)),
		"PositionInterval": _makeCooBuilder("spaceFrame",
			_makeIntervalRealBuilder("areas", "places",
				dm.SpaceInterval, dm.SpaceCoo)),

		"Spectral": _makeCooBuilder("spectralFrame",
			_makeCooRealBuilder("freqs", "value", dm.SpectralCoo)),
		"SpectralInterval": _makeCooBuilder("spectralFrame",
			_makeIntervalRealBuilder("freqAs", "freqs",
				dm.SpectralInterval, dm.SpectralCoo)),

		"Redshift": _makeCooBuilder("redshiftFrame",
			_makeCooRealBuilder("redshifts", "value", dm.RedshiftCoo)),
		"RedshiftInterval": _makeCooBuilder("redshiftFrame",
			_makeIntervalRealBuilder("redshiftAs", "redshifts",
				dm.RedshiftInterval, dm.RedshiftCoo)),

	})


def parseSTCS(literal):
	"""returns an STC AST for an STC-S expression.
	"""
	cst = stcs.getCST(literal)
	system = getCoordSys(cst)[1]
	args = {"systems": (system,)}
	args.update(getCoords(cst, system))
	return dm.STCSpec(**args)
