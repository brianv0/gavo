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
	equinox = None
	if node.get("equinox"):
		if "." in node["equinox"]: 
			equinox = node["equinox"]
		else: # allow J2000 and expand it to J2000.0
			equinox = node["equinox"]+".0"
	yield "spaceFrame", dm.SpaceFrame(refPos=_makeRefpos(node["refpos"]),
		flavor=flavor, nDim=nDim, refFrame=node["frame"], equinox=equinox)

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


############## Coordinates and their intervals


def iterVectors(values, dim, spatial):
	"""iterates over dim-dimensional vectors made of values.

	The function does not check if the last vector is actually complete.
	"""
	if dim==1 and not spatial:
		for v in values:
			yield v
	else:
		for index in range(0, len(values), dim):
			yield tuple(values[index:index+dim])


def _iterIntervals(coos, dim, spatial=False):
	"""iterates over pairs dim-dimensional vectors.

	It will always return at least one empty (i.e., None, None) pair.
	The last pair returned may be incomplete (specifying a start
	value only, supposedly) but not empty.
	"""
	first, startValue = True, None
	for item in iterVectors(coos, dim, spatial):
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


def _makeWiggleValues(nDim, val, minItems=None, maxItems=None, spatial=False):
	if val is None: 
		return
	values = _makeCooValues(nDim, val, minItems, maxItems, spatial)
	if not values:
		return
	if nDim>1:  # might be error radii if all values are equal
		if set([1])==set(len(set(v)) for v in values):
			return dm.RadiusWiggle(radii=[v[0] for v in values])
	return dm.CooWiggle(values=values)


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


def _makeCooValues(nDim, values, minItems=None, maxItems=None, spatial=False):
	"""returns a list of nDim-Tuples made up of values.

	If values does not contain an integral multiple of nDim items,
	the function will raise an STCSParseError.  You can also optionally
	give a minimally or maximally expected number of tuples.  If the 
	constraints are violated, again an STCSParseError is raised.

	If spatial is true, tuples will be returned even for 1D data.
	"""
	if values is None:
		if minItems:
			raise STCSParseError("Expected at least %s coordinate items but"
				" found none."%minItems)
		else:
			return
	_validateCoos(values, nDim, minItems, maxItems)
	return tuple(v for v in iterVectors(values, nDim, spatial))


def _addUnitPlain(args, node, frame):
	args["unit"] = node.get("unit")


def _addUnitRedshift(args, node, frame):
	unit = node.get("unit")
	if unit:
		parts = unit.split("/")
		if len(parts)!=2:
			raise STCSParseError("'%s' is not a valid unit for redshifts"%unit)
		args["unit"] = parts[0]
		args["velTimeUnit"] = parts[1]


def _addUnitSpatial(args, node, frame):
	unit, nDim = node.get("unit"), frame.nDim
	if unit:
		parts = unit.split()
		if len(parts)==frame.nDim:
			args["units"] = tuple(parts)
		elif len(parts)==1:
			args["units"] = (unit,)*nDim
		else:
			raise STCSParseError("'%s' is not a valid for unit %d-dimensional"
				" spatial coordinates"%(unit, nDim))


def _addUnitVelocity(args, node, frame):
	unit, nDim = node.get("unit"), frame.nDim
	if unit:
		parts = unit.split()
		if len(parts)!=1:
			raise STCSNotImplementedError("Inhomogeneous units not yet supported")
		parts = parts[0].split("/")
		if len(parts)!=2:
			raise STCSParseError("'%s' is not a valid unit for velocities."%unit)
		args["units"] = (parts[0],)*nDim
		args["velTimeUnits"] = (parts[1],)*nDim


_unitMakers = {
	dm.SpectralType: _addUnitPlain,
	dm.TimeType: _addUnitPlain,
	dm.SpaceType: _addUnitSpatial,
	dm.RedshiftType: _addUnitRedshift,
	dm.VelocityType: _addUnitVelocity,
}


def _makeBasicCooArgs(node, frame, posClass, spatial=False):
	"""returns a dictionary containing constructor arguments common to
	all items dealing with coordinates.
	"""
	nDim = frame.nDim
	args = {
		"error": _makeWiggleValues(nDim, node.get("error"), maxItems=2,
			spatial=spatial),
		"resolution": _makeWiggleValues(nDim, node.get("resolution"), maxItems=2,
			spatial=spatial),
		"pixSize": _makeWiggleValues(nDim, node.get("pixSize"), maxItems=2,
			spatial=spatial),
		"size": _makeWiggleValues(nDim, node.get("size"), maxItems=2,
			spatial=spatial),
		"frame": frame,
	}
	_unitMakers[posClass.cType](args, node, frame)
	return args


def _makeCooBuilder(frameName, intervalClass, intervalKey,
		posClass, posKey, iterIntervKeys, spatial=False):
	"""returns a function(node, context) -> ASTNode for building a
	coordinate-like AST node.

	frameName is the name of the coordinate frame within
	context.system,

	(interval|pos)(Class|Key) are the class (key) to be used
	(returned) for the interval/geometry and simple coordinate found
	in the phrase.	If intervalClass is None, no interval/geometry
	will be built.

	iterIntervKeys is an iterator that yields key/value pairs for intervals
	or geometries embedded.

	Single positions are always expected under the coo key.
	"""
	positionExclusiveKeys = ["error", "resolution", "pixSize", "value",
		"size"]
	def builder(node, context):
		frame = getattr(context.system, frameName)
		nDim = frame.nDim
		args = _makeBasicCooArgs(node, frame, posClass, spatial)

		# Yield a coordinate
		if "pos" in node:
			args["value"] = _makeCooValues(nDim, node["pos"],
				minItems=1, maxItems=1, spatial=spatial)[0]
		else:
			args["value"] = None
		yield posKey, posClass(**args)

		# Yield an area if defined in this phrase and non-empty
		if intervalClass is None:
			return
		for key in positionExclusiveKeys:
			if key in args:
				del args[key]
		for k, v in iterIntervKeys(node, nDim, spatial=spatial):
			args[k] = v
		if "fillfactor" in node:
			args["fillFactor"] = node["fillfactor"]

		yield intervalKey, (intervalClass(**args),)

	return builder


def _makeIntervalKeyIterator(preferUpper=False):
	"""returns a function yielding ASTNode constructor keys for intervals.
	"""
	def iterKeys(node, nDim, spatial=False):
		res, coos = {}, node.get("coos", ())
		_validateCoos(coos, nDim, None, None)
		for interval in _iterIntervals(coos, nDim, spatial):
			if preferUpper:
				res["upperLimit"], res["lowerLimit"] = interval
			else:
				res["lowerLimit"], res["upperLimit"] = interval
		return res.iteritems()
	return iterKeys



###################### Geometries


def _makeGeometryKeyIterator(argDesc, clsName):
	"""returns a key iterator for use with _makeCooBuilder that yields
	the keys particular to certain geometries.

	ArgDesc describes what keys should be parsed from the node's coos key.  
	It consists for tuples of name and type code, where type code is one of:

	* r -- a single real value.
	* v -- a vector of dimensionality given by the system (i.e., nDim).
	* rv -- a sequence of v items of arbitrary length.
	* cv -- a sequence of "Convex" vectors (dim 4) of arbitrary length.

	rv may only occur at the end of argDesc since it will consume all
	remaining coordinates.
	"""
	parseLines = [
		"def iterKeys(node, nDim, spatial=True):",
		'  coos = node.get("coos", ())',
		'  if False: yield',  # ensure the thing is an iterator
		"  try:",
		"    pass"]
	for name, code in argDesc:
		if code=="r":
			parseLines.append('    yield "%s", coos.pop(0)'%name)
		elif code=="v":
			parseLines.append('    vec = coos[:nDim]')
			parseLines.append('    coos = coos[nDim:]')
			parseLines.append('    _validateCoos(vec, nDim, 1, 1)')
			parseLines.append('    yield "%s", tuple(vec)'%name)
		elif code=="rv":
			parseLines.append('    yield "%s", _makeCooValues(nDim, coos)'%name)
			parseLines.append('    coos = []')
		elif code=="cv":
			parseLines.append('    yield "%s", _makeCooValues(4, coos)'%name)
			parseLines.append('    coos = []')
	parseLines.append('  except IndexError:')
	parseLines.append('    raise STCSParseError("Not enough coordinates'
		' while parsing %s")'%clsName)
	parseLines.append('  if coos: raise STCSParseError("Too many coordinates'
		' while building %s, remaining: %%s"%%coos)'%clsName)
	exec "\n".join(parseLines)
	return iterKeys


def _makeGeometryBuilder(cls, argDesc):
	"""returns a builder for Geometries.

	See _makeGeometryRealBulder for the meaning of the arguments.
	"""
	return _makeCooBuilder("spaceFrame", cls, "areas", dm.SpaceCoo,
		"place", _makeGeometryKeyIterator(argDesc, cls.__name__))


###################### Top level


def getCoords(cst, system):
	"""returns an argument dict for constructing STCSpecs for plain coordinates.
	"""
	context = GenericContext(system=system)

	return buildTree(cst, context, typeFunctions = {
		"Time": _makeCooBuilder("timeFrame", None, None,
			dm.TimeCoo, "time", None),
		"StartTime": _makeCooBuilder("timeFrame", dm.TimeInterval, "timeAs",
			dm.TimeCoo, "time", _makeIntervalKeyIterator()),
		"StopTime": _makeCooBuilder("timeFrame", dm.TimeInterval, "timeAs",
			dm.TimeCoo, "time", _makeIntervalKeyIterator(preferUpper=True)),
		"TimeInterval": _makeCooBuilder("timeFrame", dm.TimeInterval, "timeAs",
			dm.TimeCoo, "time", _makeIntervalKeyIterator()),

		"Position": _makeCooBuilder("spaceFrame", None, None, dm.SpaceCoo,
			"place", None, spatial=True),
		"PositionInterval": _makeCooBuilder("spaceFrame",
			dm.SpaceInterval, "areas", dm.SpaceCoo, "place",
			_makeIntervalKeyIterator(), spatial=True),
		"VelocityInterval": _makeCooBuilder("spaceFrame",
			dm.VelocityInterval, "velocityAs", dm.VelocityCoo, "velocity",
			_makeIntervalKeyIterator(), spatial=True),
		"AllSky": _makeGeometryBuilder(dm.AllSky, []),
		"Circle": _makeGeometryBuilder(dm.Circle, 
			[('center', 'v'), ('radius', 'r')]),
		"Ellipse": _makeGeometryBuilder(dm.Ellipse, 
				[('center', 'v'), ('smajAxis', 'r'), ('sminAxis', 'r'), 
					('posAngle', 'r')]),
		"Box": _makeGeometryBuilder(dm.Box, [('center', 'v'), ('boxsize', 'v')]),
		"Polygon": _makeGeometryBuilder(dm.Polygon, [("vertices", "rv")]),
		"Convex": _makeGeometryBuilder(dm.Convex, [("vectors", "cv")]),

		"Spectral": _makeCooBuilder("spectralFrame", None, None,
			dm.SpectralCoo, "freq", None),
		"SpectralInterval": _makeCooBuilder("spectralFrame", 
			dm.SpectralInterval, "freqAs", dm.SpectralCoo, "freq",
			_makeIntervalKeyIterator()),

		"Redshift": _makeCooBuilder("redshiftFrame", None, None,
			dm.RedshiftCoo, "redshift", None),
		"RedshiftInterval": _makeCooBuilder("redshiftFrame", 
			dm.RedshiftInterval, "redshiftAs", dm.RedshiftCoo, "redshift",
			_makeIntervalKeyIterator()),

	})


def parseSTCS(literal):
	"""returns an STC AST for an STC-S expression.
	"""
	cst = stcs.getCST(literal)
	system = getCoordSys(cst)[1]
	args = {"astroSystem": system}
	args.update(getCoords(cst, system))
	return dm.STCSpec(**args)


if __name__=="__main__":
	print parseSTCS("PositionInterval ICRS 1 2 3 4")
