"""
A table representing a query.

This is mainly for streaming application.  The table represents
a DB query result.  All you can do with the data itself is iterate over 
the rows.  The metadata is usable as with any other table.
"""

from gavo import base
from gavo import rscdef
from gavo.rsc import dbtable
from gavo.rsc import table


class QueryTable(table.BaseTable, dbtable.DBMethodsMixin):
	"""QueryTables are constructed with a table definition and a DB query
	feeding this table definition.

	As with plain DB tables, you can pass in a connection; if you don't
	a new connection will be opened.

	There's an alternative constructor allowing "quick" construction of
	the result table (fromColumns).
	"""
	def __init__(self, tableDef, query, **kwargs):
		if "rows" in kwargs:
			raise base.Error("QueryTables cannot be constructed with rows")
		self.query = query
		table.BaseTable.__init__(self, tableDef, **kwargs)
		self._makeConnection(kwargs)
	
	def __iter__(self):
		"""actually runs the query and returns rows (dictionaries).

		Warning: You must exhaust the iterator before iterating anew.
		"""
		cursor = self.connection.cursor("cursor"+hex(id(self)))
		cursor.execute(self.query)
		while True:
			nextRows = cursor.fetchmany(1000)
			if not nextRows:
				break
			for row in nextRows:
				yield self.tableDef.makeRowFromTuple(row)
		cursor.close()

	def __len__(self):
		# Avoid unnecessary failures when doing list(QueryTable())
		raise AttributeError()

	@classmethod
	def fromColumns(cls, colSpec, query, **kwargs):
		"""returns a QueryTable object for query, where the result table is
		inferred from colSpec.

		colSpec is a sequence consisting of either dictionaries with constructor
		arguments to rscdef.Column or complete objects suitable as rscdef.Column
		objects; futher kwargs are passed on the the QueryTable's constructor.
		"""
		columns = []
		for c in colSpec:
			if isinstance(c, dict):
				columns.append(base.makeStruct(rscdef.Column, **c))
			else:
				columns.append(c)
		return cls(base.makeStruct(rscdef.TableDef, columns=columns),
			query, **kwargs)
