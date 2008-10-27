"""
Code to support simple cone search.
"""

from nevow import inevow
from zope.interface import implements

import gavo
from gavo import resourcecache
from gavo.parsing import parsehelpers
from gavo.parsing import resource
from gavo.web import core
from gavo.web import common
from gavo.web import gwidgets
from gavo.web import standardcores
from gavo.web import resourcebased
from gavo.web import vizierexprs
from gavo.web import vodal


class ScsCondition(standardcores.CondDesc):
	"""is a condition descriptor for a plain SCS query.
	"""
	def __init__(self, initvals={}):
		vals = {
			"inputKeys": [
				gwidgets.InputKey(dest="RA", dbtype="double precision", unit="deg",
					ucd="pos.eq.ra", description="Right ascension (J2000.0)",
					tablehead="Alpha (ICRS)", optional=False, source="RA"),
				gwidgets.InputKey(dest="DEC", dbtype="double precision", unit="deg",
					ucd="pos.eq.dec", description="Declination (J2000.0)",
					tablehead="Delta (ICRS)", optional=False, source="DEC"),
				gwidgets.InputKey(dest="SR", dbtype="float", unit="deg",
					description="Search radius in degrees", tablehead="Search Radius",
					optional=False, source="SR")],
		}
		vals.update(initvals)
# XXX TODO: infer alphaFloat, deltaFloat from ucds on associated table
# (i.e., make table visible to condDesc)
		super(ScsCondition, self).__init__(initvals=vals, additionalFields={
			"alphaField": "alphaFloat",
			"deltaField": "deltaFloat",})

	def asSQL(self, inPars, sqlPars):
# XXX TODO: implement fallback if there's no q3c index on the table
		return ("q3c_radial_query(%s, %s, %%(%s)s, "
			"%%(%s)s, %%(%s)s)")%(
				self.get_alphaField(),
				self.get_deltaField(),
				vizierexprs.getSQLKey("RA", inPars["RA"], sqlPars),
				vizierexprs.getSQLKey("DEC", inPars["DEC"], sqlPars),
				vizierexprs.getSQLKey("SR", inPars["SR"], sqlPars))

core.registerCondDesc("scs", ScsCondition)


class HumanScsCondition(ScsCondition):
	"""is a condition descriptor for a simbad-enabled cone search.
	"""
	def __init__(self, initvals={}):
		vals={
			"inputKeys": [
				gwidgets.InputKey(dest="hscs_pos", dbtype="text", description=
					"position as sexagesimal ra, dec or Simbad-resolvable"
					" object", tablehead="Position", source="hscs_pos"),
				gwidgets.InputKey(dest="hscs_sr", dbtype="float", description=
					"Search radius in arcminutes", tablehead="Search radius",
					source="hscs_sr")],
		}
		vals.update(initvals)
		super(HumanScsCondition, self).__init__(initvals=vals)
	
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

core.registerCondDesc("humanScs", HumanScsCondition)
