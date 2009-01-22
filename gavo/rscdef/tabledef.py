"""
Description and definition of tables.
"""

import itertools

from gavo import base
from gavo.base import codetricks
from gavo.base import structure
from gavo.rscdef import column
from gavo.rscdef import common
from gavo.rscdef import macros
from gavo.rscdef import mixins
from gavo.rscdef import rowtriggers
from gavo.rscdef import scripting


class IgnoreThisRow(Exception):
	"""is raised by TableDef.validateRow if a row should be ignored.
	This exception must be caught upstream.
	"""


class DBIndex(base.Structure):
	"""is an index in the database.
	"""
	name_ = "index"

	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="Name of the index (defaults to something computed from"
			" columns)", copyable=True)
	_columns = base.StringListAttribute("columns", description=
		"Table columns taking part in the index (must be given even if there"
		" is an expression building the index", copyable=True)
	_cluster = base.BooleanAttribute("cluster", default=False,
		description="Cluster the table according to this index?",
		copyable=True)
	_code = base.DataContent(copyable=True)

	def completeElement(self):
		self._completeElementNext(DBIndex)
		if not self.columns:
			raise base.StructureError("Index without columns is verboten.")
		if self.name is base.Undefined:
			self.name = "%s_%s"%(self.parent.id, "_".join(self.columns))
		if not self.content_:
			self.content_ = "%s"%",".join(self.columns)


class ColumnTupleAttribute(base.StringListAttribute):
	"""is a tuple of column names.

	In a validate method, it checks that the names actually are in parent's
	fields.
	"""
	def iterParentMethods(self):
		"""adds a getPrimaryIn method to the parent class.

		This function will return the value of the primary key in a row
		passed.  The whole thing is a bit dense in that I want to compile
		that method to avoid having to loop every time it is called.  This
		compilation is done in a descriptor -- ah well, probably it's a waste
		of time anyway.
		"""
		def makeGetPrimaryFunction(instance):
			funcSrc = ('def getPrimaryIn(row):\n'
				'	return (%s)')%(" ".join(['row["%s"],'%name
					for name in getattr(instance, self.name_)]))
			return codetricks.compileFunction(funcSrc, "getPrimaryIn")

		def getPrimaryIn(self, row):
			try:
				return self.__getPrimaryIn(row)
			except AttributeError:
				self.__getPrimaryIn = makeGetPrimaryFunction(self)
				return self.__getPrimaryIn(row)
		yield "getPrimaryIn", getPrimaryIn

	def validate(self, parent):
		for colName in getattr(parent, self.name_):
			try:
				parent.getColumnByName(colName)
			except KeyError:
				raise base.LiteralParseError("Column tuple component %s is"
					" not in parent table"%colName, self.name_, colName)


class TableDef(base.Structure, base.MetaMixin, common.RolesMixin,
		scripting.ScriptingMixin, macros.StandardMacroMixin):
	"""is a descriptor for a table.

	These descriptors work for both on-disk and in-memory tables, though
	some attributes might be ignored for the in-memory ones.
	"""
	name_ = "table"

	# We don't want to force people to come up with an id for all their
	# internal tables but want to avoid writing default-named tables to
	# the db.  Thus, the default is not a valid sql identifier.
	_id = base.IdAttribute("id", default=base.NotGiven, description=
		"Name of the table (must be SQL-legal for onDisk tables)")
	_rd = common.RDAttribute()
	_cols =  common.ColumnListAttribute("columns",
		childFactory=column.Column, description="Column definitions",
		copyable=True)
	_onDisk = base.BooleanAttribute("onDisk", False, description=
		"Does this table reside in the database?")  # this must not be copyable
		  # since queries might copy the tds and havoc would result if the queries
		  # were to end up on disk.
	_adql = base.BooleanAttribute("adql", False, description=
		"Should this table be available for ADQL queries?")
	_forceUnique = base.BooleanAttribute("forceUnique", False, description=
		"Enforce dupe policy for primary key (see dupePolicy)")
	_dupePolicy = base.EnumeratedUnicodeAttribute("dupePolicy",
		"check", ["check", "drop", "overwrite"], description=
		"Handle duplicate rows with identical primary keys manually by"
		" raising an error if existing and new rows are not identical (check),"
		" dropping the new one (drop), or overwriting the old one (overwrite)")
	_primary = ColumnTupleAttribute("primary", default=(),
		description="Comma separated names of columns making up the primary key.")
	_indices = base.StructListAttribute("indices", childFactory=DBIndex,
		description="Indices defined on this table", copyable=True)
	_system = base.BooleanAttribute("system", default=False,
		description="Do not drop this table when importing")
	_ignoreOn = base.StructAttribute("ignoreOn", default=None, copyable=True,
		description="Conditions for excluding records from being written to the"
			" DB.  Note that they are only evaluated if validation is enabled.",
		childFactory=rowtriggers.IgnoreOn)
	_ref = base.RefAttribute()
	_mixins = mixins.MixinAttribute()
	_original = base.OriginalAttribute()
	_namePath = common.NamePathAttribute()

	validWaypoints = set(["preIndex", "preIndexSQL", "viewCreation", 
		"afterDrop"])

	def __iter__(self):
		return iter(self.columns)

	def __contains__(self, name):
		try:
			self.columns.getColumnByName(name)
		except KeyError:
			return False
		return True

	def completeElement(self):
		# allow iterables to be passed in for columns and convert them
		# to a ColumnList here
		if not isinstance(self.columns, common.ColumnList):
			self.columns = common.ColumnList(self.columns)
		if self.id is base.NotGiven:
			self.id = hex(id(self))[2:]
		self._completeElementNext(TableDef)

	def onElementComplete(self):
		if self.adql:
			self.readRoles = self.readRoles | base.getConfig("db", "adqlRoles")
		self.dictKeys = [c.name for c in self]
		self.indexedColumns = set()
		for index in self.indices:
			self.indexedColumns |= set(index.columns)
		if self.primary:
			self.indexedColumns |= set(self.primary)
		self._onElementCompleteNext(TableDef)
	
	def macro_curtable(self):
		"""returns the qualified name of the current table.
		"""
		return self.getQName()

	def macro_tablename(self):
		"""returns the unqualified name of the current table.
		"""
		return self.id

	def macro_nameForUCD(self, ucd):
		"""returns the (unique!) name of the field having ucd in this table.

		If there is no or more than one field with the ucd in this table,
		we raise an exception.
		"""
		fields = self.getColumnsByUCD(ucd)
		if len(fields)!=1:
			raise base.Error("More than one or no field with ucd"
				" %s in this table"%ucd)
		return fields[0].name

	def getQName(self):
		if self.rd is None:
			raise base.Error("TableDefs without resource descriptor"
				" have no qualified names")
		return "%s.%s"%(self.rd.schema, self.id)

	def validateRow(self, row):
		"""checks that row is complete and complies with all known constraints on
		the columns

		The function raises a ValidationError with an appropriate message
		and the relevant field if not.
		"""
		for column in self:
			if column.name not in row:
				raise base.ValidationError("Column %s missing"%column.name,
					column.name, row)
			try:
				column.validateValue(row[column.name])
			except base.ValidationError, ex:
				ex.row = row
				raise
		if self.ignoreOn:
			if self.ignoreOn(row):
				raise IgnoreThisRow(row)

	def getFieldIndex(self, fieldName):
		"""returns the index of the field named fieldName.
		"""
		return self.columns.getFieldIndex(fieldName)

	def getColumnByName(self, name):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnByName(name)

	def getColumnsByUCD(self, ucd):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnsByUCD(ucd)

	def getColumnByUCD(self, ucd):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnByUCD(ucd)

	def makeRowFromTuple(self, dbTuple):
		"""returns a row (dict) from a row as returned from the database.
		"""
		return dict(itertools.izip(self.dictKeys, dbTuple))
	
	def processMixinsLate(self):
		for mixinName in self.mixins:
			mixins.getMixin(mixinName).processLate(self)
