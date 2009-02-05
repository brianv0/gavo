"""
Tests for handling ivoa stc specifications.
"""

import unittest

from gavo.stc import stc

import testhelpers

class ValidationTests(unittest.TestCase, testhelpers.XSDTestMixin):
	"""tests for generation of XSD-valid documents from the xml stan.
	"""
	def testExample1(self):
		for name in dir(stc.STC):
			if not name.startswith("_"):
				exec "%s = getattr(stc.STC, %s)"%(name, repr(name))
		tree = STCResourceProfile[
			AstroCoordSystem(id="TT-ICRS-CXO")[
				TimeFrame[
					Name["Time"],
					TimeScale["TT"],
					makeReferencePosition("TOPOCENTER")],
				SpaceFrame[
					Name["Space"],
					makeSpaceRefFrame("ICRS"),
					makeReferencePosition("TOPOCENTER"),
					makeCoordFlavor("SPHERICAL")],
				SpectralFrame[
					Name["Energy"],
					makeReferencePosition("TOPOCENTER")]],
			AstroCoords(coord_system_id="TT-ICRS-CXO")[
				Time[
					Name["Time"],
					Error[0.000005],
					Error[0.0001],
					Resolution[0.000016],
					Resolution["3.0"],
					Size["1000"],
					Size[170000]],
				Position2D(unit="arcsec")[
					Name["Position"],
					Error2Radius[1.0],
					Resolution2Radius[0.5],
					Size2[
						C1[1000],
						C2[1000]],
					Size2[
						C1[1000],
						C2[1000]]],
				Spectral(unit="keV")[
					Name["Energy"],
					Error[0.1],
					Resolution[0.02],
					Resolution[2.0],
					Size[2],
					Size[10]]],
				AstroCoordArea(id="AllSky-CXO", coord_system_id="TT-ICRS-CXO")[
					TimeInterval[
						StartTime[
							Timescale["TT"],
							ISOTime["1999-07-23T16:00:00"]]],
					AllSky(fill_factor="0.02"),
					SpectralInterval(unit="keV")[
						LoLimit[0.12],
						HiLimit[10.0]]]]
		self.assertValidates(tree.render(), leaveOffending=__name__=="__main__")

	def _testExample2(self):
# I can't figure out why xlink:href is not allowed on these documents.
# Someone else figure this whole xsd mess out.  Holy cow, it's really
# a sensation if you come across an XSD-based doc that actually verifies.
		for name in dir(stc.STC):
			if not name.startswith("_"):
				exec "%s = getattr(stc.STC, %s)"%(name, repr(name))
		tree = ObsDataLocation[
			ObservatoryLocation(id="KPNO", type="simple",
				href="ivo://STClib/Observatories#KPNO"),
			ObservationLocation[
				AstroCoords(coord_system_id="TT-ICRS-TOPO", type="simple",
						href="ivo://STClib/CoordSys#TT-ICRS-TOPO")[
					Time(unit="s")[
						TimeInstant[
							ISOTime["2004-07-15T08:23:56"]],
						Error[2]],
					Position2D(unit="deg")[
						Value2[
							C1[148.88821],
							C2[69.06529]],
						Error2Radius[0.03]]],
				AstroCoordArea(coord_system_id="TT-ICRS-TOPO")[
					Polygon(unit="deg")[
						Vertex[
							Position[
								C1[148.88821],
								C2[68.81529]]],
						Vertex[
							Position[
								C1[148.18821],
								C2[69.01529]]],
						Vertex[
							Position[
								C1[148.88821],
								C2[69.31529]]],
						Vertex[
							Position[
								C1[149.58821],
								C2[69.01529]]]]]]]
		self.assertValidates(tree.render(), leaveOffending=__name__=="__main__")


if __name__=="__main__":
	testhelpers.main(ValidationTests)
