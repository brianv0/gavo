"""
Exceptions and helper functions for adql processing.

This module should be clean for from import *
"""

class Error(Exception):
	pass

class ColumnNotFound(Error):
	"""will be raised if a column name cannot be resolved.
	"""

class AmbiguousColumn(Error):
	"""will be raised if a column name matches more than one column in a
	compound query.
	"""

class NoChild(Error):
	"""will be raised if a node is asked for a non-existing child.
	"""

class MoreThanOneChild(Error):
	"""will be raised if a node is asked for a unique child but has more than
	one."""


class FieldInfo(object):
	"""is a container for meta information on columns.

	It is constructed with a unit, a ucd and userData.  UserData is
	a sequence of opaque objects.  A FieldInfo combined from more than 
	one FieldInfo will have all userDatas of the combined FieldInfos in
	its userData attribute.
	"""
	tainted = False

	def __init__(self, unit, ucd, userData=(), tainted=False):
		self.ucd = ucd
		self.warnings = []
		self.errors = []
		self.userData = userData
		self.unit = unit
		self.tainted = tainted
	
	def __repr__(self):
		return "FieldInfo(%s, %s, %s)"%(repr(self.unit), repr(self.ucd),
			repr(self.userData))

	@classmethod
	def fromMulExpression(cls, opr, fi1, fi2):
		"""returns a new FieldInfo built from the multiplication-like operator opr
		and the two field infos.

		The unit is unit1 opr unit2 unless we have a dimless (empty unit), in
		which case we keep the unit but turn the tainted flag on, unless both
		are empty.

		The ucd is always empty unless it's a simple dimless multiplication,
		in which case the ucd of the non-dimless is kept (but the info is
		tainted).
		"""
		unit1, unit2 = fi1.unit, fi2.unit
		if fi1 is dimlessFieldInfo and fi2 is dimlessFieldInfo:
			return dimlessFieldInfo
		elif unit1=="" and unit2=="":
			return cls("", "", fi1.userData+fi2.userData)
		elif unit1=="":
			return cls(unit2, fi2.ucd, fi1.userData+fi2.userData, tainted=True)
		elif unit2=="":
			return cls(unit1, fi1.ucd, fi1.userData+fi2.userData, tainted=True)
		else:
			if opr=="/":
				unit2 = "(%s)"%unit2
			return cls(unit1+opr+unit2, "", fi1.userData+fi2.userData,
				tainted=fi1.tainted or fi2.tainted)
	
	@classmethod
	def fromAddExpression(cls, opr, fi1, fi2):
		"""returns a new FieldInfo built from the addition-like operator
		opr and the two field infos.
			
		If both UCDs and units are the same, they are kept.  Otherwise,
		they are cleared and the fieldInfo is tainted.
		"""
		unit, ucd, taint = "", "", False
		if fi1.unit==fi2.unit:
			unit = fi1.unit
		else:
			taint = True
		if fi1.ucd==fi2.ucd:
			ucd = fi1.ucd
		else:
			taint = True
		return cls(unit, ucd, fi1.userData+fi2.userData, taint)


dimlessFieldInfo = FieldInfo("", "")


