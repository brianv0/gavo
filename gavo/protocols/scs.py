"""
Code to support simple cone search.
"""

from nevow import inevow
from zope.interface import implements

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo.base import coords
from gavo.base import vizierexprs
from gavo.protocols import simbadinterface


class ScsCondition(svcs.CondDesc):
	"""is a condition descriptor for a plain SCS query.
	"""
	def __init__(self, parent, **kwargs):
		if "inputKeys" not in kwargs:
			kwargs["inputKeys"] = [
				base.makeStruct(svcs.InputKey, name="RA", type="double precision", 
					unit="deg", ucd="pos.eq.ra", description="Right ascension (ICRS)",
					tablehead="Alpha (ICRS)", required=True),
				base.makeStruct(svcs.InputKey, name="DEC", type="double precision", 
					unit="deg", ucd="pos.eq.dec", description="Declination (ICRS)",
					tablehead="Delta (ICRS)", required=True),
				base.makeStruct(svcs.InputKey, name="SR", type="real", unit="deg",
					description="Search radius in degrees", tablehead="Search Radius",
					required=True)]
		# we take alpha and delta names name our core's table later.
		svcs.CondDesc.__init__(self, parent, **kwargs)
	
	def onParentCompleted(self):
		self.alphaField = self.parent.queriedTable.columns.getColumnByUCD(
			"pos.eq.ra;meta.main").name
		self.deltaField = self.parent.queriedTable.columns.getColumnByUCD(
			"pos.eq.dec;meta.main").name

	def asSQL(self, inPars, sqlPars):
# XXX TODO: implement fallback if there's no q3c index on the table
		return ("q3c_radial_query(%s, %s, %%(%s)s, "
			"%%(%s)s, %%(%s)s)")%(
				self.alphaField,
				self.deltaField,
				vizierexprs.getSQLKey("RA", inPars["RA"], sqlPars),
				vizierexprs.getSQLKey("DEC", inPars["DEC"], sqlPars),
				vizierexprs.getSQLKey("SR", inPars["SR"], sqlPars))

svcs.registerCondDesc("scs", ScsCondition)


class HumanScsCondition(ScsCondition):
	"""is a condition descriptor for a simbad-enabled cone search.
	"""
	def __init__(self, parent, **kwargs):
		if "inputKeys" not in kwargs:
			kwargs["inputKeys"] =  [
				base.makeStruct(svcs.InputKey, name="hscs_pos", type="text", 
					description= "position as sexagesimal ra, dec or Simbad-resolvable"
					" object", tablehead="Position"),
				base.makeStruct(svcs.InputKey, name="hscs_sr",
					description="Search radius in arcminutes", 
					tablehead="Search radius")]
		ScsCondition.__init__(self, parent, **kwargs)
	
	def asSQL(self, inPars, sqlPars):
		if not self.inputReceived(inPars):
			return ""
		pos = inPars["hscs_pos"]
		try:
			ra, dec = base.parseCooPair(pos)
		except ValueError:
			data = base.caches.getSesame("web").query(pos)
			if not data:
				raise base.ValidationError("%s is neither a RA,DEC pair nor a simbad"
				" resolvable object"%inPars["hscs_pos"], "hscs_pos")
			ra, dec = float(data["RA"]), float(data["dec"])
		try:
			sr = float(inPars["hscs_sr"])/60.
		except ValueError:
			raise gavo.ValidationError("Not a valid float", "hscs_sr")
		res = super(HumanScsCondition, self).asSQL({
			"RA": ra, "DEC": dec, "SR": sr}, sqlPars)
		return res

svcs.registerCondDesc("humanScs", HumanScsCondition)


class PositionsMixin(rscdef.RMixinBase):
	"""is an interface for positions.
	
	It consists of the fields alphaFloat, deltaFloat (float angles
	in degrees, J2000.0) and c_x, c_y, c_z (intersection of the radius
	vector to alphaFloat, deltaFloat with the unit sphere).

	You will usually use it in conjunction with the handleEquatorialPosition
	macro that prepares these fields for you.  So, you might say:

		<Grammar...>
      <Macro name="handleEquatorialPosition"
          alphaFormat="mas" deltaFormat="mas">
        <arg name="alpha" source="18-27"/>
        <arg name="delta" source="29-38"/>
      </Macro>
		<Grammar>
		<Semantics>
			<Record table="data">
				<implements name="positions"/>
			</Record>
		</Semantics>
	"""
	name = "positions"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "positionsFields")

rscdef.registerRMixin(PositionsMixin())


class Q3CPositionsMixin(rscdef.RMixinBase):
	"""is an interface for positions indexed using q3c.
	
	This works exactly like the positions interface, except that behind
	the scenes some magic code generates a q3c index on the fields
	with pos.eq.ra;meta.main and pos.eq.dec;meta.main.
	This will fail if you don't have the q3c extension to
	postgres.
	"""
	name = "q3cpositions"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "q3cPositionsFields")

	@staticmethod
	def findNClosest(alpha, delta, tableName, n, fields, searchRadius=5):
		"""returns the n objects closest around alpha, delta in table.

		n is the number of items returned, with the closest ones at the
		top, fields is a sequence of desired field names, searchRadius
		is a radius for the initial q3c search and will need to be
		lowered for dense catalogues and possibly raised for sparse ones.

		The last item of each row is the distance of the object from
		the query center in radians (in a flat approximation).
		"""
		q = base.SimpleQuerier()
		c_x, c_y, c_z = coords.computeUnitSphereCoords(alpha, delta)
		res = q.query("SELECT %s,"
				" sqrt((%%(c_x)s-c_x)^2+(%%(c_y)s-c_y)^2+(%%(c_z)s-c_z)^2) AS dist"
				" FROM %s WHERE"
				" q3c_radial_query(alphaFloat, deltaFloat, %%(alpha)s, %%(delta)s,"
				" %%(searchRadius)s)"
				" ORDER BY dist LIMIT %%(n)s"%
					(",".join(fields), tableName),
			locals()).fetchall()
		return res

rscdef.registerRMixin(Q3CPositionsMixin())

class Q3CIndex(rscdef.RMixinBase):
	"""is an interface indexing the main positions of a table using Q3C

	The difference to Q3CPositions is that no cartesian coordinates are
	introduced into the table and the positions are taken from the
	fields with the ucds pos.eq.ra;meta.main and pos.eq.dec;meta.main;
	we will raise an error if there are not exactly one of these each
	in the pertaining record.
	"""
	name = "q3cindex"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "q3cIndexDef")

rscdef.registerRMixin(Q3CIndex())
