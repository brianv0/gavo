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

	def completeElement(self, ctx):
		if self.restrictedMode and (
				self.formatter
				or self.select):
			raise base.RestrictedElement(self.name_, hint="formatter and select"
				" attributes on output fields are not allowed in restricted mode.")
		if self.select is base.Undefined:
			self.select = self.name
		self._completeElementNext(OutputField, ctx)

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

	def __init__(self, parent, **kwargs):
		rscdef.TableDef.__init__(self, parent, **kwargs)
		try:
			self.namePath = self.parent.queriedTable.getFullId()
		except (AttributeError, base.StructureError):
			try:
				self.namePath = self.parent.core.outputTable.getFullId()
			except (AttributeError, base.StructureError):
				self.namePath = None

	def _getSourceTable(self):
		"""returns a tableDef object to be used as a column source.

		The rules are described at the fromTable attribute.
		"""
		try:
			return self.parent.queriedTable
		except AttributeError:  # not a TableBasedCore
			try:
				res =  self.parent.core.outputTable
				return res
			except AttributeError:  # not a service
				return _EMPTY_TABLE

	def _addNames(self, ctx, names):
		# since autoCols is not copyable, we can require
		# that _addNames only be called when there's a real parse context.
		if ctx is None:
			raise StructureError("outputTable autocols is"
				" only available with a parse context")
		for name in names:
			# names may refer to params or to columns, sort
			# things out here.
			refOb = ctx.resolveId(name, self)
			if refOb.name_=="param":
				self.feedObject("param", refOb.copy(self))
			else:
				self.feedObject("outputField", OutputField.fromColumn(refOb))

	def completeElement(self, ctx):
		if self.autoCols:
			self._addNames(ctx, self.autoCols)

		if self.verbLevel:
			table = self._getSourceTable()
			for col in table.columns:
				if col.verbLevel<=self.verbLevel:
					self.feedObject("outputField", OutputField.fromColumn(col))
			for par in table.params:
				if par.verbLevel<=self.verbLevel:
					self.feedObject("param", par.copy(self))

		self._completeElementNext(OutputTableDef, ctx)

	@classmethod
	def fromColumns(cls, columns, **kwargs):
		return rscdef.TableDef.fromColumns([OutputField.fromColumn(c)
			for c in columns])

	@classmethod
	def fromTableDef(cls, tableDef, ctx):
		return cls(None, columns=[OutputField.fromColumn(c) for c in tableDef],
			forceUnique=tableDef.forceUnique, dupePolicy=tableDef.dupePolicy,
			primary=tableDef.primary, params=tableDef.params).finishElement(ctx)
