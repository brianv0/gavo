"""
Transformation of STC-S CSTs to STC ASTs.
"""

from gavo.stc import coordsys
from gavo.stc import stcs


def buildTree(tree, context, pathFunctions={}, nameFunctions={}):
	for path, node in stcs.iterNodes(tree):
		if path in pathFunctions:
			res = pathFunctions[path](node, context)
		elif path and path[-1] in nameFunctions:
			res = nameFunctions[path[-1]](node, context)

def _makeRefpos(refposName):
	return coordsys.RefPos(standardOrigin=refposName)

def _buildRedshiftFrame(node, cs):
	cs.redshiftFrame = coordsys.RedshiftFrame(dopplerDef=node["dopplerdef"], 
		refPos=_makeRefpos(node["refpos"]))

def _buildSpaceFrame(node, cs):
	nDim, flavor = stcs.stcsFlavors[node["flavor"]]
	cs.spaceFrame = coordsys.SpaceFrame(refPos=_makeRefpos(node["refpos"]),
		flavor=flavor, nDim=nDim, refFrame=node["frame"])

def _buildSpectralFrame(node, cs):
	cs.spectralFrame = coordsys.SpectralFrame(refPos=_makeRefpos(node["refpos"]))

def _buildTimeFrame(node, cs):
	cs.timeFrame = coordsys.TimeFrame(refPos=_makeRefpos(node["refpos"]),
		timeScale=node["timescale"])

def getCoordSys(cst):
	"""returns constructor arguments for a CoordSys from an STC-S CST.
	"""
	system = coordsys.CoordSys()
	buildTree(cst, system, nameFunctions={
		'redshift': _buildRedshiftFrame,
		'space': _buildSpaceFrame,
		'spectral': _buildSpectralFrame,
		'time': _buildTimeFrame,
	})
	return system


def parseSTCS(literal):
	"""returns an STC AST for an STC-S expression.
	"""
	cst = stcs.getCST(literal)
	system = getCoordSys(cst)
