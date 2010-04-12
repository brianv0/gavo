"""
Tests for conversion between utype sequences and STC ASTs.
"""

from gavo import stc
from gavo import utils
from gavo.stc import dm
from gavo.stc import utypeast
from gavo.utils import ElementTree

import testhelpers


class CoosysGenerTest(testhelpers.VerboseTest):
	"""tests for generation of coosys utype dicts from STC ASTs.
	"""
	def _assertSetmatch(self, literal, expected):
		ast = stc.parseSTCS(literal)
		self.assertEqual(dict(stc.getUtypes(ast)),
			expected)

	def testRef(self):
		tree = dm.STCSpec(astroSystem=stc.getLibrarySystem("TT-ICRS-OPT-BARY-TOPO"))
		self.assertEqual(stc.getUtypes(tree), 
			[('stc:AstroCoordSystem.href', 
				'ivo://STClib/CoordSys#TT-ICRS-OPT-BARY-TOPO')])

	def testSimpleSystems(self):
		self._assertSetmatch("Time TT Position ICRS GEOCENTER Spectral BARYCENTER"
			" Redshift BARYCENTER VELOCITY OPTICAL", {
				'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
				'stc:AstroCoordSystem.TimeFrame.TimeScale': 'TT',
				'stc:AstroCoordSystem.RedshiftFrame.DopplerDefinition': 'OPTICAL',
				'stc:AstroCoordSystem.TimeFrame.ReferencePosition': 'UNKNOWNRefPos',
				'stc:AstroCoordSystem.RedshiftFrame.value_type': 'VELOCITY',
				'stc:AstroCoordSystem.RedshiftFrame.ReferencePosition': 'BARYCENTER',
				'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
				'stc:AstroCoordSystem.SpectralFrame.ReferencePosition': 'BARYCENTER',
				'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'GEOCENTER'})
	
	def testWithEquinox(self):
		self._assertSetmatch("Position FK4 J1975.0", {
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'FK4',
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame.Equinox': 'J1975.0',
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'UNKNOWNRefPos'})
	
	def testWithDistance(self):
		self._assertSetmatch("Position ICRS BARYCENTER SPHER3 unit deg deg pc",{
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes': '3',
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'BARYCENTER'})


class CooGenerTest(testhelpers.VerboseTest):
	"""tests for generation of column utype dicts from STC ASTs.
	"""
	def _assertAssmatch(self, literal, truth):
		ast = stc.parseQSTCS(literal)
		gr = [p for p in stc.getUtypes(ast) 
			if not p[0].startswith("stc:AstroCoordSystem")]
		for k in truth:
			if isinstance(truth[k], basestring):
				truth[k] = stc.ColRef(truth[k])
			else:
				truth[k] = str(truth[k])
		self.assertEqual(dict(gr), truth)
	
	def testTrivialPos(self):
		self._assertAssmatch('Position ICRS "ra" "dec"', {
			'stc:AstroCoords.Position2D.Value2.C1': "ra",
			'stc:AstroCoords.Position2D.Value2.C2': "dec", 
		})

	def testMixedPos(self):
		self._assertAssmatch('Position ICRS "ra" 20.0', {
			'stc:AstroCoords.Position2D.Value2.C1': "ra",
			'stc:AstroCoords.Position2D.Value2.C2': 20.0, 
		})

	def testVecPos(self):
		self._assertAssmatch('Position ICRS [point]', 
			{'stc:AstroCoords.Position2D.Value2': "point"})
	
	def testVecPos3(self):
		self._assertAssmatch('Position ICRS SPHER3 [point]', 
			{'stc:AstroCoords.Position3D.Value3': 'point'})

	def testVeloc(self):
		self._assertAssmatch(
			'Position ICRS VelocityInterval Velocity "pmra" "pmde"', {
				'stc:AstroCoords.Velocity2D.Value2.C2': 'pmde',
				'stc:AstroCoords.Velocity2D.Value2.C1': 'pmra'})

	def testErrorRadius(self):
		self._assertAssmatch(
			'Position ICRS Error "ep" "ep"', {
				'stc:AstroCoords.Position2D.Error2Radius': 'ep'})

	def testTime(self):
		self._assertAssmatch('Time TT "obsDate"',
			{'stc:AstroCoords.Time.TimeInstant.ISOTime': "obsDate"})

	def testTimeA(self):
		self._assertAssmatch(
			'TimeInterval TT "start" "end"', {
				'stc:AstroCoordArea.TimeInterval.StartTime.ISOTime': 'start', 
				'stc:AstroCoordArea.TimeInterval.StopTime.ISOTime': 'end'})
	
	def testGeoRef(self):
		self._assertAssmatch('Circle FK5 J1000.0 [circle]', {
			'stc:AstroCoordArea.Circle': 'circle'})
		self._assertAssmatch('Box FK5 J1000.0 [bbox]', {
			'stc:AstroCoordArea.Box': 'bbox'})
		self._assertAssmatch('Polygon FK5 J1000.0 [poly]', {
			'stc:AstroCoordArea.Polygon': 'poly'})

	def testGeoSplit(self):
		self._assertAssmatch('Circle FK5 J1000.0 "cx" "cy" "radius"', {
			'stc:AstroCoordArea.Circle.Center.C2': 'cy',
			'stc:AstroCoordArea.Circle.Center.C1': 'cx',
			'stc:AstroCoordArea.Circle.Radius': 'radius'})

	def testError(self):
		self._assertAssmatch('Position ICRS Error "e_ra" "e_dec"', {
			'stc:AstroCoords.Position2D.Error2.C1': 'e_ra', 
			'stc:AstroCoords.Position2D.Error2.C2': 'e_dec'})

	def testRedshift(self):
		self._assertAssmatch('Redshift "z" Error "zErr"', {
			'stc:AstroCoords.Redshift.Value': 'z',
			'stc:AstroCoords.Redshift.Error': 'zErr'
		})

	def testCombined(self):
		self._assertAssmatch('Time TT "dateObs" Error "e_date"'
			' Circle ICRS "cra" "cdec" "crad" Position "ra" "dec"'
			'   Error "e_ra" "e_dec" Size "s_ra" "s_dec"'
			' SpectralInterval "bandLow" "bandHigh"'
			' Redshift "z" Error "zErr"', {
					'stc:AstroCoordArea.SpectralInterval.HiLimit': 'bandHigh', 
					'stc:AstroCoordArea.SpectralInterval.LoLimit': 'bandLow',
					'stc:AstroCoordArea.Circle.Center.C2': 'cdec', 
					'stc:AstroCoordArea.Circle.Center.C1': 'cra',
					'stc:AstroCoordArea.Circle.Radius': 'crad',
					'stc:AstroCoords.Time.TimeInstant.ISOTime': 'dateObs', 
					'stc:AstroCoords.Position2D.Value2.C2': 'dec',
					'stc:AstroCoords.Position2D.Error2.C2': 'e_dec', 
					'stc:AstroCoords.Position2D.Error2.C1': 'e_ra', 
					'stc:AstroCoords.Time.Error': 'e_date',
					'stc:AstroCoords.Position2D.Value2.C1': 'ra',
					'stc:AstroCoords.Position2D.Size2.C2': 's_dec',
					'stc:AstroCoords.Position2D.Size2.C1': 's_ra', 
					'stc:AstroCoords.Redshift.Value': 'z',
					'stc:AstroCoords.Redshift.Error': 'zErr',
				})


class UtypeASTTest(testhelpers.VerboseTest):
	"""tests for building STC ASTs out of utype sequences.
	"""
	def _getASTFromSTCS(self, stcs):
		ast = stc.parseQSTCS(stcs)
		utypes = stc.getUtypes(ast)
		return stc.parseFromUtypes(utypes)

	def testSimplePos(self):
		ast = self._getASTFromSTCS('Position GALACTIC "long" "lat"')
		self.assertEqual(ast.astroSystem.spaceFrame.refFrame, "GALACTIC_II")
		self.assertEqual(ast.place.value[0].dest, "long")
		self.assertEqual(ast.place.frame.refFrame, "GALACTIC_II")

	def testWithError(self):
		ast = self._getASTFromSTCS('Position GALACTIC Error "e1" "e1"')
		self.assertEqual(ast.place.error.radii[0].dest, "e1")

	def testWithEquinox(self):
		ast = self._getASTFromSTCS("Position FK4 J1975.0")
		self.assertEqual(ast.astroSystem.spaceFrame.equinox, "J1975.0")

	def testTime(self):
		ast = self._getASTFromSTCS(
			'Time TT TOPOCENTER "dateObs" Error "clockdamage"')
		self.assertEqual(ast.time.value.dest, "dateObs")
		self.assertEqual(ast.time.error.values[0].dest, "clockdamage")
		self.assertEqual(ast.time.frame.refPos.standardOrigin, "TOPOCENTER")
		self.assertEqual(ast.time.frame.timeScale, "TT")

	def testGeoComp(self):
		ast = self._getASTFromSTCS('Circle ICRS [errc]')
		self.assertEqual(ast.areas[0].geoColRef.dest, "errc")

	def testTime(self):
		ast = self._getASTFromSTCS('Time TDB "time"')
		self.assertEqual(ast.time.frame.timeScale, 'TDB')


class UtypeRoundtripTest(testhelpers.VerboseTest):
	"""tests for working roundtrip of utype de-/serialization.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _assertSublist(self, sub, full):
		sub, full = dict(sub), dict(full)
		for k, v in sub.iteritems():
			if k not in full:
				raise AssertionError("%s not in full"%k)
			if sub[k]!=full[k]:
				raise AssertionError("%s has wrong value, %s instead of %s"%(
					k, full[k], sub[k]))

	def _runTest(self, args):
		inTypes = args
		ast = stc.parseFromUtypes(inTypes)
		outTypes = stc.getUtypes(ast)
		#print colTypes1, sysTypes1
		# allow additional keys in output (non-removed defaults)
		self._assertSublist(inTypes, outTypes)

	samples = [
		[],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS')],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS'),
			('stc:AstroCoords.Position2D.epoch', 'J2002.0'),
		],
		[('stc:AstroCoords.Position2D.Value2.C1', stc.ColRef('ra')),
			('stc:AstroCoords.Position2D.Value2.C2', stc.ColRef('dec'))],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS'),
			('stc:AstroCoordSystem.TimeFrame.TimeScale', 'TT'),
			('stc:AstroCoordSystem.RedshiftFrame.DopplerDefinition', 'OPTICAL'),
			('stc:AstroCoordSystem.TimeFrame.ReferencePosition', 'UNKNOWNRefPos'),
			('stc:AstroCoordSystem.RedshiftFrame.value_type', 'VELOCITY'),
			('stc:AstroCoordSystem.RedshiftFrame.ReferencePosition', 'BARYCENTER'),
			('stc:AstroCoordSystem.SpaceFrame.CoordFlavor', 'SPHERICAL'),
			('stc:AstroCoordSystem.SpectralFrame.ReferencePosition', 'BARYCENTER'),
			('stc:AstroCoordSystem.SpaceFrame.ReferencePosition', 'GEOCENTER'),
		 	('stc:AstroCoords.Position2D.Value2.C1', stc.ColRef('ra')),
		  ('stc:AstroCoords.Position2D.Value2.C2', stc.ColRef('dec'))],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS'),
			('stc:AstroCoordSystem.SpaceFrame.CoordFlavor', 'CARTESIAN'),
			('stc:AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes', '3')],
		[
			('stc:AstroCoords.Time.TimeInstant.ISOTime', '2000-01-01T00:00:00'),
			('stc:AstroCoordArea.Circle', stc.ColRef('errc'))],
		[
			('stc:AstroCoordSystem.href', 
				'ivo://STClib/CoordSys#TT-ICRS-OPT-BARY-TOPO')],
	]


if __name__=="__main__":
	testhelpers.main(UtypeRoundtripTest)
