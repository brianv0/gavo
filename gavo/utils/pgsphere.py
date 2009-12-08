"""
Bindings for the pgsphere libarary and psycopg2.

Basically, once per program run, you need to call preparePgSphere(connection),
and you're done.
"""

# XXX TODO: handle remaining pgsphere types.

import re

import psycopg2
from psycopg2.extensions import (adapt, register_adapter, AsIs, register_type,
	new_type)

from gavo.utils import codetricks


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
	"""
	pgType = "spoint"
	checkedAttributes = ["x", "y"]
	pattern = re.compile(r"\s*\(\s*([0-9.e-]+)\s*,\s*([0-9.e-]+)\s*\)")

	def __init__(self, x, y):
		self.x, self.y = float(x), float(y)

	def __repr__(self):
		return "spoint(%r, %r)"%(self.x, self.y)

	def p(self):   # helps below
		return "(%r, %r)"%(self.x, self.y)

	@staticmethod
	def _adaptToPgSphere(spoint):
		return AsIs("spoint '(%f,%f)'"%(spoint.x, spoint.y))
	
	@classmethod
	def _castFromPgSphere(cls, value, cursor):
		if value is not None:
			return cls(*map(float, cls.pattern.match(value).groups()))
	


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
