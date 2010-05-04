"""
Helpers for defining service output
"""

from gavo import base 
from gavo import rscdef 


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
		return "<OutputField %s>"%self.name

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


class ColRefListAttribute(base.StringListAttribute):
	"""An attribute containing a comma separated list of column names.

	They will be resolved using the same mechanism as original and friends,
	i.e., namePaths count, and you can use hashes.
	"""
	def feed(self, ctx, instance, value):
		self.feedObject(instance, [ctx.resolveId(name, instance=instance
			).copy(parent=instance) for name in self.parse(value)])
	
	def getCopy(self, instance, newParent):
		return [c.copy(parent=newParent)
			for c in getattr(instance, self.name_)]
	

class OutputTableDef(rscdef.TableDef):
	"""A table that has outputFields for columns.
	"""
	name_ = "outputTable"

	_cols = rscdef.ColumnListAttribute("columns", childFactory=OutputField,
		description="Output fields for this table.", aliases=["column"],
		copyable=True)
	_verbLevel = base.IntAttribute("verbLevel", default=None,
		description="Copy over columns from the core's output table not"
			" more verbose than this.")
	_autocols = ColRefListAttribute("autoCols", 
		description="Column names for the output table; this is an abbreviation"
		" for <column original='c1'/><column original='c2'/> etc.  The columns"
		" will always be prepended to columns given in full.")

	def completeElement(self):
		if self.autoCols:
			self.columns = rscdef.ColumnList(self.autoCols+self.columns)
		# see if any Column objects were copied into our column and convert
		# them to OutputFields
		for col in self.columns:
			if not hasattr(col, "wantsRow"):
				self.columns.replace(col, OutputField.fromColumn(col))
		self._completeElementNext(OutputTableDef)

	def onParentComplete(self):
		if self.verbLevel is not None:
			for c in self.parent.core.outputTable:
				if c.verbLevel<self.verbLevel:
					self._cols.feedObject(self, OutputField.fromColumn(c))

	@classmethod
	def fromColumns(cls, columns, **kwargs):
		return rscdef.TableDef.fromColumns([OutputField.fromColumn(c)
			for c in columns])

	@classmethod
	def fromTableDef(cls, tableDef):
		return cls(None, columns=[OutputField.fromColumn(c) for c in tableDef],
			forceUnique=tableDef.forceUnique, dupePolicy=tableDef.dupePolicy,
			primary=tableDef.primary).finishElement()
