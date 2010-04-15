"""
Exceptions and helper functions for adql processing.

This module should be clean for from import *
"""

class Error(Exception):
	pass

class NotImplementedError(Error):
	"""is raised for features we don't (yet) support.
	"""

class ColumnNotFound(Error):
	"""is raised if a column name cannot be resolved.
	"""

class TableNotFound(Error):
	"""is raised when a table name cannot be resolved.
	"""

class AmbiguousColumn(Error):
	"""is raised if a column name matches more than one column in a
	compound query.
	"""

class NoChild(Error):
	"""is raised if a node is asked for a non-existing child.
	"""
	def __init__(self, searchedType, toks):
		self.searchedType, self.toks = searchedType, toks
	
	def __str__(self):
		return "No %s child found in %s"%(self.searchedType, self.toks)

class MoreThanOneChild(NoChild):
	"""is raised if a node is asked for a unique child but has more than
	one.
	"""
	def __str__(self):
		return "Multiple %s children found in %s"%(self.searchedType, 
			self.toks)

class BadKeywords(Error):
	"""is raised when an ADQL node is constructed with bad keywords.

	This is a development help and should not occur in production code.
	"""

class UfuncError(Error):
	"""is raised if something is wrong with a call to a user defined
	function.
	"""

class GeometryError(Error):
	"""is raised if something is wrong with a geometry.
	"""

class RegionError(GeometryError):
	"""is raised if a region specification is in some way bad.
	"""

class FlattenError(Error):
	"""is raised when something cannot be flattened.
	"""


class FieldInfo(object):
	"""is a container for meta information on columns.

	It is constructed with a unit, a ucd and userData.  UserData is
	a sequence of opaque objects.  A FieldInfo combined from more than 
	one FieldInfo will have all userDatas of the combined FieldInfos in
	its userData attribute.
	"""
	def __init__(self, unit, ucd, userData=(), tainted=False, stc=None):
		self.ucd = ucd
		self.unit = unit
		self.stc = stc
		self.userData = userData
		self.tainted = tainted
	
	def __repr__(self):
		return "FieldInfo(%s, %s, %s)"%(repr(self.unit), repr(self.ucd),
			repr(self.userData))

	@staticmethod
	def combineUserData(fi1, fi2):
		return fi1.userData+fi2.userData

	@staticmethod
	def combineSTC(fi1, fi2):
		"""tries to find a common STC system for fi1 and fi2.

		Two STC systems are compatible if at least one is None or if they
		are equal.

		If this method discovers incompatible systems, it will create a
		new STC object with a "broken" attribute containing some sort
		for error message.
		"""
		if fi1.stc is None and fi2.stc is None:
			return None
		elif fi2.stc is None or fi1.stc==fi2.stc:
			return fi1.stc
		elif fi1.stc is None:
			return fi2.stc
		else: # Trouble: stcs not equal but given, warn and blindly return
		      # fi1's stc
			res = fi1.stc.change()
			res.broken = ("This STC info is bogus.  It is the STC from an"
				" expression combining two different systems.")
			return res

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
		newUserData = cls.combineUserData(fi1, fi2)
		stc = cls.combineSTC(fi1, fi2)

		if fi1 is dimlessFieldInfo and fi2 is dimlessFieldInfo:
			return dimlessFieldInfo
		elif unit1=="" and unit2=="":
			return cls("", "", newUserData, stc=stc)
		elif unit1=="":
			return cls(unit2, fi2.ucd, newUserData, tainted=True, stc=stc)
		elif unit2=="":
			return cls(unit1, fi1.ucd, newUserData, tainted=True, stc=stc)
		else:
			if opr=="/":
				unit2 = "(%s)"%unit2
			return cls(unit1+opr+unit2, "", newUserData,
				tainted=fi1.tainted or fi2.tainted, stc=stc)
	
	@classmethod
	def fromAddExpression(cls, opr, fi1, fi2):
		"""returns a new FieldInfo built from the addition-like operator
		opr and the two field infos.
			
		If both UCDs and units are the same, they are kept.  Otherwise,
		they are cleared and the fieldInfo is tainted.
		"""
		unit, ucd, taint = "", "", False
		stc = cls.combineSTC(fi1, fi2)
		if fi1.unit==fi2.unit:
			unit = fi1.unit
		else:
			taint = True
		if fi1.ucd==fi2.ucd:
			ucd = fi1.ucd
		else:
			taint = True
		return cls(unit, ucd, cls.combineUserData(fi1, fi2), taint, stc)

	def copyModified(self, **kwargs):
		res = FieldInfo(self.unit, self.ucd, self.userData, 
			self.tainted, self.stc)
		for k,v in kwargs.items():
			setattr(res, k, v)
		return res


dimlessFieldInfo = FieldInfo("", "")


def getUniqueMatch(matches, colName):
	"""returns the only item of matches if there is exactly one, raises an
	appropriate exception if not.
	"""
	if len(matches)==1:
		return matches[0]
	elif not matches:
		raise ColumnNotFound(colName)
	else:
		matches = set(matches)
		if len(matches)!=1:
			raise AmbiguousColumn(colName)
		else:
			return matches.pop()
