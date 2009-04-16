"""
Spherical sky coordinates and helpers.
"""

from math import sin, cos

from gavo import utils
from gavo.stc import times
from gavo.stc.common import *


def prec_IAU1976(fromEpoch, toEpoch):
	"""returns the precession angles in the IAU 1976 system.

	The expressions are those of Lieske, A&A 73, 282.

	This function is for the precTheory argument of getPrecMatrix.
	"""
	# time differences have to be in julian centuries
	# captial T in Lieske
	fromDiff = times.getSeconds(fromEpoch-times.dtJ2000)/secsPerJCy 
	# lowercase T in Lieske
	toDiff = times.getSeconds(toEpoch-fromEpoch)/secsPerJCy  

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


_dtB1850 = times.bYearToDateTime(1850)

def prec_Newcomb(fromEpoch, toEpoch):
	"""returns the precession angles for the newcomp

	This function is for the precTheory argument of getPrecMatrix.

	The expressions are Kinoshita (1975)'s from Aoki et al, (A&A 128, 263).
	"""
	# time differences have to be in tropical centuries
	T = times.getSeconds(fromEpoch-_dtB1850)/(tropicalYear*86400*100)
	t2 = times.getSeconds(toEpoch-_dtB1850)/(tropicalYear*86400*100)
	tau = t2-T

	zPzeta = tau**2+(0.79236+0.000656*T)+tau**3*0.000328
	zMZeta = tau*(4607.1096+2.79440*T+0.000118*T**2
		)+t**2*(1.39720+0.000118*T
		)+t**3*0.036320
	theta = tau*(2005.1125-0.85294*T-0.000375*T**2
		)-tau**2*(0.42647+0.000365*T
		)-0.041802*tau**3
	cv = utils.arcsecToRad
	return (zPzeta-zMzeta)*cv/2., (zPzeta+zMzeta)*cv/2., theta*cv


def getPrecMatrix(fromEpoch, toEpoch, precTheory):
	"""returns a precession matrix in the IAU(1976) system.


	fromEpoch and toEpoch are datetimes (in case of doubt, TT).

	precTheory(fromEpoch, toEpoch) -> zeta, z, theta computes the
	precession angles.  Defined in this module are prec_IAU1976 and 
	prec_Newcomb, but you can provide your own.  The angles must all be
	in rad.
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
