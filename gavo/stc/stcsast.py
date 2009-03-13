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
	args = {
		"error": _makeCooValues(nDim, node.get("error"), 
			cooParse=float, maxItems=2),
		"resolution": _makeCooValues(nDim, node.get("resolution"), 
			cooParse=float, maxItems=2),
		"pixSize": _makeCooValues(nDim, node.get("pixSize"), cooParse=float,
			maxItems=2),
		"unit": node.get("unit"),
		"frame": frame,
	}
	# Frame-dependent hack handling -- what a pain...
	if isinstance(frame, dm.SpaceFrame):
		args["size"] =_makeCooValues(nDim, node.get("size"), cooParse=float,
			maxItems=2)
	if isinstance(frame, dm.RedshiftFrame):
		if args["unit"]:
			parts = args["unit"].split("/")
			if len(parts)!=2:
				raise STCSParseError("%s is not a valid unit for redshifts")
			args["unit"] = parts[0]
			args["velTimeUnit"] = parts[1]
	return args


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
	"""returns a function(node, context) -> ASTNode for building a 
	coordinate-like AST node.

	frameName is the name of the coordinate frame within context.system,
	realBuilder a function(node, context, args, coordinates, nDim)
	that actually builds the node, based on the partial constructor
	arguments args and a list of unparsed coordinates.

	Typically, the realBuilder is generated from a factory function as
	well.  See, e.g., _makeCooRealBuilder or _makeGeometryRealBuilder.
	"""
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
		if "fillfactor" in node:
			args["fillFactor"] = float(node["fillfactor"])
		for interval in iterIntervals(coos, nDim):
			args["lowerLimit"], args["upperLimit"] = interval
			yield resKey, (intervalClass(**args),)
	return realBuilder


###################### Geometries


def _makeGeometryRealBuilder(clsName, argDesc):
	"""returns a realBuilder for use with _makeCooBuilder that returns
	a clsName instance built using argDesc.

	clsName is a name of a class resolvable within this module's global
	namespace.  We passing the name rather than the class to work around 
	trouble with closures and exec.

	ArgDesc describes what constructor arguments should be parsed from
	the coordinates.  It consists for tuples of name and type code, where
	type code is one of:

	* r -- a single real value.
	* v -- a vector of dimensionality given by the system (i.e., nDim).
	* rv -- a sequence of v items of arbitrary length.
	* cv -- a sequence of "Convex" vectors (dim 4) of arbitrary length.

	rv may only occur at the end of argDesc since it will consume all
	remaining coordinates.
	"""
	parseLines = [
		"def realBuilder(node, context, args, coos, nDim):",
		"  try:",
		"    pass"]
	for name, code in argDesc:
		if code=="r":
			parseLines.append('    args["%s"] = float(coos.pop(0))'%name)
		elif code=="v":
			parseLines.append('    vec = coos[:nDim]')
			parseLines.append('    coos = coos[nDim:]')
			parseLines.append('    _validateCoos(vec, nDim, 1, 1)')
			parseLines.append('    args["%s"] = tuple(map(float, vec))'%name)
		elif code=="rv":
			parseLines.append('    args["%s"] = _makeCooValues(nDim, coos)'%name)
			parseLines.append('    coos = []')
		elif code=="cv":
			parseLines.append('    args["%s"] = _makeCooValues(4, coos)'%name)
			parseLines.append('    coos = []')
	parseLines.append('  except IndexError:')
	parseLines.append('    raise STCSParseError("Not enough coordinates'
		' while parsing %s")'%clsName)
	parseLines.append('  if coos: raise STCSParseError("Too many coordinates'
		' while building %s, remaining: %%s"%%coos)'%clsName)
	parseLines.append('  if "fillfactor" in node:')
	parseLines.append('    args["fillFactor"] = float(node["fillfactor"])')
	parseLines.append('  yield "areas", (%s(**args),)'%clsName)
	exec "\n".join(parseLines)
	return realBuilder


def _makeGeometryBuilder(clsName, argDesc):
	"""returns a builder for Geometries.

	See _makeGeometryRealBulder for the meaning of the arguments.
	"""
	return _makeCooBuilder("spaceFrame",
		_makeGeometryRealBuilder(clsName, argDesc))


###################### Top level

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
		"AllSky": _makeGeometryBuilder("dm.AllSky", []),
		"Circle": _makeGeometryBuilder("dm.Circle", 
				[('center', 'v'), ('radius', 'r')]),
		"Ellipse": _makeGeometryBuilder("dm.Ellipse", 
				[('center', 'v'), ('smajAxis', 'r'), ('sminAxis', 'r'), 
					('posAngle', 'r')]),
		"Box": _makeGeometryBuilder("dm.Box", 
				[('center', 'v'), ('boxsize', 'v')]),
		"Polygon": _makeGeometryBuilder("dm.Polygon",
			[("vertices", "rv")]),
		"Convex": _makeGeometryBuilder("dm.Convex",
			[("vectors", "cv")]),

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


if __name__=="__main__":
	print parseSTCS("Box fillfactor 0.1 ICRS 70 190 23 18").areas[0].fillFactor
