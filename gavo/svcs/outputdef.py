"""
Helpers for defining service output
"""

from gavo import base 
from gavo import rscdef 


class OutputField(rscdef.Column):
	"""is a column for defining the output of a service.

	It adds some attributes useful for rendering results, plus functionality
	specific to certain cores.
	"""
	name_ = "outputField"

	_formatter = base.UnicodeAttribute("formatter", description="Function"
		" body to render this item to HTML", copyable=True)
	_wantsRow = base.BooleanAttribute("wantsRow", description="Does"
		"formatter expect the entire row rather than the colum value only?",
		copyable="True")
	_select = base.UnicodeAttribute("select", description="Use this SQL"
		" fragment rather than field name in the select list of a DB based"
		" core", default=base.Undefined, copyable=True)
	_sets = base.StringSetAttribute("sets", description=
		"Output sets this field should be included in",
		copyable=True)
	
	def completeElement(self):
		if self.select is base.Undefined:
			self.select = self.name
		self._completeElementNext(OutputField)

	@classmethod
	def fromColumn(cls, col):
		return cls(None, **col.getAttributes(rscdef.Column)).finishElement()


class OutputTableDef(rscdef.TableDef):
	"""is a TableDefinition that has OutputColumns for columns.
	"""
	name_ = "outputTable"

	_cols = rscdef.ColumnListAttribute("columns", childFactory=OutputField,
		description="Output fields for this table.", aliases=["column"],
		copyable=True)
	_verbLevel = base.IntAttribute("verbLevel", default=None,
		description="Copy over columns from the core's output table not"
			" more verbose than this.")

	def completeElement(self):
		# see if any Column objects were copied into our column and convert
		# them to OutputFields
		for ind, col in enumerate(self.columns):
			if not hasattr(col, "select"):
				self.columns[ind] = OutputField.fromColumn(col)
		self._completeElementNext(OutputTableDef)

	def onParentCompleted(self):
		if self.verbLevel is not None:
			for c in self.parent.core.outputTable:
				self._cols.feedObject(self, OutputField.fromColumn(c))

	@classmethod
	def fromColumns(cls, columns):
		return cls(None, columns=[OutputField.fromColumn(c) for c in tableDef])

	@classmethod
	def fromTableDef(cls, tableDef):
		return cls(None, columns=[OutputField.fromColumn(c) for c in tableDef],
			forceUnique=tableDef.forceUnique, dupePolicy=tableDef.dupePolicy,
			primary=tableDef.primary).finishElement()
