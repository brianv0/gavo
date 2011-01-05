"""
VOTable-style groups for RD tables.
"""

from gavo import base
from gavo.base import parsecontext
from gavo.rscdef import column


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

	_columns = base.ReferenceListAttribute("columns",
		description="The columns belonging to this group",
		forceType=column.Column,
		aliases=["colref", "column"])

	_params = base.ReferenceListAttribute("params",
		description="The params belonging to this group, as references or"
		" inline",
		forceType=column.Param,
		aliases=["paramref", "param"])

	_groups = base.ReferenceListAttribute("groups",
		description="Sub-groups, or references to them",
		forceType=parsecontext.RECURSIVE,
		aliases=["group"])

	@property
	def table(self):
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

	# this resolveName definition makes groups have an automatic name path
	# to the parent table.
	def resolveName(self, context, id):
		return parsecontext.resolveNameBased(self.table, id)
