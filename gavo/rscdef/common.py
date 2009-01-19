"""
Common items used by resource definition objects.
"""

import re

from gavo import base


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

	def __init__(self):
		base.AttributeDef.__init__(self, "rd", None, "The parent"
			" resource descriptor")
	
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
		description="DB roles that can read data stored here")
	_allRoles = RoleListAttribute("allRoles", 
		default=base.getConfig("db", "maintainers"),
		description="DB roles that can read and write data stored here")


class ColumnList(list):
	"""is a list of column.Columns (or derived classes) that takes
	care that no duplicates (in name) occur.

	If you add a field with the same dest to a ColumnList, the previous
	instance will be overwritten.  The idea is that you can override
	ColumnList in, e.g., interfaces later on.

	Also, two ColumnLists are considered equal if they contain the
	same names.
	"""
	internallyUsedFields = set(["feedbackSelect"])

	def __init__(self, *args):
		list.__init__(self, *args)
		self.nameIndex = dict([(c.name, ct) for ct, c in enumerate(self)])

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
	
	def extend(self, seq):
		for item in seq:
			self.append(item)

	def getColumnByName(self, name):
		"""returns the column with name.

		It will raise a KeyError if no such column exists.
		"""
		return self[self.nameIndex[name]]

	def getColumnsByUCD(self, ucd):
		"""returns all columns having ucd.
		"""
		return [item for item in self if item.ucd==ucd]

	def getColumnByUCD(self, ucd):
		"""retuns the single, unique column having ucd.

		It returns a LiteralParseError if there is no such column.
		"""
		cols = self.getColumnsByUCD(ucd)
		if len(cols)==1:
			return cols[0]
		elif cols:
			raise base.LiteralParseError("More than one column for %s"%ucd,
				"ucd", ucd)
		else:
			raise base.LiteralParseError("No column for %s"%ucd, "ucd", ucd)


class ColumnListAttribute(base.StructListAttribute):
	"""is an adapter from a ColumnList to a structure attribute.
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
	def __init__(self, **kwargs):
		base.AtomicAttribute.__init__(self, name="namePath", description=
			"Id of an element tried to satisfy requests for names in"
			" original attributes.", **kwargs)
	
	def iterParentMethods(self):
		def resolveName(instance, context, id):
			if instance.namePath is None:
				raise base.StructureError("No namePath here")
			return base.resolveId(context, instance.namePath+"."+id)
		yield "resolveName", resolveName
					
	def parse(self, value):
		return value
	
	def unparse(self, value):
		return value


identifierPat = re.compile("[A-Za-z_][A-Za-z_0-9]*$")
