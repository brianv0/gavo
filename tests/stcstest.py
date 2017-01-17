"""
Tests for STC-S handling.

STC-S to AST tests are in stctest.py.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import os
import unittest

from gavo.helpers import testhelpers

from gavo import stc
from gavo.stc import dm
from gavo.stc import stcs
from gavo.stc import stcsgen
from gavo.stc import syslib



class STCSParsesTestBase(testhelpers.VerboseTest):
	"""an abstract base for STCS parse tests asserting valid expressions.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	syms = stcs.getSymbols()

	def _runTest(self, args):
		sym, literal = args
		try:
			self.syms[sym].parseString(literal, parseAll=True)
		except stcs.ParseException:
			raise AssertionError("'%s' didn't parse but should have"%literal)


class STCSFailsTestBase(testhelpers.VerboseTest):
	"""an abstract base for STCS parse tests asserting invalid expressions.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	syms = stcs.getSymbols()

	def _runTest(self, args):
		sym, literal = args
		self.assertRaisesVerbose((stcs.ParseException, stcs.ParseSyntaxException),
			self.syms[sym].parseString,
			(literal, True), "No exception when parsing '%s' with %s"%
			(literal, sym))


class STCSTimeParsesTest(STCSParsesTestBase):
	"""Tests for parsing of time sub-phrases.
	"""
	samples = [
			("jdLiteral", "JD2569903.78"),
			("jdLiteral", "JD 2569403.78"),
			("mjdLiteral", "MJD2503.78"),
			("isoTimeLiteral", "1980-10-10"),
			("isoTimeLiteral", "1980-10-10T12:12:15"),
			("isoTimeLiteral", "1980-10-10T12:12:15Z"),
			("timeInterval", "TimeInterval"),
			("timeInterval", "TimeInterval 1900-01-01"),
			("timeInterval", "TimeInterval 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval 1900-01-01 2000-01-01"
				" 2001-01-10 2002-03-12"),
			("timeInterval", "TimeInterval 1900-01-01T12:30:14Z 2000-01-01T14:30:21"),
			("timeInterval", "TimeInterval TT 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval GEOCENTER 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval TT GEOCENTER 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval fillfactor 0.1 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval fillfactor 1e-9 1900-01-01 2000-01-01"),
			("timeInterval", "TimeInterval 1900-01-01 2000-01-01"
				" Time 1920-01-20T05:03:20Z"),
			("timeInterval", "TimeInterval 1900-01-01 2000-01-01 unit s"),
			("startTime", "StartTime 1900-01-01 unit s"),
			("startTime", "StartTime fillfactor 0.1 1900-01-01 unit yr"),
			("stopTime", "StopTime 1900-01-01 unit s"),
			("stopTime", "StopTime fillfactor 0.1 1900-01-01 unit yr"),
			("stopTime", "StopTime 1900-01-01 unit yr Error 19"),
			("stopTime", "StopTime 1900-01-01 unit yr Error 19 20"),
			("stopTime", "StopTime 1900-01-01 unit yr Resolution 19"),
			("stopTime", "StopTime 1900-01-01 unit yr Resolution 19 20"),
			("stopTime", "StopTime 1900-01-01 unit yr PixSize 19"),
			("stopTime", "StopTime 1900-01-01 unit yr Size 19"),
			("stopTime", "StopTime 1900-01-01 unit yr PixSize 19 20"),
			("stopTime", "StopTime fillfactor 0.1 TT GEOCENTER 1900-01-01"
				" Time 2000-12-31 unit yr Error 1 2 Resolution 0.1 0.1 PixSize 19 20"),
			]


class STCSTimeFails(STCSFailsTestBase):
	"""Tests for failing on invalid time sub-phrases.
	"""
	samples = [
			("timeInterval", "TimeInterval unit s fillfactor 0.1"),
			("timeInterval", "TimeInterval fillfactor 0.1 foobar"),
			("timeInterval", "fillfactor 0.1 foobar"),
			("timeInterval", "TimeInterval 0.2 0.2"),
			("jdLiteral", "0.2"),
			("jdLiteral", "JD x20"),
			("isoTimeLiteral", "JD"),
			("isoTimeLiteral", "30x50"),
			("startTime", "startTime 1900-01-01 2000-01-01 unit s")]


class STCSSpaceParsesTest(STCSParsesTestBase):
	samples = [
		("velocityUnit", "unit kpc/a"),
		("velocityUnit", "unit kpc/a m/s"),
		("positionInterval", "PositionInterval ICRS"),
		("positionInterval", "PositionInterval ICRS 12 12"),
		("positionInterval", "PositionInterval ICRS 12 11 10 9 8 7 6 5 4 3 2 1"),
		("positionInterval", "PositionInterval ICRS 12 11 unit m Error 10 10"
			" Resolution 12 Size 2 PixSize 14 14"),
		("atomicGeometry", "AllSky ICRS"),
		("atomicGeometry", "Circle FK4 B1975.0 1 2 3"),
		("atomicGeometry", "Circle FK4 J1975.0 1 2 3"),
		("atomicGeometry", "Circle fillfactor 0.1 FK4 TOPOCENTER SPHER2 1 2 3"
			" unit deg Error 3 3 Size 23"),
		("atomicGeometry", "Ellipse J2000 unit deg"),
		("atomicGeometry", "Box GALACTIC 12 12 10 20 unit deg"),
		("atomicGeometry", "Polygon GALACTIC_II 12 12 10 20 21 21 20 19"),
		("atomicGeometry", "Convex GEO_C 12 12 10 20 21 21 20 19"),
		("position", "Position UNKNOWNFrame 12 13 Error 0.1 0.1"),
		("position", "Position UNKNOWNFrame Epoch J1992.5 12 13 Error 0.1 0.1"
			" VelocityInterval fillfactor 0.125 1 1.5 2 3 Error 0.25 0.5"
			" Resolution 0.25 0.25 PixSize 0.5 0.75"),
		("position", "Position ICRS TOPOCENTER JPL-DE200"),
	]


class STCSSpaceFailsTest(STCSFailsTestBase):
	samples = [
		("positionInterval", "PositionInterval"),
		("positionInterval", "PositionInterval 12 12"),
		("positionInterval", "PositionInterval 12 12 Error x"),
		("positionInterval", "PositionInterval 12 12 Error 5 unit m"),
		("positionInterval", "PositionInterval 12 12 unit s"),
		("positionInterval", "PositionInterval 12 12 unit 14"),
		("atomicGeometry", "Circle FK4 fillfactor 0.1"),
		("atomicGeometry", "Elipse J2000 unit deg Error 3 3 Size 23"),
		("atomicGeometry", "Ellipse J200 unit deg Error 3 3 Size 23"),
		("spaceSubPhrase", "Ellipse Box J2000"),
	]


class STCSRedshiftParsesTest(STCSParsesTestBase):
	samples = [
		("redshiftSubPhrase", "Redshift TOPOCENTER VELOCITY RELATIVISTIC 0.1"
			" unit km/s Error 10 12 Resolution 1 2 Size 3 PixSize 4 5"),
		("redshiftSubPhrase", "RedshiftInterval fillfactor 0.4"
			" BARYCENTER REDSHIFT"),
		("redshiftSubPhrase", "RedshiftInterval fillfactor 0.4"
			" BARYCENTER REDSHIFT 12 13 Redshift 11.3"),
	]


class STCSRedshiftFailsTest(STCSFailsTestBase):
	samples = [
		("redshiftSubPhrase", "Redshift GEOCENTER 0.1 unit mm"),
		("redshiftSubPhrase", "Redshift TOPOCENTER 0.1 RELATIVISTIC VELOCITY"),
	]


class STCSSpectralParsesTest(STCSParsesTestBase):
	samples = [
		("spectralSubPhrase", "Spectral 12 unit mm"),
		("spectralSubPhrase", "Spectral 12 unit mm Size 3"),
		("spectralSubPhrase", "Spectral NEPTUNE 12 unit mm"),
		("spectralSubPhrase", "Spectral UNKNOWNRefPos 12 unit Angstrom Error 4 3"
			" Resolution 0.2 PixSize 12"),
		("spectralSubPhrase", "SpectralInterval HELIOCENTER 12 13 Spectral 12.2"
			" unit nm Error 4 Resolution 0.2 PixSize 12"),
	]


class STCSSpectralFailsTest(STCSFailsTestBase):
	samples = [
		("spectralSubPhrase", "Spectral ab"),
		("spectralSubPhrase", "Spectral 1e10 unit pc"),
		("spectralSubPhrase", "SpectralInterval ICRS 1e10 unit Angstrom"),
	]


class STCSCompoundParsesTest(STCSParsesTestBase):
	samples = [
		("compoundGeoPhrase", 
			"Union ICRS (Circle 10 12 1 Circle 11 11 1)"),
		("compoundGeoPhrase", 
			"Union ICRS (Circle 10 12 1 Not (Circle 11 11 1))"),
		("compoundGeoPhrase", 
			"Union ICRS (Circle 10 12 1 Union (Not (Circle 11 11 1) Box 12 22 1 2))"),
		("compoundGeoPhrase", 
			"Intersection ICRS (Circle 10 12 1 Union (Not (Circle 11 11 1)"
				" Box 12 22 1 2))"),
		("compoundGeoPhrase", 
			"Difference ICRS (Circle 10 12 1 Intersection (Not (Circle 11 11 1)"
				" Box 12 22 1 2))"),
# 5
		("compoundGeoPhrase", 
			"Union ICRS (Circle 10 12 1"
			" Not (Intersection( Circle 11 11 1 Box 12 22 1 2)))"),
		("compoundGeoPhrase", 
			"Union ICRS (Circle 10 12 1"
			" Not (Intersection (Circle 11 11 1 Not (Union (Box 12 22 1 2"
			" Ellipse 1 2 3 4 5)))))"),
		("compoundGeoPhrase",
			"Union Galactic (PositionInterval 10 12 20 14"
			"  PositionInterval 20 12 20 24)"),
	]


class STCSCompoundFailsTest(STCSFailsTestBase):
	samples = [
		("compoundGeoPhrase", 
			"Not (Union ICRS (Circle 10 12 1 Circle 11 11 1))"),
		("compoundGeoPhrase", 
			"Union ICRS (Position 12 13 Circle 10 12 1 Circle 11 11 1)"),
		("compoundGeoPhrase", 
			"Difference ICRS (Circle 10 12 1 Not Circle 11 11 1 Box 12 22 1 2)"),
		("compoundGeoPhrase", 
			"Union ICRS"),
	]


class STCSSpectralParsesTest(STCSParsesTestBase):
	samples = [
		("spectralSubPhrase", "Spectral 12 unit mm"),
		("spectralSubPhrase", "Spectral NEPTUNE 12 unit mm"),
		("spectralSubPhrase", "Spectral UNKNOWNRefPos 12 unit Angstrom Error 4 3"
			" Resolution 0.2 PixSize 12"),
		("spectralSubPhrase", "SpectralInterval HELIOCENTER 12 13 Spectral 12.2"
			" unit nm Error 4 Resolution 0.2 PixSize 12"),
	]


class STCSSpectralFailsTest(STCSFailsTestBase):
	samples = [
		("spectralSubPhrase", "Spectral ab"),
		("spectralSubPhrase", "Spectral 1e10 unit pc"),
		("spectralSubPhrase", "SpectralInterval ICRS 1e10 unit Angstrom"),
	]


class STCSTreeParseTestBase(testhelpers.VerboseTest):
	"""A base for parse tests checking the concrete syntax trees.

	Fill out the samples class variable with tuples of 
	(symbolName, inputString, resultTree)
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	syms = stcs.getSymbols()
	samples = []

	def _runTest(self, sample):
		symbolName, inputString, resultTree = sample
		try:
			self.assertEqual(stcs.makeTree(self.syms[symbolName].parseString(
				inputString, parseAll=True)), resultTree)
		except stcs.ParseException:
			raise AssertionError(
				"Sample '%s' with expected result %s didn't parse"%(
					inputString, resultTree))


class SimpleSTCSTreesTest(STCSTreeParseTestBase):
	samples = [
		("timeUnit", "unit s", {'unit': 's'}),
		("spaceUnit", "unit pc", {"unit": 'pc'}),
		("spaceUnit", "unit pc kpc m", {"unit": 'pc kpc m'}),
		("velocityUnit", "unit pc/cy km/s", {"unit": 'pc/cy km/s'}),
		("positionSpec", "Position 2 1 3.5 7e9", {"pos": [2., 1., 3.5, 7e9]}),
		("timescale", "TT", {'timescale': 'TT'}),
		("jdLiteral", "JD 2450000.5", [datetime.datetime(
			1995, 10, 9, 23, 59, 59, 999997)]),
		("redshiftType", "VELOCITY", {'redshiftType': 'VELOCITY'}),
		("frame", "FK4 B1940.5", {'frame': 'FK4', 'equinox': 'B1940.5'}),
		("systemDefinition", "System TT-ICRS-TOPO", 
			{'libSystem': 'TT-ICRS-TOPO'}),
	]


class ComplexSTCSTreesTest(STCSTreeParseTestBase):
	samples = [
		("positionInterval", "PositionInterval ICRS Epoch J2003.4 2 3", 
			{'coos': [2., 3.], 'frame': 'ICRS', 'type': 'PositionInterval',
			'epoch': 'J2003.4'}),
		("positionInterval", "PositionInterval ICRS 2 3 Error 5 7", 
			{'coos': [2., 3.], 'frame': 'ICRS', 'type': 'PositionInterval',
				'error': [5., 7.]}),
		("timeInterval", "TimeInterval 1980-10-15 JD 2454930.7", 
			{'coos': [datetime.datetime(1980, 10, 15, 0, 0), 
				datetime.datetime(2009, 4, 9, 4, 48, 0, 18)], 'type': 'TimeInterval'}),
		("stopTime", "StopTime fillfactor 0.1 TT GEOCENTER 1900-01-01"
				" Time 2000-12-31 unit yr Error 1 2 Resolution 0.5 0.5 PixSize 19 20",
			{'fillfactor': 0.1, 'timescale': 'TT', 'type': 'StopTime', 
				'refpos': 'GEOCENTER', 'coos': [datetime.datetime(1900, 1, 1, 0, 0)],
				'pos': [datetime.datetime(2000, 12, 31, 0, 0)], 
				'error': [1., 2.], 'resolution': [0.5, 0.5], 'unit': 'yr', 
				'pixSize': [19., 20.]}),
		("spaceSubPhrase", "Circle fillfactor 0.1 FK4 TOPOCENTER SPHER2 1 2 3"
			" unit deg Error 3 3 Size 23", [{'coos': [1., 2., 3.], 
				'frame': 'FK4', 'refpos': 'TOPOCENTER', 'fillfactor': 0.1, 
				'error': [3., 3.], 'flavor': 'SPHER2', 'type': 'Circle', 
				'unit': 'deg', 'size': [23.]}]),
		("spaceSubPhrase", "PositionInterval FK4 VelocityInterval fillfactor 0.25"
				" 12 13"
				" Velocity 12.5 unit km/s Error 4 5 Resolution 1.25 PixSize 1.5", 
			[{'frame': 'FK4', 'type': 'PositionInterval', 'velocity': [
				{'coos': [12., 13.], 'fillfactor': 0.25, 
				'error': [4., 5.], 'pos': [12.5], 'resolution': [1.25], 
				'unit': 'km/s', 'pixSize': [1.5], 'type': "Velocity"}]}]),
		("stcsPhrase", "Circle ICRS 2 23 12 RedshiftInterval RADIO 0.125 0.25", {
			'space': {
				'coos': [2., 23., 12.], 'frame': 'ICRS', 'type': 'Circle'}, 
			'redshift': {
				'coos': [0.125, 0.25], 'dopplerdef': 'RADIO', 
				'type': 'RedshiftInterval'}}),
	]


class STCSPhraseTest(STCSTreeParseTestBase):
	samples = [
		("stcsPhrase", "StopTime TT 2009-03-10T09:56:10.015625",
			{'time': {'coos': [datetime.datetime(2009, 3, 10, 9, 56, 10, 15625)], 
				'type': 'StopTime', 'timescale': 'TT'}}),
		("stcsPhrase", "AllSky FK4 B1975.0 Epoch J1970.0 Position 12 13",
			{'space': {'type': 'AllSky', 'frame': 'FK4', 'equinox': 'B1975.0', 
				'pos': [12., 13.], 'epoch': 'J1970.0'}}),
		("stcsPhrase", "Spectral BARYCENTER 200000 unit Hz PixSize 1",
			{'spectral': {'type': 'Spectral', 'pos': [200000.], 
				"refpos": "BARYCENTER", "unit": "Hz", "pixSize": [1.0]}}),
		("stcsPhrase", "Time TT 2008-05-05T12:33:45",
			{'time': {'type': 'Time', 'pos': 
				[datetime.datetime(2008, 5, 5, 12, 33, 45)], 'timescale': 'TT'}}),
		("stcsPhrase", "AllSky ICRS",
			{'space': {'type': 'AllSky', 'frame': 'ICRS'}}),
		("stcsPhrase", "Position ECLIPTIC System TT-ICRS-TOPO",
			{'libSystem': 'TT-ICRS-TOPO', 'space': 
				{'frame': 'ECLIPTIC', 'type': 'Position'}}),
		("stcsPhrase", 'Position ICRS Epoch J2000.0 \n 20 21',
			{'space': {
					'frame': 'ICRS', 
					'type': 'Position', 
					'epoch': 'J2000.0', 
					'pos': [20.0, 21.0]}}),
	]


class TreeIterTest(testhelpers.VerboseTest):
	"""tests for sensible traversal of STCS CSTs.
	"""
	syms = stcs.getSymbols()

	def _getTree(self, inputString):
		return stcs.makeTree(self.syms["stcsPhrase"].parseString(
			inputString, parseAll=True))
	
	def testSimple(self):
		self.assertEqual(list(stcs.iterNodes(self._getTree("Position ICRS 2 3"))),
			[(('space',), {'pos': [2.0, 3.0], 
				'frame': 'ICRS', 'type': 'Position'}), 
			((), {'space': {'pos': [2.0, 3.0], 
				'frame': 'ICRS', 'type': 'Position'}})])
	
	def testComplex(self):
		self.assertEqual(list(stcs.iterNodes(self._getTree(
			"Circle ICRS 2 23 12 VelocityInterval fillfactor 0.5 12 13"
		  " RedshiftInterval RADIO 0.125 0.25"))), [
				(('space', 'velocity'),
				  {'coos': [12.0, 13.0], 'fillfactor': 0.5, 
						'type': 'VelocityInterval'}),
				(('space',), {
					'coos': [2.0, 23.0, 12.0], 'frame': 'ICRS', 'type': 'Circle', 
					'velocity': [
						{'coos': [12.0, 13.0], 'fillfactor': 0.5, 
							'type': 'VelocityInterval'}]}), 
				(('redshift',), {
						'coos': [0.125, 0.25], 'dopplerdef': 'RADIO', 
							'type': 'RedshiftInterval'}), 
				((), {'space': {'coos': [2.0, 23.0, 12.0], 'frame': 'ICRS', 
					'type': 'Circle', 'velocity': [{'coos': [12., 13.], 
					'fillfactor': 0.5, 'type': 'VelocityInterval'}]}, 
					'redshift': {'coos': [0.125, 0.25], 
					'dopplerdef': 'RADIO', 'type': 'RedshiftInterval'}})])


class DefaultingTest(testhelpers.VerboseTest):
	def testPositionInterval(self):
		self.assertEqual(stcs.getCST("PositionInterval ICRS"),
			{'space': {'frame': 'ICRS', 'unit': 'deg', 'type': 'PositionInterval', 
			'flavor': 'SPHER2'}})
	
	def testSpatialWithVelInterval(self):
		self.assertEqual(stcs.getCST("PositionInterval ICRS VelocityInterval"
			" Velocity 1 2"),
			{'space': {'frame': 'ICRS', 'unit': 'deg', 'type': 'PositionInterval', 
			'flavor': 'SPHER2',
			'velocity': [{'pos': [1.0, 2.0], 'unit': 'm/s', 
				'type': 'Velocity'}]}})

	def testWithUnit(self):
		self.assertEqual(stcs.getCST("PositionInterval ICRS unit arcsec"),
			{'space': {'frame': 'ICRS', 'unit': 'arcsec', 
			'type': 'PositionInterval',
			'flavor': 'SPHER2'}})

	def testConvex(self):
		self.assertEqual(stcs.getCST("Convex ICRS"),
			{'space': {'frame': 'ICRS', 'unit': '', 'type': 'Convex', 
			'flavor': 'UNITSPHER'}})

	def testCart2(self):
		self.assertEqual(stcs.getCST("PositionInterval FK4 TOPOCENTER CART2"),
			{'space': {'frame': 'FK4', 'unit': 'm', 'type': 'PositionInterval', 
			'refpos': 'TOPOCENTER', 'flavor': 'CART2', "equinox": 'B1950.0'}})

	def testGeoC(self):
		self.assertEqual(stcs.getCST("PositionInterval GEO_C"),
			{'space': {'frame': 'GEO_C', 'unit': 'deg deg m', 
				'type': 'PositionInterval', 'flavor': 'SPHER2'}})

	def testTemporal(self):
		self.assertEqual(stcs.getCST("TimeInterval"), {'time': {'unit': 's', 
			'type': 'TimeInterval'}})

	def testSpectral(self):
		self.assertEqual(stcs.getCST("SpectralInterval"), {'spectral': 
			{'type': 'SpectralInterval', 'unit': 'Hz'}})

	def testRedshift(self):
		self.assertEqual(stcs.getCST("RedshiftInterval"),
			{'redshift': {'redshiftType': 'REDSHIFT', 'type': 'RedshiftInterval', 
			'unit': 'nil', 'dopplerdef': 'OPTICAL'}})


def assertMapsto(stcsInput, expectedOutput):
	ast = stc.parseSTCS(stcsInput)
	foundOutput = stcsgen.getSTCS(ast)
	if foundOutput!=expectedOutput:
		matchLen = len(os.path.commonprefix([expectedOutput, foundOutput]))
		raise AssertionError("Didn't get expected STC-S for example '%s';"
			" non-matching part: '%s'"%(stcsInput, foundOutput[matchLen:]))


class GeneralGenerationTest(testhelpers.VerboseTest):
	"""tests for STCS-STCS-round trips.
	"""
	def testEmpty(self):
		assertMapsto('', '')

	def testTimeCoo(self):
		assertMapsto("Time TT 2009-03-10T09:56:10.015625 unit s"
			" Error 0.0001 0.0002 Resolution 0.0001 PixSize 2",
			'Time TT 2009-03-10T09:56:10.015625 Error 0.0001 0.0002 Resolution 0.0001 PixSize 2.0')
	
	def testTimeInterval(self):
		assertMapsto("TimeInterval TAI MJD52000.5 MJD52011.5",
			'TimeInterval TAI 2001-04-01T12:00:00 2001-04-12T12:00:00')
	
	def testTimeHalfInterval(self):
		assertMapsto("StopTime TT 2009-03-10T09:56:10.015625",
			'StopTime TT 2009-03-10T09:56:10.015625')
	
	def testTimeIntervalWithValue(self):
		assertMapsto("TimeInterval TAI MJD52000.5 MJD52011.5"
			" Time 2001-04-01T18:23:50",
			'TimeInterval TAI 2001-04-01T12:00:00 2001-04-12T12:00:00 Time 2001-04-01T18:23:50'),
	
	def testOtherIntervals(self):
		assertMapsto("SpectralInterval 20 30 unit m"
			" RedshiftInterval VELOCITY 1 2 Error 0 0.125",
			'SpectralInterval 20.0 30.0 unit m\nRedshiftInterval VELOCITY 1.0 2.0 Error 0.0 0.125')
	
	def testOtherCoodinates(self):
		assertMapsto("Spectral BARYCENTER 200000 unit Hz PixSize 1"
			" Redshift TOPOCENTER REDSHIFT RELATIVISTIC 2",
			'Spectral BARYCENTER 200000.0 PixSize 1.0\n'
			'Redshift TOPOCENTER RELATIVISTIC 2.0')

	def testSpatialCoo(self):
		assertMapsto("Position ICRS -50 320",
			'Position ICRS -50.0 320.0')

	def testComplexSpatialCoo(self):
		assertMapsto("Position ICRS UNKNOWNRefPos CART3 -50 320 20 unit pc"
			" Error 1 2 3 1.25 2.25 3.25 Resolution 0.125 0.125 0.125"
			" Size 4 3 2",
			'Position ICRS CART3 -50.0 320.0 20.0 unit pc Error 1.0 2.0 3.0 1.25 2.25 3.25 Resolution 0.125 0.125 0.125 Size 4.0 3.0 2.0')
	
	def testSpatialInterval(self):
		assertMapsto('PositionInterval J2000 Epoch J2010.2 12 13 19 29'
			' Position 15 16',
			'PositionInterval FK5 Epoch J2010.2 12.0 13.0 19.0 29.0'
			' Position 15.0 16.0')

	def testSystem(self):
		assertMapsto('Position FK5 J2010 15 16 System TT-ICRS-TOPO',
			"Position ICRS TOPOCENTER 15.0 16.0\nSystem TT-ICRS-TOPO")


class SampleGenerationTestBase(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	samples = []
	def _runTest(self, sample):
		assertMapsto(*sample)


class BaseGenerationTest(SampleGenerationTestBase):
	samples = [
		("Redshift BARYCENTER JPL-DE405 3.5",
			"Redshift BARYCENTER JPL-DE405 3.5"),]


class GeometriesGenerationTest(SampleGenerationTestBase):
	samples = [
		("AllSky ICRS", "AllSky ICRS"),
		("AllSky FK5 J2010 Position 12 13",
			'AllSky FK5 J2010.0 Position 12.0 13.0'),
		("Circle ICRS 12 13 0.25 Position 12.5 13.5",
			'Circle ICRS 12.0 13.0 0.25 Position 12.5 13.5'),
		("Ellipse ECLIPTIC TOPOCENTER -40 38 0.75 0.5 45"
			" PixSize 0.25 0.25 0.5 0.5",
			'Ellipse ECLIPTIC TOPOCENTER -40.0 38.0 0.75 0.5 45.0'
			' PixSize 0.25 0.25 0.5 0.5'),
		("Box ICRS 32 24 1 2",
			"Box ICRS 32.0 24.0 1.0 2.0"),
		("Polygon UNKNOWNFrame CART2 1 2 3 4 5 6 Size 3 4",
			'Polygon UNKNOWNFrame CART2 1.0 2.0 3.0 4.0 5.0 6.0 Size 3.0 4.0'),
		("Convex GEO_C 2 3 4 0.5 5 6 7 0.25",
			'Convex GEO_C 2.0 3.0 4.0 0.5 5.0 6.0 7.0 0.25'),
	]


class CompoundGenerationTest(SampleGenerationTestBase):
	samples = [
		("Union FK5 (Box 12 -13 2 2 Circle 14 -13.5 3)", 
			'Union FK5 (Box 12.0 -13.0 2.0 2.0 Circle 14.0 -13.5 3.0)'),
		("Not FK5 (Circle 14 14 3)",
			'Not FK5 (Circle 14.0 14.0 3.0)'),
		("Union FK5 (Box 12 -13 2 2 Not (Circle 14 -13.5 3))", 
			'Union FK5 (Box 12.0 -13.0 2.0 2.0 Not (Circle 14.0 -13.5 3.0))'),
		("Intersection GALACTIC (Polygon 12 13 14 15 16 17 Union (Circle 340 -30 3"
			" Not (Circle 341 -32 2)))",
			'Intersection GALACTIC (Polygon 12.0 13.0 14.0 15.0 16.0 17.0 Union'
			' (Circle 340.0 -30.0 3.0 Not (Circle 341.0 -32.0 2.0)))'),
		("Difference GALACTIC (Polygon 12 13 14 15 16 17"
			" Not (Intersection (Circle 340 -30 3 Circle 341 -32 2)))",
			'Difference GALACTIC (Polygon 12.0 13.0 14.0 15.0 16.0 17.0 Not'
			' (Intersection (Circle 340.0 -30.0 3.0 Circle 341.0 -32.0 2.0)))'),
	]


class VelocitiesGenerationTest(SampleGenerationTestBase):
	samples = [
		("Position ICRS VelocityInterval 1 2",
			"Position ICRS VelocityInterval 1.0 2.0"),
		("Position ICRS VelocityInterval 1 2 Velocity 1.5 2.5",
			"Position ICRS VelocityInterval 1.0 2.0 Velocity 1.5 2.5"),
		("Position ICRS 12 13 VelocityInterval Velocity 1.5 2.5",
			"Position ICRS 12.0 13.0 Velocity 1.5 2.5"),
		("Position ICRS 12 13 Velocity 1.5 2.5",
			"Position ICRS 12.0 13.0 Velocity 1.5 2.5"),
		("Position ICRS VelocityInterval unit deg/s Error 0.125 0.125",
			"Position ICRS Velocity unit deg/s Error 0.125 0.125"),
		("Position ICRS Velocity 1 2 unit deg/s Error 0.125 0.125",
			"Position ICRS Velocity 1.0 2.0 unit deg/s Error 0.125 0.125"),
	]


class ColrefTest(testhelpers.VerboseTest):
	def testPosCol(self):
		tree = stc.parseQSTCS('Position ICRS "foo" "bar" Error "e_foo" "e_bar"')
		self.assertEqual(tree.place.value[0].dest, "foo")
		self.assertEqual(tree.place.error.values[0][0].dest, "e_foo")

	def testPosGeo(self):
		tree = stc.parseQSTCS('Position ICRS [pos]')
		self.assertEqual(tree.place.value.dest, "pos")

	def testErrorRadius(self):
		tree = stc.parseQSTCS('Position ICRS Error "p1" "p1"')
		self.assertEqual(tree.place.error.radii[0].dest, "p1")



class SyslibTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	samples = syslib.SYSDEFS

	def _runTest(self, sysId):
		self.assertRuns(syslib.getLibrarySystem, (sysId,),
			"Cannot build system %s"%sysId)


class SpatialSystemTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		stcsInput, expected = sample
		ast = stc.parseSTCS(stcsInput)
		self.assertEqual(stc.getSpatialSystem(ast), expected)

	samples = [
		("Position ICRS", "ICRS"),
		("Position FK4 B1875.0", "FK4 B1875.0"),
		("Time TT 2000-01-01 Circle GALACTIC GEOCENTER 10 10 2", 
			"GALACTIC GEOCENTER"),
	]


if __name__=="__main__":
	testhelpers.main(VelocitiesGenerationTest)
