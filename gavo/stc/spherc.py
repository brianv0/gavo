"""
Spherical sky coordinates and helpers.
"""

from math import sin, cos

from gavo import utils
from gavo.stc import times


def _getIAU1976PrecAngles(fromEpoch, toEpoch):
	"""returns the precession angles in the IAU 1976 system.

	This is a helper for getIAU1976PrecMatrix and returns zeta, z, and theta
	in rads.
	"""
	# time differences have to be in julian centuries
	# captial T in Lieske
	fromDiff = times.getSeconds(fromEpoch-times.dtJ2000)/utils.secsPerJCy 
	# lowercase T in Lieske
	toDiff = times.getSeconds(toEpoch-fromEpoch)/utils.secsPerJCy  

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
	cv = utils.arcsecToRad
	return zeta*cv, z*cv, theta*cv


def getIAU1976PrecMatrix(fromEpoch, toEpoch):
	"""returns a precession matrix in the IAU(1976) system.

	This uses the matrix and algorithm given by Lieske, A&A 73, 282.

	fromEpoch and toEpoch are datetimes (in case of doubt, TT).
	"""
	zeta, z, theta = _getIAU1976PrecAngles(fromEpoch, toEpoch)

	return numarray.array([
		[cos(z)*cos(theta)*cos(zeta)-sin(z)*sin(zeta),
			-cos(z)*cos(theta)*sin(zeta)-sin(z)*cos(zeta),
			-cos(z)*sin(theta)],
		[sin(z)*cos(theta)*cos(zeta)+cos(z)*sin(zeta),
			-sin(z)*cos(theta)*sin(zeta)+cos(z)*cos(zeta),
			-sin(z)*sin(theta)],
		[sin(theta)*cos(zeta),
			-sin(theta)*sin(zeta),
			cos(theta)]])
