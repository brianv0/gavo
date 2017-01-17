"""
Tests for conversion between utype sequences and STC ASTs.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo import stc
from gavo import utils
from gavo.stc import dm
from gavo.stc import utypeast
from gavo.utils import ElementTree



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
				'stc:AstroCoordSystem.RedshiftFrame.value_type': 'VELOCITY',
				'stc:AstroCoordSystem.RedshiftFrame.ReferencePosition': 'BARYCENTER',
				'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
				'stc:AstroCoordSystem.SpectralFrame.ReferencePosition': 'BARYCENTER',
				'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'GEOCENTER'})
	
	def testWithEquinox(self):
		self._assertSetmatch("Position FK4 J1975.0", {
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'FK4',
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame.Equinox': 'J1975.0',
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',})
	
	def testWithDistance(self):
		self._assertSetmatch("Position ICRS BARYCENTER SPHER3 unit deg deg pc",{
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes': '3',
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'BARYCENTER'})

	def testWithPleph(self):
		self._assertSetmatch("Position ICRS BARYCENTER JPL-DE405", {
			'stc:AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL', 
			'stc:AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS', 
			'stc:AstroCoordSystem.SpaceFrame.ReferencePosition.PlanetaryEphem': 
				'JPL-DE405', 
			'stc:AstroCoordSystem.SpaceFrame.ReferencePosition': 'BARYCENTER'})


CR = stc.ColRef


class CooGenerTest(testhelpers.VerboseTest):
	"""tests for generation of column utype dicts from STC ASTs.
	"""
	def _assertAssmatch(self, literal, truth):
		ast = stc.parseQSTCS(literal)
		gr = [p for p in stc.getUtypes(ast) 
			if not p[0].startswith("stc:AstroCoordSystem")]
		self.assertEqual(dict(gr), truth)
	
	def testTrivialPos(self):
		self._assertAssmatch('Position ICRS "ra" "dec"', {
			'stc:AstroCoords.Position2D.Value2.C1': CR("ra"),
			'stc:AstroCoords.Position2D.Value2.C2': CR("dec"), 
		})

	def testMixedPos(self):
		self._assertAssmatch('Position ICRS "ra" 20.0', {
			'stc:AstroCoords.Position2D.Value2.C1': CR("ra"),
			'stc:AstroCoords.Position2D.Value2.C2': '20.0', 
		})

	def testVecPos(self):
		self._assertAssmatch('Position ICRS [point]', 
			{'stc:AstroCoords.Position2D.Value2': CR("point")})
	
	def testVecPos3(self):
		self._assertAssmatch('Position ICRS SPHER3 [point]', 
			{'stc:AstroCoords.Position3D.Value3': CR('point')})

	def testVecEpoch(self):
		self._assertAssmatch('Position ICRS Epoch J2010.5', {
			'stc:AstroCoords.Position2D.Epoch': '2010.5',
			'stc:AstroCoords.Position2D.Epoch.yearDef': 'J'})

	def testBesselEpoch(self):
		self._assertAssmatch('Position ICRS Epoch B2010.5', {
			'stc:AstroCoords.Position2D.Epoch': '2010.5',
			'stc:AstroCoords.Position2D.Epoch.yearDef': 'B'})

	def testVeloc(self):
		self._assertAssmatch(
			'Position ICRS VelocityInterval Velocity "pmra" "pmde"', {
				'stc:AstroCoords.Velocity2D.Value2.C2': CR('pmde'),
				'stc:AstroCoords.Velocity2D.Value2.C1': CR('pmra')})

	def testErrorRadius(self):
		self._assertAssmatch(
			'Position ICRS Error "ep" "ep"', {
				'stc:AstroCoords.Position2D.Error2Radius': CR('ep')})

	def testTime(self):
		self._assertAssmatch('Time TT "obsDate"', {
			'stc:AstroCoords.Time.TimeInstant': CR("obsDate"),})

	def testTimeA(self):
		self._assertAssmatch(
			'TimeInterval TT "start" "end"', {
				'stc:AstroCoordArea.TimeInterval.StartTime': CR('start'), 
				'stc:AstroCoordArea.TimeInterval.StopTime': CR('end')})
	
	def testGeoRef(self):
		self._assertAssmatch('Circle FK5 J1000.0 [circle]', {
			'stc:AstroCoordArea.Circle': CR('circle')})
		self._assertAssmatch('Box FK5 J1000.0 [bbox]', {
			'stc:AstroCoordArea.Box': CR('bbox')})
		self._assertAssmatch('Polygon FK5 J1000.0 [poly]', {
			'stc:AstroCoordArea.Polygon': CR('poly')})

	def testGeoSplit(self):
		self._assertAssmatch('Circle FK5 J1000.0 "cx" "cy" "radius"', {
			'stc:AstroCoordArea.Circle.Center.C2': CR('cy'),
			'stc:AstroCoordArea.Circle.Center.C1': CR('cx'),
			'stc:AstroCoordArea.Circle.Radius': CR('radius')})

	def testError(self):
		self._assertAssmatch('Position ICRS Error "e_ra" "e_dec"', {
			'stc:AstroCoords.Position2D.Error2.C1': CR('e_ra'), 
			'stc:AstroCoords.Position2D.Error2.C2': CR('e_dec')})

	def testRedshift(self):
		self._assertAssmatch('Redshift "z" Error "zErr"', {
			'stc:AstroCoords.Redshift.Value': CR('z'),
			'stc:AstroCoords.Redshift.Error': CR('zErr')
		})

	def testCombined(self):
		self._assertAssmatch('Time TT "dateObs" Error "e_date"'
			' Circle ICRS "cra" "cdec" "crad" Position "ra" "dec"'
			'   Error "e_ra" "e_dec" Size "s_ra" "s_dec"'
			' SpectralInterval "bandLow" "bandHigh"'
			' Redshift "z" Error "zErr"', {
					'stc:AstroCoordArea.SpectralInterval.HiLimit': CR('bandHigh'), 
					'stc:AstroCoordArea.SpectralInterval.LoLimit': CR('bandLow'),
					'stc:AstroCoordArea.Circle.Center.C2': CR('cdec'), 
					'stc:AstroCoordArea.Circle.Center.C1': CR('cra'),
					'stc:AstroCoordArea.Circle.Radius': CR('crad'),
					'stc:AstroCoords.Time.TimeInstant': CR('dateObs'), 
					'stc:AstroCoords.Position2D.Value2.C2': CR('dec'),
					'stc:AstroCoords.Position2D.Error2.C2': CR('e_dec'), 
					'stc:AstroCoords.Position2D.Error2.C1': CR('e_ra'), 
					'stc:AstroCoords.Time.Error': CR('e_date'),
					'stc:AstroCoords.Position2D.Value2.C1': CR('ra'),
					'stc:AstroCoords.Position2D.Size2.C2': CR('s_dec'),
					'stc:AstroCoords.Position2D.Size2.C1': CR('s_ra'), 
					'stc:AstroCoords.Redshift.Value': CR('z'),
					'stc:AstroCoords.Redshift.Error': CR('zErr'),
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
		ast = self._getASTFromSTCS("Position FK4 J1975.0 Epoch B2000.0")
		self.assertEqual(ast.astroSystem.spaceFrame.equinox, "J1975.0")
		self.assertEqual(ast.place.yearDef, "B")
		self.assertEqual(ast.place.epoch, 2000.)

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

	def testPleph(self):
		ast = self._getASTFromSTCS('Time TDB TOPOCENTER JPL-DE405')
		self.assertEqual(ast.astroSystem.timeFrame.refPos.planetaryEphemeris, 
			"JPL-DE405")


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
		outTypes = stc.getUtypes(ast, includeDMURI=True)
		# allow additional keys in output (non-removed defaults)
		self._assertSublist(inTypes, outTypes)

	samples = [
		[],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS')],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS'),
			('stc:AstroCoords.Position2D.Epoch', '2002.0'),
			('stc:DataModel.URI', 'http://www.ivoa.net/xml/STC/stc-v1.30.xsd'),
		],
		[('stc:AstroCoords.Position2D.Value2.C1', stc.ColRef('ra')),
			('stc:AstroCoords.Position2D.Value2.C2', stc.ColRef('dec'))],
		[('stc:AstroCoordSystem.SpaceFrame.CoordRefFrame', 'ICRS'),
			('stc:AstroCoordSystem.TimeFrame.TimeScale', 'TT'),
			('stc:AstroCoordSystem.RedshiftFrame.DopplerDefinition', 'OPTICAL'),
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
			('stc:AstroCoords.Time.TimeInstant', '2000-01-01T00:00:00'),
			('stc:AstroCoordArea.Circle', stc.ColRef('errc'))],
		[
			('stc:AstroCoordSystem.href', 
				'ivo://STClib/CoordSys#TT-ICRS-OPT-BARY-TOPO')],
	]


if __name__=="__main__":
	testhelpers.main(CooGenerTest)
