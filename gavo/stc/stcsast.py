"""
Transformation of STC-S CSTs to STC ASTs.
"""

from gavo.stc import dm
from gavo.stc import stcs
from gavo.stc.common import *


def buildTree(tree, context, pathFunctions={}, nameFunctions={}):
	"""traverses tree, calling functions on nodes.

	pathFunctions is a dictionary mapping complete paths (i.e., tuples
	of node labels) to handler functions, nameFunctions name a single
	label and are called for nodes that don't match a pathFunction if
	the last item of their paths is the label.

	The handler functions must return None or a key-value pair.
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
			res = pathFunctions[path](node, context)
		elif path and path[-1] in nameFunctions:
			res = nameFunctions[path[-1]](node, context)
		else: # No handler, ignore this node
			continue
		if res is not None:
			k, v = res
			if isinstance(v, ()):
				resDict.setdefault(k, []).extend(v)
			else:
				assert k not in resDict
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
	return "redshiftFrame", dm.RedshiftFrame(dopplerDef=node["dopplerdef"], 
		refPos=_makeRefpos(node["refpos"]))

def _buildSpaceFrame(node, context):
	nDim, flavor = stcs.stcsFlavors[node["flavor"]]
	return "spaceFrame", dm.SpaceFrame(refPos=_makeRefpos(node["refpos"]),
		flavor=flavor, nDim=nDim, refFrame=node["frame"])

def _buildSpectralFrame(node, context):
	return "spectralFrame", dm.SpectralFrame(refPos=_makeRefpos(node["refpos"]))

def _buildTimeFrame(node, context):
	return "timeFrame", dm.TimeFrame(refPos=_makeRefpos(node["refpos"]),
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
	return tuple(v for v in iterVectors(map(cooParse, values), nDim))


def _makeCoo(cooClass, node, coos, nDim, **moreAttrs):
	"""returns coordinate of cooClass from the contents of node, with
	additional attributes from moreAttrs.
	"""
	def id(val):
		return val
	args = {
		"error": _makeCooValues(nDim, node.get("error"), cooParse=float, maxItems=2),
		"value": _makeCooValues(nDim, coos, cooParse=id, maxItems=1)[0],
		"resolution": _makeCooValues(nDim, node.get("resolution"), cooParse=float,
			maxItems=2),
		"size": _makeCooValues(nDim, node.get("size"), cooParse=float,
			maxItems=2),
		"pixSize": _makeCooValues(nDim, node.get("pixSize"), cooParse=float,
			maxItems=2),
		"units": node.get("unit"),
	}
	args.update(moreAttrs)
	return cooClass(**args),

def _buildTimeCoo(node, context):
	if node["type"]!="Time":
		return
	return "times", _makeCoo(dm.TimeCoo, node, node.get("coos"),
		1, frame=context.system.timeFrame)

def _buildSpaceCoo(node, context):
	if node["type"]!="Position":
		return
	return "places", _makeCoo(dm.SpaceCoo, node, map(float, node.get("coos", [])),
		context.system.spaceFrame.nDim, frame=context.system.spaceFrame)

def _buildSpectralCoo(node, context):
	if node["type"]!="Spectral":
		return
	return "freqs", _makeCoo(dm.SpectralCoo, node, 
		map(float, node.get("coos", [])), 1, frame=context.system.spectralFrame)

def _buildRedshiftCoo(node, context):
	if node["type"]!="Redshift":
		return
	return "redshifts", _makeCoo(dm.RedshiftCoo, node, 
		map(float, node.get("coos", [])), 1, frame=context.system.redshiftFrame)


def getCoords(cst, system):
	"""returns a tuple of the coordinates found in cst for inclusion in
	an AST.
	"""
	context = GenericContext(system=system)
	return buildTree(cst, context, nameFunctions={
		"time": _buildTimeCoo,
		"space": _buildSpaceCoo,
		"spectral": _buildSpectralCoo,
		"redshift": _buildRedshiftCoo,
	})


def parseSTCS(literal):
	"""returns an STC AST for an STC-S expression.
	"""
	cst = stcs.getCST(literal)
	system = getCoordSys(cst)[1]
	args = {"systems": (system,)}
	args.update(getCoords(cst, system))
	return dm.STCSpec(**args)
