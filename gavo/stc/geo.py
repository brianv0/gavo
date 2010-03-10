"""
Coordinate systems for positions on earth.
"""

import math

from gavo.utils import DEG


class WGS84(object):
	"""the WGS84 reference system.
	"""
	a = 6378137.
	f1 = 298.257223563  # f^-1!
	GM = 3.986005e14    # m3s-1
	J2 = 0.00108263
	omega = 7.292115e-5 # rad s-1


def _getC_S(phi, refSys):
	"""returns the values of the auxillary functions C and S.

	phi must be in rad.

	See Astron. Almanac, Appendix K.
	"""
	C = math.sqrt(
			math.cos(phi)**2
			+((1-1/refSys.f1)*math.sin(phi))**2)
	S = (1-1/refSys.f1)**2*C
	return C, S


def geocToGeod(long, phip, rho=1, refSys=WGS84):
	"""returns geodetic coordinates long, phi for geocentric coordinates.

	refSys defaults is the reference system the geodetic coordinates are
	expressed in.

	This will not work at the poles -- patches welcome.

	See Astron. Almanac, Appendix K; we go for the iterative solution
	discussed there.
	"""
	long, phip = long*DEG, phip*DEG
	x = refSys.a*rho*math.cos(phip)*math.cos(long)
	y = refSys.a*rho*math.cos(phip)*math.sin(long)
	z = refSys.a*rho*math.sin(phip)

	e2 = 2/refSys.f1-1/refSys.f1**2
	lam = math.atan2(y, x)
	r = math.sqrt(x**2+y**2)
	phi = math.atan2(z, r)

	while True:
		phi1 = phi
		C = math.sqrt((1-e2*math.sin(phi1)**2))
		phi = math.atan2(z+refSys.a*C*e2*math.sin(phi1), r)
		if abs(phi1-phi)<1e-14: # phi is always of order 1
			break
	return long/DEG, phi1/DEG, r/math.cos(phi)-refSys.a*C



def geodToGeoc(long, phi, height, refSys=WGS84):
	"""returns geocentric coordinates lambda, phi', rho for geodetic coordinates.

	refSys defaults is the reference system the geodetic coordinates are
	expressed in.

	height is in meter, long, phi in degrees.

	See Astron. Almanac, Appendix K.
	"""
	long, phi = long*DEG, phi*DEG
	C, S = _getC_S(phi, refSys)
	rcp = (refSys.a*C+height)*math.cos(phi)/refSys.a
	rsp = (refSys.a*S+height)*math.sin(phi)/refSys.a
	rho = math.sqrt(rcp**2+rsp**2)
	phip = math.atan2(rsp, rcp)
	return long/DEG, phip/DEG, rho
