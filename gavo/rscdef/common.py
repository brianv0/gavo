"""
Common items used by resource definition objects.
"""

import re

from gavo import base
from gavo import utils


class RDAttribute(base.AttributeDef):
	"""is an attribute that gives access to the current rd.

	The attribute is always called rd.  There is no default, but on
	the first access, we look for an ancestor with an rd attribute and
	use that if it exists, otherwise rd will be None.  There currently
	is no way to reset the rd.

	These attributes cannot (yet) be fed, so there's rd="xxx" won't work.
	If we need this, the literal would probably be an id.
	"""
	computed_ = True
	typeDesc_ = "reference to a resource descriptor"

	def __init__(self):
		base.AttributeDef.__init__(self, "rd", None, "The parent"
			" resource descriptor; never set this manually, the value will"
			" be filled in by the software.")
	
	def iterParentMethods(self):
		def _getRD(self):
			if self.parent is None: # not yet adopted, we may want to try again later
				return None
			try:
				return self.__rd
			except AttributeError:
				parent = self.parent
				while parent:
					if hasattr(parent, "rd") and parent.rd is not None:
						self.__rd = parent.rd
						break
					parent = parent.parent
				else:
					self.__rd = None
			return self.__rd
		yield ("rd", property(_getRD))

		def getFullId(self):
			return "%s#%s"%(self.rd.sourceId, self.id)
		yield ("getFullId", getFullId)

	def makeUserDoc(self):
		return None   # don't metion it in docs -- users can't and mustn't set it.


class ResdirRelativeAttribute(base.FunctionRelativePathAttribute):
	"""is a path that is interpreted relative to the current RD's resdir.

	The parent needs an RDAttribute.
	"""
	def __init__(self, name, default=None, description="Undocumented", **kwargs):
		base.FunctionRelativePathAttribute.__init__(self, name, 
			baseFunction=lambda instance: instance.rd.resdir,
			default=default, description=description, **kwargs)


class RoleListAttribute(base.AtomicAttribute):
	"""is an attribute containing a comma separated list of role names.

	There's the special role name "defaults" for whatever default this role 
	list was constructed with.
	"""
	typeDesc_ = "Comma separated list of db roles"

	def __init__(self, name, default, description):
		base.AtomicAttribute.__init__(self, name, base.Computed, description)
		self.realDefault = default
	
	@property
	def default_(self):
		return self.realDefault.copy()

	def parse(self, value):
		roles = set()
		for role in value.split(","):
			role = role.strip()
			if not role:
				continue
			if role=="defaults":
				roles = roles|self.default_
			else:
				roles.add(role)
		return roles
	
	def unparse(self, value):
# It would be nice to reconstruct "defaults" here, but right now it's 
# certainly not worth the effort.
		return ", ".join(value)


class RolesMixin(object):
	"""is a mixin for structures defining database roles.

	We have two types of roles: "All" roles, having all privileges, and "Read"
	roles that have r/o access to objects.  These are kept in two attributes
	given here.
	"""
	_readRoles = RoleListAttribute("readRoles", 
		default=base.getConfig("db", "queryRoles"),
		description="DB roles that can read data stored here.")
	_allRoles = RoleListAttribute("allRoles", 
		default=base.getConfig("db", "maintainers"),
		description="DB roles that can read and write data stored here.")


class ColumnList(list):
	"""A list of column.Columns (or derived classes) that takes
	care that no duplicates (in name) occur.

	If you add a field with the same dest to a ColumnList, the previous
	instance will be overwritten.  The idea is that you can override
	ColumnList in, e.g., interfaces later on.

	Also, two ColumnLists are considered equal if they contain the
	same names.

	After construction, you should set the withinId attribute to
	something that will help make sense of error messages.
	"""
	def __init__(self, *args):
		list.__init__(self, *args)
		self.nameIndex = dict([(c.name, ct) for ct, c in enumerate(self)])
		self.withinId = "unnamed table"

	def __contains__(self, fieldName):
		return fieldName in self.nameIndex

	def __eq__(self, other):
		if isinstance(other, DataFieldList):
			myFields = set([f.name for f in self 
				if f.name not in self.internallyUsedFields])
			otherFields = set([f.name for f in other 
				if f.name not in self.internallyUsedFields])
			return myFields==otherFields
		return False

	def deepcopy(self, newParent):
		"""returns a deep copy of self.

		This means that all child structures are being copied.  In that
		process, they receive a new parent, which is why you need to
		pass one in.
		"""
		return self.__class__([c.copy(newParent) for c in self])

	def getIdIndex(self):
		try:
			return self.__idIndex
		except AttributeError:
			self.__idIndex = dict((c.id, c) for c in self if c.id is not None)
			return self.__idIndex

	def append(self, item):
		"""adds the Column item to the data field list.

		It will overwrite a Column of the same name if such a thing is already
		in the list.  Indices are updated.
		"""
		key = item.name
		if key in self.nameIndex:
			nameInd = self.nameIndex[key]
			assert self[nameInd].name==key, \
				"Someone tampered with ColumnList"
			self[nameInd] = item
		else:
			self.nameIndex[item.name] = len(self)
			list.append(self, item)

	def replace(self, oldCol, newCol):
		ind = 0
		while True:
			if self[ind]==oldCol:
				self[ind] = newCol
				break
			ind += 1
		del self.nameIndex[oldCol.name]
		self.nameIndex[newCol.name] = ind

	def extend(self, seq):
		for item in seq:
			self.append(item)

	def getColumnByName(self, name):
		"""returns the column with name.

		It will raise a NotFoundError if no such column exists.
		"""
		try:
			return self[self.nameIndex[name]]
		except KeyError:
			raise base.NotFoundError(name, what="column", within=self.withinId)

	def getColumnById(self, id):
		"""returns the column with id.

		It will raise a NotFoundError if no such column exists.
		"""
		try:
			return self.getIdIndex()[id]
		except KeyError:
			raise base.NotFoundError(id, what="column", within=self.withinId)

	def getColumnsByUCD(self, ucd):
		"""returns all columns having ucd.
		"""
		return [item for item in self if item.ucd==ucd]

	def getColumnByUCD(self, ucd):
		"""retuns the single, unique column having ucd.

		It raises a ValueError if there is no such column or more than one.
		"""
		cols = self.getColumnsByUCD(ucd)
		if len(cols)==1:
			return cols[0]
		elif cols:
			raise ValueError("More than one column for %s"%ucd)
		else:
			raise ValueError("No column for %s"%ucd)

	def getColumnByUCDs(self, *ucds):
		"""returns the single, unique column having one of ucds.

		This method has a confusing interface.  It sole function is to
		help when there are multiple possible UCDs that may be interesting
		(like pos.eq.ra;meta.main and POS_EQ_RA_MAIN).  It should only be
		used for such cases.
		"""
		for ucd in ucds:
			try:
				return self.getColumnByUCD(ucd)
			except ValueError:
				pass
		raise ValueError("No unique column for any of %s"%", ".join(ucds))


class ColumnListAttribute(base.StructListAttribute):
	"""An adapter from a ColumnList to a structure attribute.
	"""
	@property
	def default_(self):
		return ColumnList()
	
	def getCopy(self, instance, newParent):
		return ColumnList(base.StructListAttribute.getCopy(self,
			instance, newParent))
	
	def replace(self, instance, oldStruct, newStruct):
		if oldStruct.name!=newStruct.name:
			raise base.StructureError("Can only replace fields of the same"
				" name in a ColumnList")
		getattr(instance, self.name_).append(newStruct)


class NamePathAttribute(base.AtomicAttribute):
	"""defines an attribute NamePath used for resolution of "original"
	attributes.

	The NamePathAttribute provides a resolveNamed method as expected
	by base.OriginalAttribute.
	"""
	typeDesc_ = "id reference"

	def __init__(self, **kwargs):
		if "description" not in kwargs:
			kwargs["description"] = ("Reference to an element tried to"
				" satisfy requests for names in id references of this"
				" element's children.")
		base.AtomicAttribute.__init__(self, name="namePath", **kwargs)
	
	def iterParentMethods(self):
		def resolveName(instance, context, id):
			np = instance.namePath
			if np is None and instance.parent:
				np = getattr(instance.parent, "namePath", None)
			if np is None:
				raise base.StructureError("No namePath here")
			res = context.resolveId(np+"."+id)
			return res
		yield "resolveName", resolveName
					
	def parse(self, value):
		return value
	
	def unparse(self, value):
		return value


_atPattern = re.compile("@(%s)"%utils.identifierPattern.pattern[:-1])

def replaceRMKAt(src):
	"""replaces @<identifier> with vars["<identifier>"] in src.

	We do this to support this shortcut in the vicinity of rowmakers (i.e.,
	there and in procApps).
	"""
	return _atPattern.sub(r'vars["\1"]', src)
