"""
Tests for the calculations with various spherical coordinate systems.
"""

import datetime
import math
import re

import numarray

from gavo import stc
from gavo import utils
from gavo.stc import common
from gavo.stc import conform
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


class SixVectorTest(testhelpers.VerboseTest):
	"""tests for working spherical-to-six-vector full transforms.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	
	posSamples = [
		((0,0), ('deg', 'deg')),
		((180,0), ('deg', 'deg')),
		((359.99,0), ('deg', 'deg')),
		((40,22), ('deg', 'deg')),
		((163,-52), ('deg', 'deg')),
		((253,-82), ('deg', 'deg')),
		((0,90), ('deg', 'deg')),
		((0,-90), ('deg', 'deg')),
		((2,10), ('rad', 'deg')),
		((2,10,5), ('rad', 'deg', 'arcsec')),
		((4,-10,5), ('rad', 'deg', 'pc')),
	]

	samples = [posSamp+velSamp
			for posSamp in posSamples
		for velSamp in [
			(None, None, None),
			((0, 0), ("arcsec", "arcsec"), ("yr", "yr")),
			((0.1, 0.1), ("arcsec", "arcsec"), ("yr", "yr")),
			((0.1, -0.1), ("rad", "arcsec"), ("cy", "yr")),
			((-0.1, 0.1), ("rad", "rad"), ("cy", "cy")),
			((0.1, -0.1), ("rad", "rad"), ("cy", "cy")),
			((1, 1, 9), ("rad", "rad", "km"), ("cy", "cy", "s")),
			((1, 1, 0.01), ("rad", "rad", "pc"), ("cy", "cy", "cy"))]]

	def assertAlmostEqualST(self, pos1, pos2, vel1, vel2):
		try:
			self.assertEqual(len(pos1), len(pos2))
			for v1, v2 in zip(pos1, pos2):
				self.assertAlmostEqual(v1, v2)
			if vel1 is None:
				self.assertEqual(vel2, None)
			else:
				self.assertEqual(len(vel1), len(vel2))
				for v1, v2 in zip(vel1, vel2):  # Numerical issues in RV -- fix?
					self.assertAlmostEqual(v1, v2, places=4)
		except AssertionError:
			raise AssertionError("%s, %s != %s, %s"%(pos1, vel1, pos2, vel2))

	def _runTest(self, sample):
		pos, posUnit, vel, velUnitS, velUnitT = sample
		trans = sphermath.SVConverter(pos, posUnit, vel, velUnitS, velUnitT)
		newPos, newVel = trans.from6(trans.to6(pos, vel))
		self.assertAlmostEqualST(pos, newPos, vel, newVel)



class SpherMathTest(testhelpers.VerboseTest):
	"""tests for some basic functionality of sphermath.
	"""
	trans = sphermath.SVConverter((0,0), ('deg', 'deg'))

	def testRotateY(self):
		sv = self.trans.to6((0,10))
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotY(angle*utils.DEG))
			pos, _ = self.trans.from6(numarray.dot(matrix, sv))
			self.assertAlmostEqual(pos[1], (10+angle))

	def testRotateX(self):
		sv = self.trans.to6((270,10))
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotX(angle*utils.DEG))
			pos, _ = self.trans.from6(numarray.dot(matrix, sv))
			self.assertAlmostEqual(pos[1], (10+angle))

	def testRotateZ(self):
		sv = self.trans.to6((10,0))
		for angle in range(10):
			matrix = spherc.threeToSix(sphermath.getRotZ(angle*utils.DEG))
			pos, _  = self.trans.from6(numarray.dot(matrix, sv))
			self.assertAlmostEqual(pos[0], (10-angle))

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
		ast = stc.parseSTCS("Position GALACTIC %.11f %.11f"%fromCoo)
		st = sphermath.SVConverter.fromSTC(ast)
		sv = st.to6(ast.place.value)
		sv = numarray.dot(spherc._b1950ToGalMatrix, sv)
		pos, vel = st.from6(sv)
		a, d = pos
		self.assertAlmostEqual(ares, a, places=6)
		self.assertAlmostEqual(dres, d, places=6)
	
	samples = [
		((265.6108440311, -28.9167903484), (0,0)),
		((129.5660460691, -19.7089490512), (243.78, 13.2)),
	]


class PositionOnlyTestBase(testhelpers.VerboseTest):
	"""A base class for makestctruth-based tests involving positions only.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		(ra, dec), (ra1, dec1) = sample
		ast = self.srcSystem.change(
			place=self.srcSystem.place.change(value=(ra,dec)))
		res = stc.conformTo(ast, self.destSystem)
		self.assertAlmostEqual(res.place.value[0], ra1)
		self.assertAlmostEqual(res.place.value[1], dec1)


class SixVectorTestBase(testhelpers.VerboseTest):
	"""A base class for makestctruth-based tests involving full 6-vectors.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		(ra, dec, prl, pma, pmd, rv
			), (ra1, dec1, prl1, pma1, pmd1, rv1) = sample
		ast = self.srcSystem.change(
			place=self.srcSystem.place.change(value=(ra,dec,prl)),
			velocity=self.srcSystem.velocity.change(value=(pma, pmd, rv)))
		res = stc.conformTo(ast, self.destSystem, slaComp=True)
		places = 6
		self.assertAlmostEqual(res.place.value[0], ra1, places=places)
		self.assertAlmostEqual(res.place.value[1], dec1, places=places)
		self.assertAlmostEqual(res.place.value[2], prl1, places=places)
		self.assertAlmostEqual(res.velocity.value[0], pma1, places=places-3)
		self.assertAlmostEqual(res.velocity.value[1], pmd1, places=places-3)
		self.assertAlmostEqual(res.velocity.value[2], rv1, places=places-3)


# This mess creates tests from the samples in stcgroundtruth;
# see the globals in there; the tests are called Test<varname>
for sampleName in dir(stcgroundtruth):
	if not re.match("[a-zA-Z]", sampleName):
		continue
	_samples, _srcSystemSTC, _destSystemSTC = getattr(stcgroundtruth, sampleName)
	if sampleName.startswith("Six"):
		base = SixVectorTestBase
	else:
		base = PositionOnlyTestBase
	class GroundTruthTest(base):
		samples = _samples
		destSystem = stc.parseSTCS(_destSystemSTC)
		srcSystem = stc.parseSTCS(_srcSystemSTC)
	globals()["Test"+sampleName] = GroundTruthTest
	GroundTruthTest.__name__= "Test"+sampleName
	del GroundTruthTest
	del base


if __name__=="__main__":
	testhelpers.main(SpherMathTest)
