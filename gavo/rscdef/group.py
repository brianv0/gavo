"""
VOTable-style groups for RD tables.
"""

from gavo import base
from gavo.base import parsecontext
from gavo.rscdef import column
from gavo.rscdef import common


class Group(base.Structure):
	"""A group is a collection of columns, parameters and other groups 
	with a dash of metadata.

	Within a group, you can refer to columns of the enclosing table by
	their names.  For params and everything else, you need id on the
	elements you want to refer to.

	Rather than referring to params, you can also embed them into a group;
	they will then *not* be present in the embedding table.

	You could do the same for columns, but again the column would not be
	part of the embedding table, which is almost certainly not what you
	want.

	Groups may contain groups.
	"""
	name_ = "group"

	_name = column.ColumnNameAttribute("name", 
		default=base.Undefined,
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
		description="Names of table columns belonging to this group")

	_paramRefs = base.StringListAttribute("paramRefs",
		description="Names of table parameters belonging to this group")

	_params = common.ColumnListAttribute("params",
		childFactory=column.Param, 
		description="Immediate param elements for this group (use paramref"
		" to reference params defined in the parent table)",
		copyable=True)

	_groups = base.ReferenceListAttribute("groups",
		description="Sub-groups, or references to them",
		forceType=parsecontext.RECURSIVE,
		aliases=["group"])

	@property
	def table(self):
		"""the table this group lives in.

		For nested groups, this still is the ancestor table.
		"""
		try:
			return self.__tableCache
		except AttributeError:
			# find the first non-group ancestor; this (the "table") is used to
			# resolve ids by column name.
			anc = self.parent
			while anc:
				if not isinstance(anc, Group):
					self.__tableCache = anc
					break
				anc = anc.parent
			else:
				self.__tableCache = None
		return self.__tableCache

	def onParentComplete(self):
		"""checks that param and column names can be found in the parent table.
		"""
		try:
			for col in self.iterColumns():
				pass
			for par in self.iterParams():
				pass
		except base.NotFoundError, msg:
			raise base.StructureError(
				"No param or field %s in found in table %s"%(
					msg.what, self.table.id))

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

