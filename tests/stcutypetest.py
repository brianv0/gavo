"""
Tests for conversion between utype sequences and STC ASTs.
"""

from gavo import stc
from gavo import utils
from gavo.stc import utypeast
from gavo.utils import ElementTree

import testhelpers


class CoosysGenerTest(testhelpers.VerboseTest):
	"""tests for generation of coosys utype dicts from STC ASTs.
	"""
	def _assertSetmatch(self, literal, expected):
		ast = stc.parseSTCS(literal)
		self.assertEqual(stc.getUtypes(ast)[0],
			expected)

	def testSimpleSystems(self):
		self._assertSetmatch("Time TT Position ICRS GEOCENTER Spectral BARYCENTER"
			" Redshift BARYCENTER VELOCITY OPTICAL",{
				'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
				'AstroCoordSystem.TimeFrame.TimeScale': 'TT',
				'AstroCoordSystem.RedshiftFrame.DopplerDefinition': 'OPTICAL',
				'AstroCoordSystem.TimeFrame.ReferencePosition': 'UNKNOWNRefPos',
				'AstroCoordSystem.RedshiftFrame.value_type': 'VELOCITY',
				'AstroCoordSystem.RedshiftFrame.ReferencePosition': 'BARYCENTER',
				'AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
				'AstroCoordSystem.SpectralFrame.ReferencePosition': 'BARYCENTER',
				'AstroCoordSystem.SpaceFrame.ReferencePosition': 'GEOCENTER'})
	
	def testWithEquinox(self):
		self._assertSetmatch("Position FK4 J1975.0", {
			'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'FK4',
			'AstroCoordSystem.SpaceFrame.CoordRefFrame.Equinox': 'J1975.0',
			'AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'AstroCoordSystem.SpaceFrame.ReferencePosition': 'UNKNOWNRefPos'})
	
	def testWithDistance(self):
		self._assertSetmatch("Position ICRS BARYCENTER SPHER3 unit deg deg pc",{
			'AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes': '3',
			'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
			'AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'AstroCoordSystem.SpaceFrame.ReferencePosition': 'BARYCENTER'})


class CooGenerTest(testhelpers.VerboseTest):
	"""tests for generation of column utype dicts from STC ASTs.
	"""
	def _assertAssmatch(self, literal, truth):
		ast = stc.parseQSTCS(literal)
		self.assertEqual(dict(stc.getUtypes(ast)[1]),
			truth)
	
	def testTrivialPos(self):
		self._assertAssmatch('Position ICRS "ra" "dec"', {
			'ra': 'AstroCoords.Position2D.Value2.C1',
			'dec': 'AstroCoords.Position2D.Value2.C2', 
		})
		
	def testVecPos(self):
		self._assertAssmatch('Position ICRS [point]', 
			{'point': 'AstroCoords.Position2D.Value2'})
	
	def testVecPos3(self):
		self._assertAssmatch('Position ICRS SPHER3 [point]', 
			{'point': 'AstroCoords.Position3D.Value3'})

	def testVeloc(self):
		self._assertAssmatch(
			'Position ICRS VelocityInterval Velocity "pmra" "pmde"', {
				'pmde': 'AstroCoords.Velocity2D.Value2.C2', 
				'pmra': 'AstroCoords.Velocity2D.Value2.C1'})

	def testErrorRadius(self):
		self._assertAssmatch(
			'Position ICRS Error "ep" "ep"', {
				'ep': 'AstroCoords.Position2D.Error2Radius'})

	def testTime(self):
		self._assertAssmatch('Time TT "obsDate"',
			{'obsDate': 'AstroCoords.Time.TimeInstant.ISOTime'})

	def testTimeA(self):
		self._assertAssmatch(
			'TimeInterval TT "start" "end"', {
				'start': 'AstroCoordArea.TimeInterval.StartTime.ISOTime', 
				'end': 'AstroCoordArea.TimeInterval.StopTime.ISOTime'})
	
	def testGeoRef(self):
		self._assertAssmatch('Circle FK5 J1000.0 [circle]', {
			'circle': 'AstroCoordArea.Circle'})
		self._assertAssmatch('Box FK5 J1000.0 [bbox]', {
			'bbox': 'AstroCoordArea.Box'})
		self._assertAssmatch('Polygon FK5 J1000.0 [poly]', {
			'poly': 'AstroCoordArea.Polygon'})

	def testGeoSplit(self):
		self._assertAssmatch('Circle FK5 J1000.0 "cx" "cy" "radius"', {
			'cy': 'AstroCoordArea.Circle.Center.C2',
			'cx': 'AstroCoordArea.Circle.Center.C1',
			'radius': 'AstroCoordArea.Circle.Radius'})

	def testError(self):
		self._assertAssmatch('Position ICRS Error "e_ra" "e_dec"', {
			'e_ra': 'AstroCoords.Position2D.Error2.C1', 
			'e_dec': 'AstroCoords.Position2D.Error2.C2'})

	def testRedshift(self):
		self._assertAssmatch('Redshift "z" Error "zErr"', {
			'z': 'AstroCoords.Redshift.Value',
			'zErr': 'AstroCoords.Redshift.Error'
		})

	def testCombined(self):
		self._assertAssmatch('Time TT "dateObs" Error "e_date"'
			' Circle ICRS "cra" "cdec" "crad" Position "ra" "dec"'
			'   Error "e_ra" "e_dec" Size "s_ra" "s_dec"'
			' SpectralInterval "bandLow" "bandHigh"'
			' Redshift "z" Error "zErr"', {
					'bandHigh': 'AstroCoordArea.SpectralInterval.HiLimit', 
					'bandLow': 'AstroCoordArea.SpectralInterval.LoLimit',
					'cdec': 'AstroCoordArea.Circle.Center.C2', 
					'cra': 'AstroCoordArea.Circle.Center.C1',
					'crad': 'AstroCoordArea.Circle.Radius',
					'dateObs': 'AstroCoords.Time.TimeInstant.ISOTime', 
					'dec': 'AstroCoords.Position2D.Value2.C2',
					'e_dec': 'AstroCoords.Position2D.Error2.C2', 
					'e_ra': 'AstroCoords.Position2D.Error2.C1', 
					'e_date': 'AstroCoords.Time.Error',
					'ra': 'AstroCoords.Position2D.Value2.C1',
					's_dec': 'AstroCoords.Position2D.Size2.C2',
					's_ra': 'AstroCoords.Position2D.Size2.C1', 
					'z': 'AstroCoords.Redshift.Value',
					'zErr': 'AstroCoords.Redshift.Error',
				})


def _etreeToString(et):
	return ElementTree.tostring(et)


class PairseqETTest(testhelpers.VerboseTest):
	"""tests for building ETrees from key/value pairs.
	"""
	def testPairBulding(self):
		et = utypeast.utypePairsToTree(sorted([
			("foo.bar.baz", "ab"),
			("foo.bar.quux", "u"),
			("foo.nuuk", "r"),
			("foo.nuuk", "x"),
			("boo.work.noppa.poo", "z")]), utils.identity)
		self.assertEqual(_etreeToString(et), '<STCSpec><boo><work><noppa><poo>'
			'z</poo></noppa></work></boo><foo><bar><baz>ab</baz><quux>u</quux>'
			'</bar><nuuk>r</nuuk><nuuk>x</nuuk></foo></STCSpec>')

	def testFromSTCS(self):
		sys, col = stc.getUtypes(stc.parseQSTCS('Position ICRS BARYCENTER'
			' "ra" "dec" VelocityInterval Velocity "pmra" "pmdec"'))
		et = utypeast.utypePairsToTree(
			sorted(sys.items()+[(v, k) for k, v in col.iteritems()]))
		serialized = _etreeToString(et)
		self.failUnless("RefFrame>ICRS</stc:CoordRefF" in serialized)
		self.failUnless('Velocity2D><stc:Value2><stc:C1>pmra</stc:C1><stc:C2>'
			'pmdec</stc:C2></stc:Value2></stc:V' in serialized)


class UtypeASTTest(testhelpers.VerboseTest):
	"""tests for building STC ASTs out of utype sequences.
	"""
	def _getASTFromSTCS(self, stcs):
		ast = stc.parseQSTCS(stcs)
		sys, col = stc.getUtypes(ast)
		return stc.parseFromUtypes(sys, col)

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
	

class UtypeRoundtripTest(testhelpers.VerboseTest):
	"""tests for working roundtrip of utype de-/serialization.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _assertSubdict(self, sub, full):
		for k, v in sub.iteritems():
			if k not in full:
				raise AssertionError("%s not in full"%k)
			if sub[k]!=full[k]:
				raise AssertionError("%s has wrong value, %s instead of %s"%(
					k, full[k], sub[k]))

	def _runTest(self, args):
		sysTypes0, colTypes0 = args
		ast = stc.parseFromUtypes(sysTypes0, colTypes0)
		sysTypes1, colTypes1 = stc.getUtypes(ast)
		self.assertEqual(colTypes0, colTypes1)
		#print colTypes1, sysTypes1
		# allow additional key in the system, but all original ones must be there.
		self._assertSubdict(sysTypes0, sysTypes1)

	samples = [
		({}, {}),
		({'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS'}, {}),
		({}, 
		 {'ra': 'AstroCoords.Position2D.Value2.C1',
		  'dec': 'AstroCoords.Position2D.Value2.C2'}),
		({'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
			'AstroCoordSystem.TimeFrame.TimeScale': 'TT',
			'AstroCoordSystem.RedshiftFrame.DopplerDefinition': 'OPTICAL',
			'AstroCoordSystem.TimeFrame.ReferencePosition': 'UNKNOWNRefPos',
			'AstroCoordSystem.RedshiftFrame.value_type': 'VELOCITY',
			'AstroCoordSystem.RedshiftFrame.ReferencePosition': 'BARYCENTER',
			'AstroCoordSystem.SpaceFrame.CoordFlavor': 'SPHERICAL',
			'AstroCoordSystem.SpectralFrame.ReferencePosition': 'BARYCENTER',
			'AstroCoordSystem.SpaceFrame.ReferencePosition': 'GEOCENTER'},
		 {'ra': 'AstroCoords.Position2D.Value2.C1',
		  'dec': 'AstroCoords.Position2D.Value2.C2'}),
		({'AstroCoordSystem.SpaceFrame.CoordRefFrame': 'ICRS',
			'AstroCoordSystem.SpaceFrame.CoordFlavor': 'CARTESIAN',
			'AstroCoordSystem.SpaceFrame.CoordFlavor.coord_naxes': '3'},{}),
		({}, {'errc': 'AstroCoordArea.Circle'}),
	]


if __name__=="__main__":
	testhelpers.main(UtypeASTTest)
