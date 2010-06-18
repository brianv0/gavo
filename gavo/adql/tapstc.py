"""
The subset of STC proposed by the TAP spec.

We mostly use this this subset rather than the full-blown STC library
since we don't have the latter in the database, and it's much slower
for generating (or parsing) STC-S strings.  Also, there are the ADQL
reference systems that require special handling anyway.
"""

from gavo import stc
from gavo import utils
from gavo.adql import common


TAP_SYSTEMS = set(
	['ICRS', 'FK4', 'FK5', 'GALACTIC', 'RELOCATABLE', 'UNKNOWN', '', "BROKEN"])

UNIVERSALLY_COMPATIBLE = set(['RELOCATABLE', 'UNKNOWN', '', "BROKEN"])

TRANSFORMS = {
# From "ICRS" (really, FK5 J2000, and the lo-prec) to...
	'FK4': (1.5651864333666516, -0.0048590552804904244, -1.5763681043529187),
	'FK5': None,
	'ICRS': None,
	'GALACTIC': (1.3463560974407338, -1.0973190018372752, 0.57477052472873258),
}


def _getEulersFor(frame):
	if not frame in TRANSFORMS:
		raise common.GeometryError("Unknown reference frame: %s"%frame)
	return TRANSFORMS[frame]


def getPGSphereTrafo(fromSys, toSys):
	"""returns a pgsphere expression fragment to turn a pgsphere geometry
	from fromSys to toSys.

	fromSys and toSys are system designations like for TAP.

	If the systems are "compatible" (i.e., no transformation is deemed necessary),
	None is returned.  A GeometryError is raised for incomprehensible system
	specifications.
	"""
	if (fromSys in UNIVERSALLY_COMPATIBLE
			or toSys in UNIVERSALLY_COMPATIBLE):
		return None
	if fromSys=='ICRS':
		template = "+strans(%f,%f,%f)"
	elif toSys=='ICRS':
		angles = _getEulersFor(fromSys)
		template = "-strans(%f,%f,%f)"
	else:
		t1 = getPGSphereTrafo(fromSys, 'ICRS')
		t2 = getPGSphereTrafo('ICRS', toSys)
		return "%s%s"%(t1 or "", t2 or "")
	angles = _getEulersFor(fromSys)
	if angles:
		return template%angles
	return None


def getTAPSTC(stcInstance):
	"""returns a tap system identifier for an STC AstroSystem.

	This is stc.spaceFrame.refFrame if existing and TAP-defined, UNKNOWN
	otherwise.
	"""
	rf = None
	if stcInstance.spaceFrame:
		rf = stcInstance.spaceFrame.refFrame
	if rf not in TAP_SYSTEMS:
		return "UNKNOWN"
	return rf


@utils.memoized
def getSTCForTAP(tapIdentifier):
	"""returns an stc AST for a tap reference system identifier.
	"""
	tapIdentifier = utils.identifierRE.findall(tapIdentifier)[0]
	if tapIdentifier in ["BROKEN", '', "UNKNOWN"]:
		tapIdentifier = "UNKNOWNFrame"
	ast = stc.parseSTCS("Position %s"%tapIdentifier).astroSystem
	if tapIdentifier=='BROKEN':
		ast.broken = True
	return ast


if __name__=="__main__":
# compute the Euler angles given above.  pgsphere has its rotation
# matrices opposite to ours (ccw rather than cw), hence the negation
	from kapteyn import celestial
	from gavo.stc import spherc, sphermath
	print "FK4:", tuple(-a for a in 
		sphermath.getEulerAnglesFromMatrix(
			celestial.skymatrix("icrs", "fk4 B1950.0")[0]))
	print "GAL:", tuple(-a for a in 
		sphermath.getEulerAnglesFromMatrix(
			celestial.skymatrix("icrs", "galactic")[0]))

