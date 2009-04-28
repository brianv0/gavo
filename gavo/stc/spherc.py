"""
Spherical sky coordinates and helpers.
"""

from itertools import *
from math import sin, cos
import math

import numarray
from numarray import linear_algebra as la

from gavo.stc import sphermath
from gavo.stc import times
from gavo.stc.common import *
from gavo.utils import DEG, ARCSEC, memoized


############### Basic definitions for transforms

# Finding transformation sequences: This, in principle, is a standard
# graph problem.  However, we have lots of underspecified transforms,
# which makes building a Dijkstrable graph somewhat inconvenient.  So,
# instead of striving for an optimal shortest path, we go for a
# greedy search with some heuristics.  The most nonstandard feature is
# that nodes are built ad-hoc and noncircularity of the paths thorugh
# the "virtual" graph is checked on these ad-hoc nodes.

# The nodes in the graph are triples of (system, equinox, refpos).  The
# vertices are triples (fromNode, toNode, transform generator).
# Transform generators are functions 
#
# f(fromNode, toNode) -> (function or matrix)
#
# The arguments are node triples, the result either a function taking
# and returning 6-vectors or numarray matrices.  These functions may
# assume that only "appropriate" values are passed in as nodes, i.e.,
# they are not assumed to check that the are actually able to produce
# the requested transformation.

class _Wildcard(object): 
	"""is an object that compares equal to everything.

	This is used for underspecification of transforms, see SAME and
	ANYVAL below.
	"""
	def __init__(self, name):
		self.name = name
	
	def __repr__(self):
		return self.name

	def __ne__(self, other): return False
	def __eq__(self, other): return True


SAME = _Wildcard("SAME")
ANYVAL = _Wildcard("ANYVAL")

def _specifyTrafo(trafo, fromTuple, toTuple):
	"""fills in underspecified values in trafo from fromTuple and toTuple.

	The rules are: In the source, both SAME and ANYVAL are filled from
	fromTuple.  In the destination, SAME is filled from fromTuple,
	ANYVAL is filled from toTuple.

	The function returns a new transformation triple.
	"""
	src, dst, tgen = trafo
	newSrc, newDst = [], []
	for ind, val in enumerate(src):
		if val is SAME or val is ANYVAL:
			newSrc.append(fromTuple[ind])
		else:
			newSrc.append(val)
	for ind, val in enumerate(dst):
		if val is SAME:
			newDst.append(fromTuple[ind])
		elif val is ANYVAL:
			newDst.append(toTuple[ind])
		else:
			newDst.append(val)
	return tuple(newSrc), tuple(newDst), tgen


def _makeFindPath(transforms):
	"""returns a function for path finding in the virtual graph
	defined by transforms.

	Each transform is a triple of (fromNode, toNode, transformFactory).

	There's quite a bit of application-specific heuristics built in
	here, so there's litte you can do with this code outside of
	STC transforms construction.
	"""
	def findPath(fromTuple, toTuple, path=()):
		"""returns a sequence of transformation triples that lead from
		fromTuple to toTuple.

		fromTuple and toTuple are node triples (i.e., (system, equinox,
		refpoint)).

		The returned path is not guaranteed to be the shortest or even
		the numerically most stable.  It is the result of a greedy
		search for a cycle free path between the two "non-virtual" nodes.
		To keep the paths reasonable, we apply the heuristic that
		transformations keeping the system are preferable.

		The simple heuristics sometimes need help; e.g., the transformations
		below add explicit transformations to j2000 and b1950; you will always
		need this if your transformations include "magic" values for otherwise
		underspecified items.
		"""
		seenSystems = set(c[0] for c in path) | set(c[1] for c in path)
		candidates = [_specifyTrafo(t, fromTuple, toTuple) 
				for t in transforms if t[0]==fromTuple]
		# sort operations within the same reference system to the start
		candidates = [c for c in candidates if c[1][0]==toTuple[0]] + [
			c for c in candidates if c[1]!=toTuple[0]]
		for cand in candidates:
			srcSystem, dstSystem, tgen = cand
			# Ignore identities or trafos leading to cycles
			if srcSystem==dstSystem or dstSystem in seenSystems:
				continue
			if dstSystem==toTuple:  # If we are done, return result
				return path+(cand,)
			else:
				# Do the depth-first search
				np = findPath(dstSystem, toTuple, path+(cand,))
				if np:
					return np
	return findPath



############### Computation of precession matrices.

def prec_IAU1976(fromEquinox, toEquinox):
	"""returns the precession angles in the IAU 1976 system.

	The expressions are those of Lieske, A&A 73, 282.

	This function is for the precTheory argument of getPrecMatrix.
	"""
	# time differences have to be in julian centuries
	# captial T in Lieske
	fromDiff = times.getSeconds(fromEquinox-times.dtJ2000)/secsPerJCy 
	# lowercase T in Lieske
	toDiff = times.getSeconds(toEquinox-fromEquinox)/secsPerJCy  

	# Lieske's expressions yield arcsecs, fix below
	zeta = toDiff*(2306.2181+1.39656*fromDiff-0.000139*fromDiff**2
		)+toDiff**2*(0.30188-0.000344*fromDiff
		)+toDiff**3*0.017998
	z =    toDiff*(2306.2181+1.39656*fromDiff-0.000139*fromDiff**2
		)+toDiff**2*(1.09468+0.000066*fromDiff
		)+toDiff**3*0.018203
	theta = toDiff*(2004.3109-0.85330*fromDiff-0.000217*fromDiff**2
		)-toDiff**2*(0.42665+0.000217*fromDiff
		)-toDiff**3*0.041833
	return zeta*ARCSEC, z*ARCSEC, theta*ARCSEC


_dtB1850 = times.bYearToDateTime(1850)

def prec_Newcomb(fromEquinox, toEquinox):
	"""returns the precession angles for the newcomp

	This function is for the precTheory argument of getPrecMatrix.

	The expressions are Kinoshita's (1975)'s (SAOSR 364) 
	This is somewhat at odds with Yallop's choice of Andoyer in the FK4-FK5
	machinery below, but that really shouldn't matter.
	"""
	# time differences have to be in tropical centuries
	T = times.getSeconds(fromEquinox-_dtB1850)/(tropicalYear*86400*100)
	t = times.getSeconds(toEquinox-fromEquinox)/(tropicalYear*86400*100)

	common = 2303.5548+(1.39720+0.000059*T)*T
	zeta = (common+(0.30242-0.000269*T+0.017996*t)*t)*t
	z = (common+(1.09478+0.000387*T+0.018324*t)*t)*t
	theta = (2005.1125+(-0.85294-0.000365*T)*T
		+(-0.42647-0.000365*T-0.041802*t)*t)*t
	return zeta*ARCSEC, z*ARCSEC, theta*ARCSEC


def getPrecMatrix(fromEquinox, toEquinox, precTheory):
	"""returns a precession matrix in the IAU(1976) system.

	fromEquinox and toEquinox are datetimes (in case of doubt, TT).

	precTheory(fromEquinox, toEquinox) -> zeta, z, theta computes the
	precession angles.  Defined in this module are prec_IAU1976 and 
	prec_Newcomb, but you can provide your own.  The angles must all be
	in rad.
	"""
	zeta, z, theta = precTheory(fromEquinox, toEquinox)
	return numarray.dot(
		numarray.dot(sphermath.getRotZ(-z), sphermath.getRotY(theta)),
		sphermath.getRotZ(-zeta))


_nullMatrix = numarray.zeros((3,3))
def threeToSix(matrix):
	"""returns a 6-matrix from a 3-matrix suitable for precessing our
	6-vectors.
	"""
	return numarray.concatenate((
		numarray.concatenate(  (matrix,      _nullMatrix), 1),
		numarray.concatenate(  (_nullMatrix, matrix     ), 1)))

def _getFullPrecMatrix(fromNode, toNode, precTheory):
	"""returns a full 6x6 matrix for transforming positions and proper motions.

	This only works for proper equatorial coordinates in both STC values.

	precTheory is a function returning precession angles.
	"""
	return threeToSix(getPrecMatrix(fromNode[1], toNode[1], precTheory))


def _getNewcombPrecMatrix(fromNode, toNode):
	return _getFullPrecMatrix(fromNode, toNode, prec_Newcomb)

def _getIAU1976PrecMatrix(fromNode, toNode):
	return _getFullPrecMatrix(fromNode, toNode, prec_IAU1976)


############### FK4-FK5 system transformation
# This follows the prescription of Yallop et al, AJ 97, 274

_fk4ToFk5Matrix = numarray.array([
	[0.999925678186902, -0.011182059642247, -0.004857946558960,
		0.000002423950176, -0.000000027106627, -0.000000011776558],
	[0.011182059571766, 0.999937478448132, -0.000027176441185,
		0.000000027106627, 0.000002723978783, -0.000000000065874],
	[0.004857946721186, -0.000027147426489, 0.9999881997387700,
		0.000000011776559, -0.000000000065816, 0.000002424101735],
	[-0.000541652366951, -0.237968129744288, 0.436227555856097,
		0.999947035154614, -0.011182506121805, -0.004857669684959],
	[0.237917612131583, -0.002660763319071,	-0.008537771074048,
		0.011182506007242, 0.999958833818833, -0.000027184471371],
	[-0.436111276039270, 0.012259092261564, 0.002119110818172,
		0.004857669948650, -0.000027137309539, 1.000009560363559]])
_fk5Tofk4Matrix = la.inverse(_fk4ToFk5Matrix)

# Positional correction due to E-Terms, in rad (per tropical century in the
# case of Adot, which is ok for sphermath._uvPosUnit (Yallop et al, loc cit, p.
# 276).  In PM, we ignore the "small" terms of Yallop's equation (3).  We also
# ignore the difference between tropical and julian centuries.
_b1950ETermsA = numarray.array([-1.62557e-6, -0.31919e-6, 0.13843e-6,
	1.245e-3*ARCSEC, -1.580e-3*ARCSEC, -0.659e-3*ARCSEC])

def fk4ToFK5(uvfk4):
	"""returns an FK5 2000 6-vector for an FK4 1950 6-vector.

	The procedure used is described in Yallop et al, AJ 97, 274.  E-terms
	of aberration are always removed from proper motions, regardless of
	whether the objects are within 10 deg of the pole.
	"""
	uvETerm = uvfk4-_1950ETermsA+numarray.dot(
		(numarray.dot(numarray.transpose(uvfk4), _b1950ETermsA),
		uvfk4))
	return numarray.dot(_fk4ToFk5Matrix, uvETerm)
	

def fk5ToFK4(uvfk5):
	"""returns an FK4 1950 6-vector for an FK5 2000 6-vector.
	"""
	return uvfk5


############### Galactic coordinates

_galB1950pole = (192.25/180*math.pi, 27.4/180*math.pi)
_galB1950zero = (265.6108440311/180*math.pi, -28.9167903484/180*math.pi)

_b1950ToGalTrafo = sphermath.computeTransMatrixFromPole(
	_galB1950pole, _galB1950zero)
_b1950ToGalMatrix = threeToSix(_b1950ToGalTrafo)

# For convenience, a ready-made matrix, taken basically from SLALIB
_galToJ2000Matrix = threeToSix(numarray.transpose(numarray.array([
	[-0.054875539695716, -0.873437107995315, -0.483834985836994],
	[ 0.494109453305607, -0.444829589431879,  0.746982251810510],
	[-0.867666135847849, -0.198076386130820,  0.455983795721093]])))


############### Reference positions
# XXX TODO: We don't transform anything here.  Yet.  This will not
# hurt for moderate accuracy expectations in the stellar and
# extragalactic regime but makes this libarary basically useless for
# solar system work.

def _transformRefpos(fromSTC, toSTC):
	return utils.identity


############### Top-level code


def _Constant(val):
	"""returns a transform factory always returning val.
	"""
	return lambda fromSTC, toSTC: val


# transforms are triples of fromNode, toNode, transform factory.  Due to
# the greedy nature of your "virtual graph" searching, it's generally a
# good idea to put more specific transforms further up.

_findTransformsPath = _makeFindPath([
	(("FK4", times.dtB1950, SAME), ("FK5", times.dtJ2000, SAME),
		_Constant(fk4ToFK5)),
	(("FK5", times.dtJ2000, SAME), ("FK4", times.dtB1950, SAME),
		_Constant(fk5ToFK4)),
	(("FK5", times.dtJ2000, SAME), ("GALACTIC", ANYVAL, SAME),
		_Constant(la.inverse(_galToJ2000Matrix))),
	(("GALACTIC", ANYVAL, SAME), ("FK5", times.dtJ2000, SAME),
		_Constant(_galToJ2000Matrix)),
	(("FK4", times.dtB1950, SAME), ("GALACTIC", ANYVAL, SAME),
		_Constant(_b1950ToGalMatrix)),
	(("GALACTIC", ANYVAL, SAME), ("FK4", times.dtB1950, SAME),
		_Constant(la.inverse(_b1950ToGalMatrix))),
	(("FK5", ANYVAL, SAME), ("FK5", times.dtJ2000, SAME),
		_getIAU1976PrecMatrix),
	(("FK4", ANYVAL, SAME), ("FK4", times.dtB1950, SAME),
		_getNewcombPrecMatrix),
	(("FK5", ANYVAL, SAME), ("FK5", ANYVAL, SAME),
		_getIAU1976PrecMatrix),
	(("FK4", ANYVAL, SAME), ("FK4", ANYVAL, SAME),
		_getNewcombPrecMatrix),
	((SAME, SAME, ANYVAL), (SAME, SAME, ANYVAL),
		_Constant(_transformRefpos)),
])


_precessionFuncs = set([_getNewcombPrecMatrix, _getIAU1976PrecMatrix])

def _contractPrecessions(toContract):
	"""contracts the precessions in toContract.
	
	No checks done.  This is only intended as a helper for _simplifyPath.
	"""
	return toContract[0][0], toContract[-1][1], toContract[0][-1]


def _simplifyPath(path):
	"""tries to simplify path by contracting mulitple consecutive precessions.

	These come in since our path finding algorithm sucks.  This is mainly
	done for numerical reasons since the matrices would be contracted for
	computation anyway.
	"""
# Sorry about this complex mess.  Maybe we want a more general optimization
# framework.
	if path is None:
		return path
	newPath, toContract = [], []
	curPrecFunc = None
	for t in path:
		if curPrecFunc:
			if t[-1] is curPrecFunc:
				toContract.append(t)
			else:
				newPath.append(_contractPrecessions(toContract))
				if t[-1] in _precessionFuncs:
					curPrecFunc, toContract = t[-1], [t]
				else:
					curPrecFunc, toContract = None, []
					newPath.append(t)
		else:
			if t[-1] in _precessionFuncs:
				curPrecFunc = t[-1]
				toContract = [t]
			else:
				newPath.append(t)
	if toContract:
		newPath.append(_contractPrecessions(toContract))
	return newPath

def _contractMatrices(ops):
	"""combines consecutive numarray.matrix instances in the sequence
	ops by dot-multiplying them.
	"""
	newSeq, curMat = [], None
	for op in ops:
		if isinstance(op, numarray.NumArray):
			if curMat is None:
				curMat = op
			else:
				curMat = numarray.dot(curMat, op)
		else:
			if curMat is not None:
				newSeq.append(curMat)
				curMat = None
			newSeq.append(op)
	if curMat is not None:
		newSeq.append(curMat)
	return newSeq
	

def _pathToFunction(trafoPath):
	"""returns a function encapsulating all operations contained in
	trafoPath.

	The function receives and returns a 6-vector.
	"""
	steps = _contractMatrices([factory(srcTrip, dstTrip)
		for srcTrip, dstTrip, factory in trafoPath])
	expr = []
	for index, step in enumerate(steps):
		if isinstance(step, numarray.NumArray):
			expr.append("numarray.dot(steps[%d], "%index)
		else:
			expr.append("steps[%d]("%index)
	vars = {"steps": steps, "numarray": numarray}
	exec ("def transform(uv): return %s"%
		"".join(expr)+"uv"+(")"*len(expr))) in vars
	return vars["transform"]


@memoized
def getTrafoFunction(srcTriple, dstTriple):
	"""returns a function that transforms 6-vectors from the system
	described by srcTriple to the one described by dstTriple.

	The triples consist of (system, equinox, refpoint).

	If no transformation function can be produced, the function raises
	an STCValueError.
	"""
	trafoPath = _simplifyPath(_findTransformsPath(srcTriple, dstTriple))
	if trafoPath is None:
		raise STCValueError("Cannot find a transform from %s to %s"%(
			srcTriple, dstTriple))
	return _pathToFunction(trafoPath)



def conformSpherical(fromSTC, toSTC):
	"""conforms places and velocities in fromSTC with toSTC including 
	precession and reference frame fixing.
	"""
	trafo = getTrafoFunction(fromSTC.place.frame.getTuple(),
		toSTC.place.frame.getTuple())
	return sphermath.uvToSpher(
		trafo(sphermath.spherToUV(fromSTC)), toSTC)
