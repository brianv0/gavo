"""
IVOA code search: mixins and CondDescs.
"""

from nevow import inevow
from zope.interface import implements

from gavo import base
from gavo import rscdef
from gavo import svcs
from gavo.base import coords
from gavo.base import vizierexprs
from gavo.protocols import simbadinterface


class PositionsMixin(rscdef.RMixinBase):
	"""A mixin adding standardized columns for equatorial positions to the
	table.
	
	It consists of the fields alphaFloat, deltaFloat (float angles
	in degrees, J2000.0) and c_x, c_y, c_z (intersection of the radius
	vector to alphaFloat, deltaFloat with the unit sphere).

	You will usually use it in conjunction with the predefined proc
	handleEquatorialPosition that preparse these fields for you.

	Thus, you could say::

		<proc predefined="handleEquatorialPosition">
			<arg name="alpha">alphaSrc</arg>
			<arg name="delta">deltaSrc</arg>
		</proc>
	
	Note, however, that it's usually much better to not mess with the
	table structure and handle positions using the q3cindex mixin.

	This mixin will probably grow the ability to transform the coordinates
	to a standard system, at which point it will become useful.
	"""
	name = "positions"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "positionsFields")

rscdef.registerRMixin(PositionsMixin())


class Q3CPositionsMixin(rscdef.RMixinBase):
	"""An extension of `the products mixin`_ adding a positional index.
	
	This works exactly like the positions interface, except that behind
	the scenes some magic code generates a q3c index on the fields
	alphaFloat and deltaFloat.

	This will fail without the q3c extension to postgres.
	"""
	name = "q3cpositions"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "q3cPositionsFields")


rscdef.registerRMixin(Q3CPositionsMixin())

class Q3CIndex(rscdef.RMixinBase):
	"""A mixin adding an index to the main equatorial positions.

	This is what you usually want if your input data already has
	"sane" (i.e., ICRS or at least J2000) positions or you convert
	the positions manually.

	You have to designate exactly one column with the ucds pos.eq.ra;meta.main
	pos.eq.dec;meta.main, respectively.  These columns receive the
	positional index.

	This will fail without the q3c extension to postgres.
	"""
	name = "q3cindex"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/scs", "q3cIndexDef")

	@staticmethod
	def findNClosest(alpha, delta, tableDef, n, fields, searchRadius=5):
		"""returns the n objects closest around alpha, delta in table.

		n is the number of items returned, with the closest ones at the
		top, fields is a sequence of desired field names, searchRadius
		is a radius for the initial q3c search and will need to be
		lowered for dense catalogues and possibly raised for sparse ones.

		The last item of each row is the distance of the object from
		the query center in degrees.

		The query depends on postgastro extension.
		"""
		q = base.SimpleQuerier()
		raField = tableDef.getColumnByUCDs("pos.eq.ra;meta.main", 
			"POS_EQ_RA_MAIN").name
		decField = tableDef.getColumnByUCDs("pos.eq.dec;meta.main", 
			"POS_EQ_RA_MAIN").name
		res = q.query("SELECT %s,"
				" celDistDD(%s, %s, %%(alpha)s, %%(delta)s) as dist_"
				" FROM %s WHERE"
				" q3c_radial_query(%s, %s, %%(alpha)s, %%(delta)s,"
				" %%(searchRadius)s)"
				" ORDER BY dist_ LIMIT %%(n)s"%
					(",".join(fields), raField, decField, tableDef.getQName(),
						raField, decField),
			locals()).fetchall()
		return res

rscdef.registerRMixin(Q3CIndex())
