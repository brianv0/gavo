"""
VOTable-style groups for RD tables.
"""

from gavo import base
from gavo.base import attrdef
from gavo.rscdef import column
from gavo.rscdef import common


class Group(base.Structure):
	"""A group is a collection of columns, parameters and other groups 
	with a dash of metadata.

	Within a group, you can refer to columns or params of the enclosing table 
	by their names.  Nothing outside of the enclosing table can be
	part of a group.

	Rather than referring to params, you can also embed them into a group;
	they will then *not* be present in the embedding table.

	Groups may contain groups.

	One application for this is grouping input keys for the form renderer.
	For such groups, you probably want to give the label property (and
	possibly cssClass).
	"""
	name_ = "group"

	_name = column.ColumnNameAttribute("name", 
		default=None,
		description="Name of the column (must be SQL-valid for onDisk tables)",
		copyable=True)

	_ucd = base.UnicodeAttribute("ucd", 
		default=None, 
		description="The UCD of the group", 
		copyable=True)

	_description = base.NWUnicodeAttribute("description", 
		default=None, 
		copyable=True,
		description="A short (one-line) description of the group")

	_utype = base.UnicodeAttribute("utype", 
		default=None, 
		description="A utype for the group", 
		copyable=True)

	_columnRefs = base.StringListAttribute("columnRefs",
		description="Names of table columns belonging to this group",
		copyable=True)

	_paramRefs = base.StringListAttribute("paramRefs",
		description="Names of table parameters belonging to this group",
		copyable=True)

	_params = common.ColumnListAttribute("params",
		childFactory=column.Param, 
		description="Immediate param elements for this group (use paramref"
		" to reference params defined in the parent table)",
		copyable=True)

	_groups = base.StructListAttribute("groups",
		childFactory=attrdef.RECURSIVE,
		description="Sub-groups of this group (names are still referenced"
		" from the enclosing table)",
		copyable=True,
		xmlName="group")
	
	_props = base.PropertyAttribute(copyable=True)

	@property
	def table(self):
		"""the table this group lives in.

		For nested groups, this still is the ancestor table.
		"""
		try:
			# (re) compute the table we belong to if there's no table cache
			# or determination has failed so far.
			if self.__tableCache is None:
				raise AttributeError
		except AttributeError:
			# find something that has columns (presumably a table) in our
			# ancestors.  I don't want to check for a TableDef instance
			# since I don't want to import rscdef.table here (circular import)
			# and things with column and params would work as well.
			anc = self.parent
			while anc:
				if hasattr(anc, "columns"):
					self.__tableCache = anc
					break
				anc = anc.parent
			else:
				self.__tableCache = None
		return self.__tableCache

	def onParentComplete(self):
		"""checks that param and column names can be found in the parent table.
		"""
		# defer validation for sub-groups (parent group will cause validation)
		if isinstance(self.parent, Group):
			return
		# forgo validation if the group doesn't have a table
		if self.table is None:
			return

		try:
			for col in self.iterColumns():
				pass
			for par in self.iterParams():
				pass
		except base.NotFoundError, msg:
			raise base.StructureError(
				"No param or field %s in found in table %s"%(
					msg.what, self.table.id))

		for group in self.groups:
			group.onParentComplete()

	def iterColumns(self):
		"""iterates over columns within this group.
		"""
		table = self.table
		for name in self.columnRefs:
			yield table.columns.getColumnByName(name)
	
	def iterParams(self):
		"""iterates over all params within this group.

		This includes both params refereced in the parent table and immediate
		params.
		"""
		table = self.table
		for name in self.paramRefs:
			yield table.params.getColumnByName(name)
		for par in self.params:
			yield par

