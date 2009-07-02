"""
Tables, base and in memory.

Basically, a table consists of a list of dictionaries (the rows) and a
table definition (resdef.TableDef).

You should, in general, not construct the tables directly but use
the tables.TableForDef factory.  The reason is that some classes ignore
certain aspects of TableDefs (indices, uniqueForceness) or may not be
what TableDef requires at all (onDisk).  Arguably there should be
different TableDefs for all these aspects, but then I'd have a plethora
of TableDef elements, which I think is worse than a factory function.
"""

from gavo import base
from gavo.rsc import common

import sys

class Error(base.Error):
	pass


class Feeder(object):
	"""is a feeder for a table.

	A feeder becomes active with construction with a table and provides 
	the methods

	* add(row) -> None -- add row to table.  This may raise all kinds
	  of crazy exceptions.
	* exit(excType=None, excVal=None, excTb=None) -> None -- must
	  be called when all rows are added.  If an exception happened,
	  pass sys.exc_info() here; see below on what the method really does.

	The default implementation of exit calls importFinished and importFailed of
	the parent table if an exception happens.  In importFinished raises and
	exception, it is handed on to importFailed and re-raised if importFailed
	returns False.

	This should become a context manager when we can require python 2.5.

	The batch size constructor argument is for the benefit of DBTables.
	"""
	def __init__(self, table, batchSize=1024):
		self.table = table
		self.nAffected = 0

	def getAffected(self):
		return self.nAffected

	def add(self, row):
		if self.table.validateRows:
			self.table.tableDef.validateRow(row)
		self.table.addRow(row)
		self.nAffected += 1
	
	def exit(self, excType=None, excVal=None, excTb=None):
		if excType is None: # all ok
			try:
				self.table.importFinished()
			except:
				if not self.table.importFailed(*sys.exc_info()):
					raise
		else:           # exception occurred during processing
			if not self.table.importFailed(excType, excVal, excTb):
				raise
	

class BaseTable(base.MetaMixin):
	"""is a container for row data.

	Tables consist of rows, where each row maps column names to their
	value for that row.  The rows are accessible at least by iterating
	over a table.

	Tables get constructed with a tableDef and keyword arguments.  For
	convenience, tables must accept any keyword argument and only pluck those
	out it wants.

	Here's a list of keywords used by known subclasses of BaseTables:

	validateRows -- have rows be validated by the tableDef before addition
	  (all Tables)
	rows -- a list of rows the table has at start (InMemoryTables; DbTables
	  will raise an error on these).
	connection -- a database connection to use for accessing DbTables.
	votCasts -- a dictionary mapping column names to dictionaries for
	  use with ColProperties.  See there.

	You can add rows using the addRow method.  For bulk additions, however,
	it may be much more efficient to call getFeeder (though for in-memory
	tables, there is no advantage).

	The metadata is available on the tableDef attribute.

	Tables have to implement the following methods:

	* __iter__
	* __len__
	* __getitem__(n) -- returns the n-th row or raises an IndexError
	* removeRow(row) removes a row from the table or raises an
	  IndexError if the row does not exist.  This is a slow, O(n) operation.
	* addRow(row) -- appends new data to the table
	* getRow(*args) -- returns a row by the primary key.  If no primary key
	  is defined, a ValueError is raised, if the key is not present, a
	  KeyError.  An atomic primary key is accessed through its value,
	  for compound primary keys a tuple must be passed.
	* getFeeder(**kwargs) -> feeder object -- returns an object with add and 
	  exit methods.  See feeder above.
	* importFinished() -> None -- called when a feeder exits successfully
	* importFailed(*excInfo) -> boolean -- called when feeding has failed;
	  when returning True, the exception that has caused the failure
	  is not propagated.
	* close() -> may be called by clients to signify the table will no
	  longer be used and resources should be cleared (e.g., for DBTables
	  with private connections.
	"""
	def __init__(self, tableDef, **kwargs):
		base.MetaMixin.__init__(self)
		self.tableDef = tableDef
		self.validateRows = kwargs.get("validateRows", False)
		self.votCasts = kwargs.get("votCasts", {})
		self.role = kwargs.get("role")

	def _failIncomplete(self, *args, **kwargs):
		raise NotImplementedError("%s is an incomplete Table implementation"%
			self.__class__.__name__)

	__iter__ = _failIncomplete
	__len__ = _failIncomplete
	removeRow = _failIncomplete
	addRow = _failIncomplete
	getRow = _failIncomplete
	removeRow = _failIncomplete
	getFeeder = _failIncomplete

	def importFinished(self):
		pass
	
	def importFailed(self, *excInfo):
		return False

	def close(self):
		pass

class InMemoryTable(BaseTable):
	"""is a table kept in memory.

	This table only keeps an index for the primaray key.  All other indices
	are ignored.
	"""
	def __init__(self, tableDef, **kwargs):
		BaseTable.__init__(self, tableDef, **kwargs)
		self.rows = kwargs.get("rows", [])
	
	def __iter__(self):
		return iter(self.rows)
	
	def __len__(self):
		return len(self.rows)

	def removeRow(self, row):
		self.rows.remove(row)

	def addRow(self, row):
		if self.validateRows:
			try:
				self.tableDef.validateRow(row)
			except rscdef.IgnoreThisRow:
				return
		self.rows.append(row)

	def addTuple(self, tupRow):
		self.addRow(self.tableDef.makeRowFromTuple(tupRow))

	def getRow(self, *args):
		raise ValueError("Cannot use getRow in index-less table")

	def getFeeder(self, **kwargs):
		return Feeder(self, **kwargs)


class InMemoryIndexedTable(InMemoryTable):
	"""is an InMemoryTable for a TableDef with a primary key.
	"""
	def __init__(self, tableDef, **kwargs):
		InMemoryTable.__init__(self, tableDef, **kwargs)
		if not self.tableDef.primary:
			raise Error("No primary key given for InMemoryIndexedTable")
		self._makeRowIndex()

	def removeRow(self, row):
# This remains slow since we do not keep the index of a row in self.rows
		InMemoryTable.removeRow(self, row)
		del self.rowIndex[self.tableDef.getPrimaryIn(row)]

	def addRow(self, row):
		if self.validateRows:
			try:
				self.tableDef.validateRow(row)
			except rscdef.IgnoreThisRow:
				return
		self.rows.append(row)
		self.rowIndex[self.tableDef.getPrimaryIn(row)] = row

	def getRow(self, *args):
		return self.rowIndex[args]

	def _makeRowIndex(self):
		"""recreates the index of primary keys to rows.
		"""
		self.rowIndex = {}
		for r in self.rows:
			self.rowIndex[self.tableDef.getPrimaryIn(r)] = r


class UniqueForcedTable(InMemoryIndexedTable):
	"""is an InMemoryTable with an enforced policy on duplicate
	primary keys.

	See resdef.TableDef for a discussion of the policies.
	"""
	def __init__(self, tableDef, **kwargs):
		# hide init rows (if present) in the next line to not let
		# duplicate primaries slip in here.
		rows = kwargs.pop("rows", [])
		InMemoryIndexedTable.__init__(self, tableDef, **kwargs)
		try:
			self.resolveConflict = {
				"check": self._ensureRowIdentity,
				"drop": self._dropNew,
				"overwrite": self._overwriteOld,
			}[self.tableDef.dupePolicy]
		except KeyError, msg:
			raise Error("Invalid conflict resolution strategy: %s"%str(msg))
		for row in rows:
			self.addRow(row)

	def _ensureRowIdentity(self, row, key):
		"""raises an exception if row is not equivalent to the row stored
		for key.

		This is one strategy for resolving primary key conflicts.
		"""
		storedRow = self.rowIndex[key]
		if row.keys()!=storedRow.keys():
			raise Error("Differing rows for primary key %s: %s vs. %s"%(
				key, self.rowIndex[key], row))
		for colName in row:
			if row[colName] is None or storedRow[colName] is None:
				continue
			if row[colName]!=storedRow[colName]:
				raise base.ValidationError(
					"Differing rows for primary key %s;"
					" %s vs. %s"%(key, row[colName],
						storedRow[colName]), colName=colName, row=row)

	def _dropNew(self, row, key):
		"""does nothing.

		This is for resolution of conflicting rows (the "drop" strategy).
		"""
		pass
	
	def _overwriteOld(self, row, key):
		"""overwrites the existing rows with key in table with rows.

		This is for resolution of conflicting rows (the "overwrite"
		strategy).

		Warning: This is typically rather slow.
		"""
		storedRow = self.rowIndex[key]
		self.removeRow(storedRow)
		return self.addRow(row)

	def addRow(self, row):
		if self.validateRows:
			try:
				self.tableDef.validateRow(row)
			except rscdef.IgnoreThisRow:
				return
		key = self.tableDef.getPrimaryIn(row)
		if key in self.rowIndex:
			return self.resolveConflict(row, key)
		else:
			self.rowIndex[key] = row
		return InMemoryIndexedTable.addRow(self, row)
