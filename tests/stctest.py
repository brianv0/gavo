"""
Tests for handling ivoa stc specifications.
"""

import unittest

from gavo.stc import dm
from gavo.stc import stcs

import testhelpers

class ValidationTests(unittest.TestCase, testhelpers.XSDTestMixin):
	"""tests for generation of XSD-valid documents from the xml stan.
	"""
	def testExample1(self):
		for name in dir(dm.STC):
			if not name.startswith("_"):
				exec "%s = getattr(dm.STC, %s)"%(name, repr(name))
		tree = STCResourceProfile[
			AstroCoordSystem(id="TT-ICRS-CXO")[
				TimeFrame[
					Name["Time"],
					TimeScale["TT"],
					TOPOCENTER],
				SpaceFrame[
					Name["Space"],
					ICRS,
					TOPOCENTER,
					SPHERICAL],
				SpectralFrame[
					Name["Energy"],
					TOPOCENTER]],
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


class STCSParseTest(testhelpers.VerboseTest):
	"""tests for (not) parsing parts of STCS.
	"""
	grammar, syms = stcs.getGrammar()

	def testParseTimeStuff(self):
# We're only interested in stuff not raising ParseErrors
		for sym, literal in [
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
			]:
			self.syms[sym].parseString(literal, parseAll=True)
	
	def testNoParseTimeStuff(self):
		for sym, literal in [
			("timeInterval", "TimeInterval unit s fillfactor 0.1"),
			("timeInterval", "TimeInterval fillfactor 0.1 foobar"),
			("timeInterval", "fillfactor 0.1 foobar"),
			("startTime", "startTime 1900-01-01 2000-01-01 unit s"),
			]:
			self.assertRaises(stcs.ParseException, self.syms[sym].parseString,
				literal, parseAll=True)


if __name__=="__main__":
	testhelpers.main(STCSParseTest)
