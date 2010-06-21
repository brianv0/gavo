"""
Bindings for the pgsphere libarary and psycopg2.

Basically, once per program run, you need to call preparePgSphere(connection),
and you're done.

All native representation is in rad.
"""

# XXX TODO: handle remaining pgsphere types.

import math
import re

import psycopg2
from psycopg2.extensions import (adapt, register_adapter, AsIs, register_type,
	new_type)

from gavo.utils import codetricks
from gavo.utils import excs
from gavo.utils.mathtricks import DEG


class TwoSBoxes(excs.ExecutiveAction):
	"""is raised when an SBox is constructed from center and size such that
	it overlaps the pole.
	"""
	def __init__(self, box1, box2):
		self.box1, self.box2 = box1, box2


def _query(conn, query, pars=None):
	c = conn.cursor()
	c.execute(query, pars)
	res = list(c)
	return res


class PgSAdapter(object):
	"""A base class for objects adapting pgSphere objects.

	The all need a pgType attribute and two static methods
	_adaptToPgSphere(obj) and _castFromPgSphere(value, cursor).

	You must also define a sequence checkedAttributes; all attributes
	metioned there must be equal for two adapted values to be equal (equality
	testing here really is mainly for unit tests with hand-crafted values).
	"""
	pgType = None

	def __eq__(self, other):
		if self.__class__!=other.__class__:
			return False
		for attName in self.checkedAttributes:
			if getattr(self, attName)!=getattr(other, attName):
				return False
		return True

	def __ne__(self, other):
		return not self==other


class SPoint(PgSAdapter):
	"""A point on a sphere from pgSphere.

	The first constructor accepts a pair of (alpha, delta), angles are in rad.

	You can optionally pass a "unit" argument.  This is simply multiplied
	to each coordinate.
	"""
	pgType = "spoint"
	checkedAttributes = ["x", "y"]
	pattern = re.compile(r"\s*\(\s*([0-9.e-]+)\s*,\s*([0-9.e-]+)\s*\)")

	def __init__(self, x, y):
		self.x, self.y = float(x), float(y)

	def __repr__(self):
		return "SPoint(%r, %r)"%(self.x, self.y)

	@staticmethod
	def _adaptToPgSphere(spoint):
		return AsIs("spoint '(%f,%f)'"%(spoint.x, spoint.y))
	
	@classmethod
	def _castFromPgSphere(cls, value, cursor):
		if value is not None:
			return cls(*map(float, cls.pattern.match(value).groups()))
	
	@classmethod
	def fromDegrees(cls, x, y):
		return cls(x*DEG, y*DEG)

	def asSTCS(self, systemString):
		return "Position %s %f %f"%(systemString, self.x/DEG, self.y/DEG)

	def asPgSphere(self):
		return "spoint '(%.10f,%.10f)'"%(self.x, self.y)

	def p(self):   # helps below
		return "(%r, %r)"%(self.x, self.y)


class SCircle(PgSAdapter):
	"""A spherical circle from pgSphere.

	The constructor accepts an SPoint center and a radius in rad.
	"""
	pgType = "scircle"
	checkedAttributes = ["center", "radius"]
	pattern = re.compile("<(\([^)]*\))\s*,\s*([0-9.e-]+)>")

	def __init__(self, center, radius):
		self.center, self.radius = center, float(radius)

	@staticmethod
	def _adaptToPgSphere(sc):
		return AsIs("scircle '< %s, %r >'"%(sc.center.p(), sc.radius))
	
	@classmethod
	def _castFromPgSphere(cls, value, cursor):
		if value is not None:
			pt, radius = cls.pattern.match(value).groups()
			return cls(SPoint._castFromPgSphere(pt, cursor), radius)

	def asSTCS(self, systemString):
		return "Circle %s %f %f %f"%(systemString, 
			self.center.x/DEG, self.center.y/DEG,
			self.radius/DEG)

	def asPgSphere(self):
		return "scircle '< (%.10f, %.10f), %.10f >'"%(
			self.center.x, self.center.y, self.radius)


class SPoly(PgSAdapter):
	"""A spherical polygon from pgSphere.

	The constructor accepts a list points of SPoints.
	"""
	pgType = "spoly"
	checkedAttributes = ["points"]
	pattern = re.compile("\([^)]+\)")

	def __init__(self, points):
		self.points = points

	@staticmethod
	def _adaptToPgSphere(spoly):
		return AsIs("spoly '{%s}'"%(", ".join(p.p() for p in spoly.points)))
	
	@classmethod
	def _castFromPgSphere(cls, value, cursor):
		if value is not None:
			return cls([SPoint._castFromPgSphere(ptLit, cursor)
				for ptLit in cls.pattern.findall(value)])

	def asSTCS(self, systemString):
		return "Polygon %s %s"%(systemString, 
			" ".join("%f %f"%(p.x, p.y) for p in self.points))


	def asPgSphere(self):
		return "spoly '{%s}'"%(",".join("(%.10f,%.10f)"%(p.x, p.y)
			for p in self.points))


class SBox(PgSAdapter):
	"""A spherical box from pgSphere.

	The constructor accepts the two corner points.
	"""
	pgType = "sbox"
	checkedAttributes = ["corner1", "corner2"]
	pattern = re.compile("\([^()]+\)")

	def __init__(self, corner1, corner2):
		self.corner1, self.corner2 = corner1, corner2

	def __repr__(self):
		return "sbox(%r,%r)"%(self.corner1, self.corner2)

	@staticmethod
	def _adaptToPgSphere(sbox):
		return AsIs("sbox '(%s, %s)'"%(sbox.corner1.p(), sbox.corner2.p()))

	@classmethod
	def _castFromPgSphere(cls, value, cursor):
		if value is not None:
			return cls(*[SPoint._castFromPgSphere(ptLit, cursor)
				for ptLit in cls.pattern.findall(value)])

	@classmethod
	def fromSIAPPars(cls, ra, dec, raSize, decSize):
		"""returns an SBox corresponding to what SIAP passes in.

		In particular, all values are in degrees, and a cartesian projection
		is assumed.

		This is for use with SIAP and tries to partially implement that silly
		prescription of "folding" over at the poles.  If that happens,
		a TwoSBoxes exception is raised.  It contains two SBoxes that
		should be ORed.  I agree that sucks.  Let's fix SIAP.
		"""
		if 90-abs(dec)<0.1:  # Special handling at the pole
			raSize = 360
		else:
			raSize = raSize/math.cos(dec*DEG)
		decSize = abs(decSize) # inhibit auto swapping of points
		minRA, maxRA = ra-raSize/2., ra+raSize/2.
		bottom, top = dec-decSize/2., dec+decSize/2.
		# folding over at the poles: raise an exception with two boxes,
		# and let upstream handle it.  Foldover on both poles is not supported.
		# All this isn't really thought out and probably doesn't work in
		# many interesting cases.
		# I hate that folding over.
		if bottom<-90 and top>90:
			raise ValueError("Cannot fold over at both poles")
		elif bottom<-90:
			raise TwoSBoxes(
				cls(
					SPoint.fromDegrees(minRA, -90), 
					SPoint.fromDegrees(maxRA, top)),
				cls(
					SPoint.fromDegrees(180+minRA, -90),
					SPoint.fromDegrees(180+maxRA, top)))
		elif top>90:
			raise TwoSBoxes(
				cls(
					SPoint.fromDegrees(minRA, bottom), 
					SPoint.fromDegrees(maxRA, 90)),
				cls(
					SPoint.fromDegrees(180+minRA, bottom),
					SPoint.fromDegrees(180+maxRA, 90)))
		return cls(SPoint.fromDegrees(minRA, bottom), 
			SPoint.fromDegrees(maxRA, top))

	def asSTCS(self, systemString):
		raise NotImplementedError("PositionInterval is tricky between"
			" ADQL, TAP and STC-S")



_getPgSClass = codetricks.buildClassResolver(PgSAdapter, globals().values(),
	key=lambda obj: obj.pgType, default=PgSAdapter)


def preparePgSphere(conn):
	if hasattr(psycopg2, "_pgsphereLoaded"):
		return
	try:
		oidmap = _query(conn, 
			"SELECT typname, oid"
			" FROM pg_type"
			" WHERE typname ~ '^s(point|trans|circle|line|ellipse|poly|path|box)'")
		for typeName, oid in oidmap:
			cls = _getPgSClass(typeName)
			if cls is not PgSAdapter:  # base class is null value
				register_adapter(cls, cls._adaptToPgSphere)
				register_type(
					new_type((oid,), "spoint", cls._castFromPgSphere))
			psycopg2._pgsphereLoaded = True
	except:
		psycopg2._pgsphereLoaded = False
		raise
