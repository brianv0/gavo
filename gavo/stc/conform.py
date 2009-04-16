"""
"Conforming" of STCSpecs, i.e., bringing one to the system and units of the
other.

You can only conform STCSpecs rather than individual components, since 
usually you need the whole information for the transformation (e.g.,
space and time for velocities.
"""

from gavo import utils

def getUnitConverter(baseCoo, srcCoo):
	if baseCoo is None or baseCoo.getUnitArgs() is None:
		return srcCoo.getUnitArgs(), utils.identity
	if srcCoo.getUnitArgs() is None:
		return baseCoo.getUnitArgs(), utils.identity
	return baseCoo.getUnitArgs(), baseCoo.getUnitConverter(
		srcCoo.getUnitArgs())


_conformedAttributes = ["time", "place", "freq", "redshift", "velocity"]

def conform(baseSTC, srcSTC):
	"""returns srcSTC in the units and system of baseSTC.

	Items unspecified in baseSTC are taken from srcSTC.
	"""
	stcOverrides = {}
	for attName in _conformedAttributes:
		coo = getattr(srcSTC, attName)
		if coo is not None:
			elOverrides, conv = getUnitConverter(getattr(baseSTC, attName), coo)
			elOverrides.update(coo.iterTransformed(conv))
			stcOverrides[attName] = coo.change(**elOverrides)
	return srcSTC.change(**stcOverrides)
	
