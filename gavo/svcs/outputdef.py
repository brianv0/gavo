"""
Output tables and their components.
"""

from gavo import base 
from gavo import rscdef 

_EMPTY_TABLE = base.makeStruct(rscdef.TableDef, id="<builtin empty table>")


class OutputField(rscdef.Column):
	"""A column for defining the output of a service.

	It adds some attributes useful for rendering results, plus functionality
	specific to certain cores.

	The optional formatter overrides the standard formatting code in HTML
	(which is based on units, ucds, and displayHints).  This is a standard
	nevow renderer, having ctx and data as arguments.

	Here's an example for generating a link to another service using this
	facility::

	  <outputField name="more" 
	      select="array[centerAlpha,centerDelta] as more" tablehead="More"
	      description="More exposures near the center of this plate">
	    <formatter><![CDATA[
	      return T.a(href=base.makeSitePath("/lswscans/res/positions/q/form?"
	        "POS=%s,%s&SIZE=1&INTERSECT=OVERLAPS&cutoutSize=0.5"
		      "&__nevow_form__=genForm"%tuple(data)
		      ))["More"] ]]>
	    </formatter>
	  </outputField>
	"""
	name_ = "outputField"

	_formatter = base.UnicodeAttribute("formatter", description="Function"
		" body to render this item to HTML.", copyable=True)
	_wantsRow = base.BooleanAttribute("wantsRow", description="Does"
		" formatter expect the entire row rather than the colum value only?",
		copyable="True")
	_select = base.UnicodeAttribute("select", description="Use this SQL"
		" fragment rather than field name in the select list of a DB based"
		" core.", default=base.Undefined, copyable=True)
	_sets = base.StringSetAttribute("sets", description=
		"Output sets this field should be included in; ALL includes the field"
		" in all output sets.",
		copyable=True)

	def __repr__(self):
		return "<OutputField %s>"%repr(self.name)

	def completeElement(self):
		if self.restrictedMode and (
				self.formatter
				or self.select):
			raise base.RestrictedElement(self.name_, hint="formatter and select"
				" attributes on output fields are not allowed in restricted mode.")
		if self.select is base.Undefined:
			self.select = self.name
		self._completeElementNext(OutputField)

	@classmethod
	def fromColumn(cls, col):
		return cls(None, **col.getAttributes(rscdef.Column)).finishElement()


class OutputTableDef(rscdef.TableDef):
	"""A table that has outputFields for columns.
	"""
	name_ = "outputTable"

	_cols = rscdef.ColumnListAttribute("columns", 
		childFactory=OutputField,
		description="Output fields for this table.", 
		aliases=["column"],
		copyable=True)

	_verbLevel = base.IntAttribute("verbLevel", 
		default=None,
		description="Copy over columns from fromTable not"
			" more verbose than this.")

	_autocols = base.StringListAttribute("autoCols", 
		description="Column names obtained from fromTable.")

	_fromTable = base.ReferenceAttribute("fromTable",
		default=base.NotGiven,
		description="Build output fields from the columns of this table;"
		"  if not given, defaults to the queried table for cores that have"
		" one (an emtpy table otherwise), and the core's output table"
		" for services.")

	def _getSourceTable(self):
		"""returns a tableDef object to be used as a column source.

		The rules are described at the fromTable attribute.
		"""
		if self.fromTable is base.NotGiven:
			try:
				return self.parent.queriedTable
			except AttributeError:  # not a TableBasedCore
				try:
					res =  self.parent.core.outputTable
					return res
				except AttributeError:  # not a service
					return _EMPTY_TABLE
		else:
			return self.fromTable

	def _obtainFieldsFrom(self, fieldSource, isWanted):
		"""makes outputFields and params from columns and params in
		fieldSource.
		
		Only those items are used for which isWanted returns true.
		"""
		if fieldSource is base.Undefined:
			raise base.StructureError("Attempting to copy fields from"
				" an undefined source %s's output table."%(self.parent.id))
		for c in fieldSource.columns:
			if isWanted(c):
				self.feedObject("outputField", OutputField.fromColumn(c))
		for p in fieldSource.params:
			if isWanted(p):
				self.feedObject("param", p.copy(self))

	def completeElement(self):
		fromTable = self._getSourceTable()
		if self.autoCols:
			ac = set(self.autoCols)
			self._obtainFieldsFrom(fromTable, lambda c: c.name in ac)
		if self.verbLevel:
			self._obtainFieldsFrom(fromTable, 
				lambda c: c.verbLevel<=self.verbLevel)
		self._completeElementNext(OutputTableDef)

	@classmethod
	def fromColumns(cls, columns, **kwargs):
		return rscdef.TableDef.fromColumns([OutputField.fromColumn(c)
			for c in columns])

	@classmethod
	def fromTableDef(cls, tableDef):
		return cls(None, columns=[OutputField.fromColumn(c) for c in tableDef],
			forceUnique=tableDef.forceUnique, dupePolicy=tableDef.dupePolicy,
			primary=tableDef.primary, params=tableDef.params).finishElement()
