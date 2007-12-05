"""
Code to support simple cone search.
"""

from nevow import inevow
from zope.interface import implements

import gavo
from gavo import resourcecache
from gavo.parsing import parsehelpers
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.parsing.contextgrammar import InputKey
from gavo.web import core
from gavo.web import common
from gavo.web import standardcores
from gavo.web import resourcebased
from gavo.web import vizierexprs
from gavo.web import vodal


class ScsCondition(standardcores.CondDesc):
	"""is a condition descriptor for a plain SCS query.
	"""
	def __init__(self):
		super(ScsCondition, self).__init__(initvals={
			"inputKeys": [
				InputKey(dest="RA", dbtype="double precision", unit="deg",
					ucd="pos.eq.ra", description="ICRS right ascension",
					tablehead="Alpha (ICRS)", optional=False, source="RA"),
				InputKey(dest="DEC", dbtype="double precision", unit="deg",
					ucd="pos.eq.dec", description="ICRS declination",
					tablehead="Delta (ICRS)", optional=False, source="DEC"),
				InputKey(dest="SR", dbtype="float", unit="deg",
					description="Search radius in degrees", tablehead="Search Radius",
					optional=False, source="SR")]})

	def asSQL(self, inPars, sqlPars):
# XXX TODO: implement fallback if there's no q3c index on the table
		return ("q3c_radial_query(alphaFloat, deltaFloat, %%(%s)s, "
			"%%(%s)s, %%(%s)s)")%(
				vizierexprs.getSQLKey("RA", inPars["RA"], sqlPars),
				vizierexprs.getSQLKey("DEC", inPars["DEC"], sqlPars),
				vizierexprs.getSQLKey("SR", inPars["SR"], sqlPars))

core.registerCondDesc("scs", ScsCondition())


class HumanScsCondition(ScsCondition):
	"""is a condition descriptor for a simbad-enabled cone search.
	"""
# We need to know quite a bit of the internals of ScsCondition here,
# and we bypass its constructor so we don't get their InputKeys
	def __init__(self):
		standardcores.CondDesc.__init__(self, initvals={
			"inputKeys": [
				InputKey(dest="hscs_pos", dbtype="text", description=
					"position as hourangle, sexagesimal dec or simbad-resolvable"
					" object", tablehead="Position", source="hscs_pos"),
				InputKey(dest="hscs_sr", dbtype="float", description=
					"search radius in arcminutes", tablehead="search radius",
					source="hscs_sr")]})
	
	def asSQL(self, inPars, sqlPars):
		if not self.inputReceived(inPars):
			return ""
		pos = inPars["hscs_pos"]
		try:
			ra, dec = parsehelpers.parseCooPair(pos)
		except ValueError:
			data = resourcecache.getSesame("web").query(pos)
			if not data:
				raise gavo.ValidationError("%s is neither a RA,DEC pair nor a simbad"
				" resolvable object"%inPars["hscs_pos"], "hscs_pos")
			ra, dec = float(data["RA"]), float(data["dec"])
		try:
			sr = float(inPars["hscs_sr"])/60.
		except ValueError:
			raise gavo.ValidationError("Not a valid float", "hscs_sr")
		return super(HumanScsCondition, self).asSQL({
			"RA": ra, "DEC": dec, "SR": sr}, sqlPars)

core.registerCondDesc("humanScs", HumanScsCondition())
