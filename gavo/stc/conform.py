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
from gavo.stc.common import *


_conformedAttributes = [("time", "timeAs"), ("place", "areas"), 
	("freq", "freqAs"), ("redshift", "redshiftAs"), ("velocity", "velocityAs")]


def _getDestItems(baseSTC, sysSTC):
	"""returns the units and the frame for a conversion into into sysSTC.

	The funciton returns spaceUnit, velSpaceUnit, velTimeUnit, spaceFrame
	in that order.  Each item is initialized to None, then updated from baseSTC.
	The frame is taken from sysSTC if possible, the units are not; they will
	be handled by conformUnits to make sure that dependents are unit adapted 
	as well.
	"""
	spaceUnit, velSpaceUnit, velTimeUnit, spaceFrame = None, None, None, None
	if baseSTC.place is not None:
		spaceUnit, spaceFrame = baseSTC.place.unit, baseSTC.place.frame
	if baseSTC.velocity is not None:
		v = baseSTC.velocity
		if spaceFrame is None: # Fix frame if no position has been given
			spaceFrame = v.frame
		velSpaceUnit, velTimeUnit = v.unit, v.velTimeUnit
	if sysSTC.place is not None:
		spaceFrame = sysSTC.place.frame
	if sysSTC.velocity is not None:
		spaceFrame = sysSTC.velocity.frame
	return spaceUnit, velSpaceUnit, velTimeUnit, spaceFrame


def iterSpatialChanges(baseSTC, sysSTC, features):
	"""yields changes to baseSTC to bring places and velocities to the
	system and units of sysSTC.

	features is an InputFeatures instance as prepared by spherToSV.  

	If the frame or units are not defined in sysSTC, there are taken from
	baseSTC.
	"""
	toSpaceUnit, toVelSpaceUnit, toVelTimeUnit, spaceFrame = _getDestItems(
		baseSTC, sysSTC)
	if spaceFrame is None:  # Neither pos nor vel given, nothing to fix
		return

	# do the actual transformation of place/velocity
	sv = sphermath.spherToSV(baseSTC, features)
	trafo = spherc.getTrafoFunction(baseSTC.place.frame.asTriple(),
		sysSTC.place.frame.asTriple(), features)
	sv = trafo(sv, features)
	pos, posUnit, vel, velSUnit, velTUnit = sphermath.svToSpher(sv, features)
	bPlace, bVel = baseSTC.place, baseSTC.velocity

	# build spatial items to change if necessary
	if bPlace:
		fixSpaceUnit = units.getVectorConverter(posUnit, toSpaceUnit)
		value = None
		if features.posGiven:
			value = fixSpaceUnit(pos)
		yield "place", bPlace.change(value=value, frame=spaceFrame)
		if baseSTC.areas:
			newAreas = []
			sTrafo = sphermath.makePlainSphericalTransformer(trafo, 
				bPlace.unit[:2])
			for a in baseSTC.areas:
				if hasattr(a, "getFullTransformed"): # it's a space interval that
						# has full dimensionality.
					newAreas.append(a.getFullTransformed(trafo, None, None))
				else: # it's a geometry that's always 2-spherical
					newAreas.append(a.getTransformed(sTrafo, spaceFrame))
			yield "areas", newAreas

	# build velocity items to change if necessary
	if bVel:
		fixVelUnit = units.getVelocityConverter(velSUnit, velTUnit, 
			toVelSpaceUnit, toVelTimeUnit)
		value = None
		if features.posdGiven:
			value = fixVelUnit(vel)
		yield "velocity", bVel.change(value=value, frame=spaceFrame)
# XXX TODO: velocityAs


def conformUnits(baseSTC, sysSTC):
	"""returns baseSTC in the units of sysSTC.
	"""
	changes = []
	for attName, dependentName in _conformedAttributes:
		changes.extend(units.iterUnitAdapted(baseSTC, sysSTC,
			attName, dependentName))
	return baseSTC.change(**dict(changes))


def conformSystems(baseSTC, sysSTC, relativistic=False, slaComp=False):
	"""conforms places and velocities in fromSTC with toSTC including 
	precession and reference frame fixing.
	"""
	changes = [("astroSystem", sysSTC.astroSystem)]
	if baseSTC.place is not None and sysSTC.place is not None:
		# adapt places
		features = InputFeatures(relativistic=relativistic, slaComp=slaComp)
		changes.extend(iterSpatialChanges(baseSTC, sysSTC, features))
# XXX TODO: conform time frames
	return conformUnits(baseSTC.change(**dict(changes)), sysSTC)


def conform(baseSTC, sysSTC, **kwargs):
	"""returns baseSTC in the units and the system of sysSTC.
	"""
	if baseSTC.astroSystem==sysSTC.astroSystem:
		return conformUnits(baseSTC, sysSTC)
	else:
		return conformSystems(baseSTC, sysSTC, **kwargs)
