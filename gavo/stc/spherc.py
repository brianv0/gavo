"""
Spherical sky coordinates and helpers.
"""

from math import sin, cos
import math
import numarray
from numarray import linear_algebra as la

from gavo.stc import sphermath
from gavo.stc import times
from gavo.stc.common import *
from gavo.utils import DEG, ARCSEC


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

def getFullPrecMatrix(fromEquinox, toEquinox, precTheory):
	"""returns a full 6x6 matrix for transforming positions and proper motions.
	"""
	return threeToSix(getPrecMatrix(fromEquinox, toEquinox, precTheory))


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

def fk4ToFK5(uvfk4):
	"""returns a FK5 2000 6-vector for an FK4 1950 6-vector.

	The procedure used is described in Yallop et al, AJ 97, 274.  E-terms
	of aberration are never removed from proper motions.
	"""


############### Galactic coordinates

_galB1950pole = (192.25/180*math.pi, 27.4/180*math.pi)
_galB1950zero = (265.6108440311/180*math.pi, -28.9167903484/180*math.pi)

_b1950ToGalTrafo = sphermath.computeTransMatrixFromPole(
	_galB1950pole, _galB1950zero)
_galToB1950Matrix = threeToSix(la.inverse(_b1950ToGalTrafo))
_b1950ToGalMatrix = threeToSix(_b1950ToGalTrafo)

# For convenience, a ready-made matrix, taken basically from SLALIB
_galToJ2000Matrix = threeToSix(numarray.transpose(numarray.array([
	[-0.054875539695716, -0.873437107995315, -0.483834985836994],
	[ 0.494109453305607, -0.444829589431879,  0.746982251810510],
	[-0.867666135847849, -0.198076386130820,  0.455983795721093]])))

############### Top-level code

def conformPrecess(fromSTC, toSTC):
	"""conforms fromSTC with toSTC including precession and reference frame
	fixing.
	"""
	if fromSTC.place.frame.refFrame=="FK5":
		precTheory = prec_IAU1976
	elif fromSTC.place.frame.refFrame=="FK4":
		precTheory = prec_Newcomb
	else:
		precTheory = None
	if precTheory:
		pm = getFullPrecMatrix(fromSTC.astroSystem.spaceFrame.getEquinox(),
			toSTC.astroSystem.spaceFrame.getEquinox(), precTheory)
	else:
		pm = _galToJ2000Matrix
	return sphermath.uvToSpher(
		numarray.dot(pm, sphermath.spherToUV(fromSTC)), toSTC)
