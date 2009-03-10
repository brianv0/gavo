"""
Tests for STC-S handling
"""

import datetime
import unittest

from gavo import stc
from gavo.stc import dm
from gavo.stc import stcs

import testhelpers


class STCSParsesTestBase(testhelpers.VerboseTest):
	"""an abstract base for simple parse tests.

	Inherit from this for more simple parse test.  Fill out the shouldParse 
	and shouldNotParse class variables.
	"""
	syms = stcs.getSymbols()

	shouldParse, shouldNotParse = [], []

	def testParseTimeStuff(self):
		# We're only interested in stuff not raising ParseErrors here
		for sym, literal in self.shouldParse:
			try:
				self.syms[sym].parseString(literal, parseAll=True)
			except stcs.ParseException:
				raise AssertionError("'%s' didn't parse but should have"%literal)
	
	def testNoParseTimeStuff(self):
		for sym, literal in self.shouldNotParse:
			self.assertRaisesVerbose(stcs.ParseException, self.syms[sym].parseString,
				(literal, True), "No exception when parsing '%s' with %s"%
				(literal, sym))


class STCSTimeParsesTest(STCSParsesTestBase):
	"""Tests for parsing of time sub-phrases.
	"""
	shouldParse = [
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
			("stopTime", "StopTime 1900-01-01 unit yr PixSize 19 20"),
			("stopTime", "StopTime fillfactor 0.1 TT GEOCENTER 1900-01-01"
				" Time 2000-12-31 unit yr Error 1 2 Resolution 0.1 0.1 PixSize 19 20"),
			]

	shouldNotParse = [
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
	shouldParse = [
		("positionInterval", "PositionInterval ICRS"),
		("positionInterval", "PositionInterval ICRS 12 12"),
		("positionInterval", "PositionInterval ICRS 12 11 10 9 8 7 6 5 4 3 2 1"),
		("positionInterval", "PositionInterval ICRS 12 11 unit m Error 10 10"
			" Resolution 12 Size 2 PixSize 14 14"),
		("allSky", "AllSky ICRS"),
		("circle", "Circle fillfactor 0.1 FK4 TOPOCENTER SPHER2 1 2 3"
			" unit deg Error 3 3 Size 23"),
		("ellipse", "Ellipse J2000 unit deg"),
		("box", "Box GALACTIC 12 12 10 20 unit deg"),
		("polygon", "Polygon GALACTIC_II 12 12 10 20 21 21 20 19"),
		("convex", "Convex GEO_C 12 12 10 20 21 21 20 19"),
		("position", "Position UNKNOWNFrame 12 13 Error 0.1 0.1"),
	]
	shouldNotParse = [
		("positionInterval", "PositionInterval"),
		("positionInterval", "PositionInterval 12 12"),
		("positionInterval", "PositionInterval 12 12 Error x"),
		("positionInterval", "PositionInterval 12 12 Error 5 unit m"),
		("positionInterval", "PositionInterval 12 12 unit s"),
		("positionInterval", "PositionInterval 12 12 unit 14"),
		("circle", "Circle FK4 fillfactor 0.1"),
		("ellipse", "Elipse J2000 unit deg Error 3 3 Size 23"),
		("ellipse", "Ellipse J200 unit deg Error 3 3 Size 23"),
		("spaceSubPhrase", "Ellipse Box J2000"),
	]


class STCSRedshiftParsesTest(STCSParsesTestBase):
	shouldParse = [
		("redshiftSubPhrase", "Redshift TOPOCENTER 0.1 VELOCITY RELATIVISTIC"
			" unit km/s Error 10 12 Resolution 1 2 PixSize 4 5"),
		("redshiftSubPhrase", "RedshiftInterval fillfactor 0.4"
			" BARYCENTER REDSHIFT"),
		("redshiftSubPhrase", "RedshiftInterval fillfactor 0.4"
			" BARYCENTER REDSHIFT 12 13 Redshift 11.3"),
	]
	shouldNotParse = [
		("redshiftSubPhrase", "Redshift GEOCENTER 0.1 unit mm"),
		("redshiftSubPhrase", "Redshift TOPOCENTER 0.1 RELATIVISTIC VELOCITY"),
	]


class STCSSpectralParsesTest(STCSParsesTestBase):
	shouldParse = [
		("spectralSubPhrase", "Spectral 12 unit mm"),
		("spectralSubPhrase", "Spectral NEPTUNE 12 unit mm"),
		("spectralSubPhrase", "Spectral UNKNOWNRefPos 12 unit Angstrom Error 4 3"
			" Resolution 0.2 PixSize 12"),
		("spectralSubPhrase", "SpectralInterval HELIOCENTER 12 13 Spectral 12.2"
			" unit nm Error 4 Resolution 0.2 PixSize 12"),
	]
	shouldNotParse = [
		("spectralSubPhrase", "Spectral ab"),
		("spectralSubPhrase", "Spectral 1e10 unit pc"),
		("spectralSubPhrase", "SpectralInterval ICRS 1e10 unit Angstrom"),
	]


class STCSTreeParseTestBase(testhelpers.VerboseTest):
	"""A base for parse tests checking the concrete syntax trees.

	Fill out the samples class variable with tuples of 
	(symbolName, inputString, resultTree)
	"""
	syms = stcs.getSymbols()
	samples = []

	def testSamples(self):
		for symbolName, inputString, resultTree in self.samples:
			try:
				self.assertEqual(stcs.makeTree(self.syms[symbolName].parseString(
					inputString, parseAll=True)), resultTree)
			except stcs.ParseException:
				raise AssertionError(
					"Sample '%s' with expected result %s didn't parse"%(
						inputString, resultTree))


class TestSimpleSTCSTrees(STCSTreeParseTestBase):
	samples = [
		("timeUnit", "unit s", {'unit': 's'}),
		("spaceUnit", "unit pc", {"unit": 'pc'}),
		("positionSpec", "Position 2 1 3.4 7e9", ['2', '1', '3.4', '7e9']),
		("timescale", "TT", {'timescale': 'TT'}),
		("jdLiteral", "JD 2450000.5", [datetime.datetime(
			1995, 10, 9, 23, 59, 59, 999997)]),
		("redshiftType", "VELOCITY", {'redshiftType': 'VELOCITY'}),
	]


class TestComplexSTCSTrees(STCSTreeParseTestBase):
	samples = [
		("positionInterval", "PositionInterval ICRS 2 3", 
			{'coos': ['2', '3'], 'frame': 'ICRS', 'type': 'PositionInterval'}),
		("positionInterval", "PositionInterval ICRS 2 3 Error 5 7", 
			{'coos': ['2', '3'], 'frame': 'ICRS', 'type': 'PositionInterval',
				'error': ['5', '7']}),
		("timeInterval", "TimeInterval 1980-10-15 JD 2454930.7", 
			{'coos': [datetime.datetime(1980, 10, 15, 0, 0), 
				datetime.datetime(2009, 4, 9, 4, 48, 0, 18)], 'type': 'TimeInterval'}),
		("stopTime", "StopTime fillfactor 0.1 TT GEOCENTER 1900-01-01"
				" Time 2000-12-31 unit yr Error 1 2 Resolution 0.1 0.1 PixSize 19 20",
			{'fill_factor': ['0.1'], 'timescale': 'TT', 'type': 'StopTime', 
				'refpos': 'GEOCENTER', 'stopTime': datetime.datetime(1900, 1, 1, 0, 0),
				'pos': [datetime.datetime(2000, 12, 31, 0, 0)], 
				'error': ['1', '2'], 'resolution': ['0.1', '0.1'], 'unit': 'yr', 
				'pixSize': ['19', '20']}),
		("spaceSubPhrase", "Circle fillfactor 0.1 FK4 TOPOCENTER SPHER2 1 2 3"
			" unit deg Error 3 3 Size 23", [{'coos': ['1', '2', '3'], 
				'frame': 'FK4', 'refpos': 'TOPOCENTER', 'fillfactor': ['0.1'], 
				'error': ['3', '3'], 'flavor': 'SPHER2', 'type': 'Circle', 
				'unit': 'deg', 'size': ['23']}]),
		("spaceSubPhrase", "PositionInterval FK4 VelocityInterval fillfactor 0.1"
				" 12 13"
				" Velocity 12.3 unit km/s Error 4 5 Resolution 1.2 PixSize 1.3", 
			[{'frame': 'FK4', 'type': 'PositionInterval', 'velocityInterval': [
				{'coos': ['12', '13'], 'fillfactor': ['0.1'], 
				'error': ['4', '5'], 'velocity': ['12.3'], 'resolution': ['1.2'], 
				'unit': 'km/s', 'pixSize': ['1.3']}]}]),
		("stcsPhrase", "Circle ICRS 2 23 12 RedshiftInterval RADIO 0.1 0.2", {
			'space': {
				'coos': ['2', '23', '12'], 'frame': 'ICRS', 'type': 'Circle'}, 
			'redshift': {
				'coos': ['0.1', '0.2'], 'dopplerdef': 'RADIO', 
				'type': 'RedshiftInterval'}}),
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
			[(('space',), {'coos': ['2', '3'], 
				'frame': 'ICRS', 'type': 'Position'}), 
			((), {'space': {'coos': ['2', '3'], 
				'frame': 'ICRS', 'type': 'Position'}})])
	
	def testComplex(self):
		self.assertEqual(list(stcs.iterNodes(self._getTree(
			"Circle ICRS 2 23 12 VelocityInterval fillfactor 0.1 12 13"
		  " RedshiftInterval RADIO 0.1 0.2"))), [
				(('space', 'velocityInterval'), {
					'coos': ['12', '13'], 'fillfactor': ['0.1']}), 
				(('space',), {
					'coos': ['2', '23', '12'], 'frame': 'ICRS', 'type': 'Circle', 
					'velocityInterval': [
						{'coos': ['12', '13'], 'fillfactor': ['0.1']}]}), 
				(('redshift',), {
						'coos': ['0.1', '0.2'], 'dopplerdef': 'RADIO', 
							'type': 'RedshiftInterval'}), 
				((), {'space': {'coos': ['2', '23', '12'], 'frame': 'ICRS', 
					'type': 'Circle', 'velocityInterval': [{'coos': ['12', '13'], 
					'fillfactor': ['0.1']}]}, 'redshift': {'coos': ['0.1', '0.2'], 
					'dopplerdef': 'RADIO', 'type': 'RedshiftInterval'}})])


class DefaultingTest(testhelpers.VerboseTest):
	def testSpatial(self):
		self.assertEqual(stcs.getCST("PositionInterval ICRS"),
			{'space': {'frame': 'ICRS', 'unit': 'deg', 'type': 'PositionInterval', 
			'refpos': 'UNKNOWNRefPos', 'flavor': 'SPHER2'}})
		self.assertEqual(stcs.getCST("PositionInterval ICRS unit arcsec"),
			{'space': {'frame': 'ICRS', 'unit': 'arcsec', 
			'type': 'PositionInterval', 'refpos': 'UNKNOWNRefPos', 
			'flavor': 'SPHER2'}})
		self.assertEqual(stcs.getCST("Convex ICRS"),
			{'space': {'frame': 'ICRS', 'unit': 'deg', 'type': 'Convex', 
			'refpos': 'UNKNOWNRefPos', 'flavor': 'UNITSPHER'}})
		self.assertEqual(stcs.getCST("PositionInterval FK4 TOPOCENTER CART2"),
			{'space': {'frame': 'FK4', 'unit': 'm', 'type': 'PositionInterval', 
			'refpos': 'TOPOCENTER', 'flavor': 'CART2'}})
		self.assertEqual(stcs.getCST("PositionInterval GEO_C"),
			{'space': {'frame': 'GEO_C', 'unit': 'deg deg m', 
				'type': 'PositionInterval', 'refpos': 'UNKNOWNRefPos', 
				'flavor': 'SPHER2'}})

	def testTemporal(self):
		self.assertEqual(stcs.getCST("TimeInterval"), {'time': {'unit': 's', 
			'type': 'TimeInterval', 'refpos': 'UNKNOWNRefPos', 
			'timescale': 'nil'}})

	def testSpectral(self):
		self.assertEqual(stcs.getCST("SpectralInterval"), {'spectral': 
			{'type': 'SpectralInterval', 'refpos': 'UNKNOWNRefPos', 'unit': 'Hz'}})

	def testRedshift(self):
		self.assertEqual(stcs.getCST("RedshiftInterval"),
			{'redshift': {'redshiftType': 'VELOCITY', 'type': 'RedshiftInterval', 
			'refpos': 'UNKNOWNRefPos', 'unit': 'km/s', 'dopplerdef': 'OPTICAL'}})


if __name__=="__main__":
	testhelpers.main(TestComplexSTCSTrees)
