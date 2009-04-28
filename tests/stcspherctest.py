"""
Tests for the calculations with various spherical coordinate systems.
"""

import datetime
import math
import re

import numarray

from gavo import stc
from gavo import utils
from gavo.stc import spherc
from gavo.stc import sphermath
from gavo.stc import times

from gavo.utils import DEG

import stcgroundtruth
import testhelpers


class PrecAnglesTest(testhelpers.VerboseTest):
	"""tests for various precessions.
	"""
	def testLieskeConstantsFromJ2000(self):
		for year, zetaL, zL, thetaL in [
				(1950, -1153.036, -1152.838, -1002.257),
				(1980, -461.232, -461.200, -400.879),
				(2050, 1153.187, 1153.385, 1002.044)]:
			destEp = stc.jYearToDateTime(year)
			zeta, z, theta = spherc.prec_IAU1976(times.dtJ2000, destEp)
			self.assertAlmostEqual(zeta/utils.ARCSEC, zetaL, places=3)
			self.assertAlmostEqual(z/utils.ARCSEC, zL, places=3)
			self.assertAlmostEqual(theta/utils.ARCSEC, thetaL, places=3)

	def testLieskeConstantsToJ2000(self):
		for year, zetaL, zL, thetaL in [
				(1850, 3456.881, 3458.664, 3007.246),
				(1920, 1844.273, 1844.781, 1603.692),
				(1965, 807.055, 807.152, 701.570),]:
			srcEp = stc.bYearToDateTime(year)
			zeta, z, theta = spherc.prec_IAU1976(srcEp, times.dtJ2000)
			self.assertAlmostEqual(zeta/utils.ARCSEC, zetaL, places=3)
			self.assertAlmostEqual(z/utils.ARCSEC, zL, places=3)
			self.assertAlmostEqual(theta/utils.ARCSEC, thetaL, places=3)


_b = "BARYCENTER"
_t = "TOPOCENTER"
J2000 = times.dtJ2000
B1950 = times.dtB1950
B1885 = times.bYearToDateTime(1885)
J1992 = times.bYearToDateTime(1992.25)

class PathTest(testhelpers.VerboseTest):
	"""tests for finding paths in the "virtual graph" of transforms.
	
	This is a rather fragile test due to the whacky heuristics inherent in
	path finding by spherc.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fromTriple, toTriple, path0 = sample
		path = tuple(t[1] for t in
			spherc._findTransformsPath(fromTriple, toTriple))
		self.assertEqual(path0, path)

	samples = [
		(("FK4", B1950, _b), ("FK5", J2000, _b), (
			('FK5', J2000, 'BARYCENTER'),)),
		(("FK4", B1950, _b), ("FK5", datetime.datetime(2009, 10, 2), _b), (
			('FK5', J2000, _b), ('FK5', datetime.datetime(2009, 10, 2, 0, 0), _b))),
		(("FK5", B1950, _b), ("FK4", J2000, _b), (
			('FK5', J2000, _b), ('FK4', B1950, _b), ('FK4', J2000, _b))),
		(("FK4", B1885, _b), ("FK5", J1992, _b), (
			('FK4', B1950, _b), ('FK5', J2000, _b), 
			('FK5', datetime.datetime(1992, 4, 1, 9, 45, 9, 292082), _b))),
		(("FK5", B1885, _b), ("FK5", J1992, _b), (
			('FK5', J2000, _b), 
			('FK5', datetime.datetime(1992, 4, 1, 9, 45, 9, 292082), _b))),
		(("FK5", B1885, _b), ("GALACTIC", None, _b), (
			('FK5', J2000, _b), ('GALACTIC', None, _b))),
		(("FK4", B1885, _b), ("GALACTIC", None, _b), (
			('FK4', B1950, _b), ('GALACTIC', None, _b))),
		(("FK4", B1885, _t), ("GALACTIC", None, _b), (
			('FK4', B1950, _t), ('GALACTIC', None, _t), ('GALACTIC', None, _b))),
	]


class SpherUVRoundtripTest(testhelpers.VerboseTest):
	"""tests for conversion between 6-vectors and spherical coordinates.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		ast0 = stc.parseSTCS(sample)
		ast1 = sphermath.uvToSpher(sphermath.spherToUV(ast0), ast0)
		self.assertEqual(ast0, ast1)

	samples = [
		"Position ICRS -20 -50",
		"Position ICRS SPHER3 -20 -50 2 unit deg deg pc",
		"Position ICRS -20 -50 VelocityInterval Velocity 1 2 unit arcsec/yr",
		"Position ICRS SPHER3 45 -30 2 unit deg deg pc"
			" VelocityInterval Velocity 1 -2 40 unit arcsec/yr arcsec/yr km/s",
		"Position ICRS SPHER3 3.2 -0.5 0.1 unit rad rad arcsec"
			" VelocityInterval Velocity 1 -2 40 unit arcsec/cy arcsec/cy km/s",
		]


class SpherMathTests(testhelpers.VerboseTest):
	"""tests for some basic functionality of sphermath.
	"""
	def testRotateY(self):
		ast = stc.parseSTCS("Position ICRS 0 10")
		uv = sphermath.spherToUV(ast)
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotY(angle/180.*math.pi))
			res = sphermath.uvToSpher(numarray.dot(matrix, uv), ast).place.value
			self.assertAlmostEqual(res[1], 10+angle)

	def testRotateX(self):
		ast = stc.parseSTCS("Position ICRS 270 10")  # XXX that right?  90???
		uv = sphermath.spherToUV(ast)
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotX(angle/180.*math.pi))
			res = sphermath.uvToSpher(numarray.dot(matrix, uv), ast).place.value
			self.assertAlmostEqual(res[1], 10+angle)

	def testRotateZ(self):
		ast = stc.parseSTCS("Position ICRS 180 0")
		uv = sphermath.spherToUV(ast)
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotZ(angle/180.*math.pi))
			res = sphermath.uvToSpher(numarray.dot(matrix, uv), ast).place.value
			self.assertAlmostEqual(res[0], 180-angle)  # XXX that right?  +???

	def testSimpleSpher(self):
		for theta, phi in [(0, -90), (20, -89), (180, -45), (270, 0),
				(358, 45), (0, 90)]:
			thetaObs, phiObs = sphermath.cartToSpher(
				sphermath.spherToCart(theta/180.*math.pi, phi/180.*math.pi))
			self.assertAlmostEqual(theta, thetaObs/math.pi*180)
			self.assertAlmostEqual(phi, phiObs/math.pi*180)

	def testArtificialRotation(self):
		transMat = sphermath.computeTransMatrixFromPole((0, math.pi/4), 
			(0, -math.pi/4))
		def trans(t, p):
			a, b = sphermath.cartToSpher(numarray.dot(transMat,
				sphermath.spherToCart(t*DEG, p*DEG)))
			return a/DEG, b/DEG
		for t, p, a0, b0 in [
			(0, 90, 180, 45),
			(90, 0, 90, 0),
			(270, 0, 270, 0),
			(45, 45, 106.32494993689, 58.60028519008), # XXX think about this
		]:
			a, b = trans(t, p)
			self.assertAlmostEqual(a0, a)
			self.assertAlmostEqual(b0, b)


class ToGalacticTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	_toSystem = stc.parseSTCS("Position J2000")

	def _runTest(self, sample):
		fromCoo, (ares, dres) = sample
		ast = stc.parseSTCS("Position GALACTIC %f %f"%fromCoo)
		uv = numarray.dot(spherc._b1950ToGalMatrix, sphermath.spherToUV(ast))
		res = sphermath.uvToSpher(uv, self._toSystem)
		a, d = res.place.value
		self.assertAlmostEqual(ares, a, places=6)
		self.assertAlmostEqual(dres, d, places=6)
	
	samples = [
		((265.6108440311, -28.9167903484), (0,0)),
		((129.5660460691, -19.7089490512), (243.78, 13.2)),
	]


class JulianTestBase(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		(ra, dec), (ra1, dec1) = sample
		ast = self.srcSystem.change(
			place=self.srcSystem.place.change(value=(ra,dec)))
		res = spherc.conformSpherical(ast, self.destSystem)
		self.assertAlmostEqual(res.place.value[0], ra1)
		self.assertAlmostEqual(res.place.value[1], dec1)


# This mess creates tests from the samples in stcgroundtruth;
# see the globals in there; the tests are called Test<varname>
for sampleName in dir(stcgroundtruth):
	if not re.match("[a-zA-Z]", sampleName):
		continue
	_samples, _srcSystemSTC, _destSystemSTC = getattr(stcgroundtruth, sampleName)
	class GroundTruthTest(JulianTestBase):
		samples = _samples
		destSystem = stc.parseSTCS(_destSystemSTC)
		srcSystem = stc.parseSTCS(_srcSystemSTC)
	globals()["Test"+sampleName] = GroundTruthTest
	GroundTruthTest.__name__= "Test"+sampleName
	del GroundTruthTest



if __name__=="__main__":
	testhelpers.main(TestGalToJ2000)
