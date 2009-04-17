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
	if baseCoo.getUnitArgs()==srcCoo.getUnitArgs():
		return None, None
	return baseCoo.getUnitArgs(), baseCoo.getUnitConverter(
		srcCoo.getUnitArgs())


_conformedAttributes = [("time", "timeAs"), ("place", "areas"), 
	("freq", "freqAs"), ("redshift", "redshiftAs"), ("velocity", "velocityAs")]


def conformUnits(baseSTC, srcSTC):
	"""returns srcSTC in the units of baseSTC.
	"""
	stcOverrides = {}
	for attName, dependentName in _conformedAttributes:
		coo = getattr(srcSTC, attName)
		if coo is not None:
			elOverrides, conv = getUnitConverter(getattr(baseSTC, attName), coo)
			if conv is None:  # units are already ok
				continue
			elOverrides.update(coo.iterTransformed(conv))
			stcOverrides[attName] = coo.change(**elOverrides)
			areas = getattr(srcSTC, dependentName)
			if areas:
				transformed = []
				for a in areas:
					if hasattr(a, "adaptValuesWith"):  # Geometries are not adapted
						transformed.append(a.adaptValuesWith(conv))
					else:
						transformed.append(a)
				stcOverrides[dependentName] = tuple(transformed)
	return srcSTC.change(**stcOverrides)


def conform(baseSTC, srcSTC):
	"""returns srcSTC in the units and system of baseSTC.

	Items unspecified in baseSTC are taken from srcSTC.
	"""
	return conformUnits(baseSTC, srcSTC)
