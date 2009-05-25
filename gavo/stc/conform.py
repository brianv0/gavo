"""
"Conforming" of STCSpecs, i.e., bringing one to the system and units of the
other.

You can only conform STCSpecs rather than individual components, since 
usually you need the whole information for the transformation (e.g.,
space and time for velocities.
"""

from gavo import utils
from gavo.stc import spherc
from gavo.stc import sphermath
from gavo.stc import units


_conformedAttributes = [("time", "timeAs"), ("place", "areas"), 
	("freq", "freqAs"), ("redshift", "redshiftAs"), ("velocity", "velocityAs")]


def conformUnits(baseSTC, srcSTC):
	"""returns srcSTC in the units of baseSTC.
	"""
	stcOverrides = []
	for attName, dependentName in _conformedAttributes:
		stcOverrides.extend(units.iterUnitAdapted(baseSTC, srcSTC,
			attName, dependentName))
	return srcSTC.change(**dict(stcOverrides))


def conformSpherical(fromSTC, toSTC, relativistic=False, slaComp=False):
	"""conforms places and velocities in fromSTC with toSTC including 
	precession and reference frame fixing.
	"""
	if fromSTC.place is None or toSTC.place is None:
		return fromSTC
	features, src6 = sphermath.spherToSV(fromSTC, relativistic)
	features.slaComp = slaComp
	trafo = spherc.getTrafoFunction(fromSTC.place.frame.asTriple(),
		toSTC.place.frame.asTriple(), features)
	toSTC = conformUnits(toSTC, fromSTC)
	return sphermath.svToSpher(trafo(src6, features), toSTC, features=features)


def conform(baseSTC, srcSTC):
	"""returns srcSTC in the units and system of baseSTC.

	Items unspecified in baseSTC are taken from srcSTC.
	"""
	return conformUnits(baseSTC, srcSTC)
