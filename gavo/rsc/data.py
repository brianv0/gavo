"""
Making data out of descriptors and sources.
"""

import sys

from gavo import base
from gavo import rscdef
from gavo.rsc import common
from gavo.rsc import dbtable
from gavo.rsc import table
from gavo.rsc import tables


class DataFeeder(table.Feeder):
	"""is a feeder for data.

	This is basically a collection of all feeders of the tables belonging
	to data, except it will also call the table's mappers, i.e., add
	expects source rows from data's grammars.
	"""
	def __init__(self, data, batchSize=1024):
		self.data, self.batchSize = data, batchSize
		self.nAffected = 0
		self._makeFeeds()

	def _getAdders(self):
		"""returns a triple of (rowAdders, parAdders, feeds) for the data we
		feed to.

		rowAdders contains functions to add raw rows returned from a grammar,
		parAdders the same for parameters returned by the grammar, and
		feeds is a list containing all feeds the adders add to (this
		is necessary to let us exit all of them.
		"""
		adders, parAdders, feeders = [], [], []
		for make in self.data.dd.makes:
			table = self.data.tables[make.table.id]
			feeder = table.getFeeder(batchSize=self.batchSize)
			makeRow = make.rowmaker.compileForTable(make.table)
			def addRow(srcRow, feeder=feeder, makeRow=makeRow):
				feeder.add(makeRow(srcRow))
			if make.rowmaker.rowSource=='parameters':
				parAdders.append(addRow)
			else:
				adders.append(addRow)
			feeders.append(feeder)
		return adders, parAdders, feeders

	def _makeFeeds(self):
		adders, parAdders, self.feeders = self._getAdders()
		def add(row):
			for adder in adders:
				adder(row)
		def addParameters(row):
			for adder in parAdders:
				adder(row)
		self.add = add
		self.addParameters = addParameters

	def exit(self, *excInfo):
		affected = []
		for feeder in self.feeders:
			feeder.exit(*excInfo)
			affected.append(feeder.getAffected())
		if affected:
			self.nAffected = max(affected)
	
	def getAffected(self):
		return self.nAffected


class Data(base.MetaMixin):
	"""is a collection of data parsed from a consistent set of sources.

	That is, Data is the instanciation of a DataDescriptor.  In consists
	of a couple of tables which may have certain roles.
	"""
	def __init__(self, dd, tables, parseOptions=common.parseNonValidating):
		base.MetaMixin.__init__(self)  # we're not a structure
		self.dd, self.parseOptions = dd, parseOptions
		self.tables = tables

	@classmethod 	
	def create(cls, dd, parseOptions=common.parseNonValidating,
			connection=None):
		"""returns a new data instance for dd.

		Existing tables on the database are not touched.  To actually
		re-create them, call recrateTables.
		"""
		controlledTables = {}
		for make in dd.makes:
			tableDef = make.table
			controlledTables[tableDef.id] = tables.TableForDef(tableDef,
				parseOptions=parseOptions, connection=connection, role=make.role)
		return cls(dd, controlledTables, parseOptions)

	def __iter__(self):
		return self.tables.itervalues()

	def updateMeta(self, updateIndices=False):
		"""updates meta information kept in the DB on the contained tables.
		"""
		for t in self.tables.values():
			if isinstance(t, dbtable.DBTable):
				t.updateMeta()
				if updateIndices:
					t.dropIndices()
					t.makeIndices()
				t.commit()
		return self

	def recreateTables(self):
		"""drops and recreates all table that are onDisk.

		System tables are only recreated when the systemImport parseOption
		is true.
		"""
		self.dd.runScripts("preCreation")
		if self.parseOptions.updateMode:
			return
		for t in self.tables.values():
			if t.tableDef.system and not self.parseOptions.systemImport:
				continue
			if t.tableDef.onDisk:
				t.recreate()
		self.dd.runScripts("postCreation")
	
	def dropTables(self):
		"""drops all tables in this RD that are onDisk.

		System tables are only dropped when the systemImport parseOption
		is true.
		"""
		for t in self.tables.values():
			if t.tableDef.system and not self.parseOptions.systemImport:
				continue
			if t.tableDef.onDisk:
				t.drop().commit()

	def getPrimaryTable(self):
		"""returns the table contained if there is only one, or the one
		with the role primary.

		If no matching table can be found, raise a DataError.
		"""
		if len(self.tables)==1:
			return self.tables.values()[0]
		else:
			try:
				return self.getTableWithRole("primary")
			except base.DataError: # raise more telling message
				pass
		raise base.DataError("Ambiguous request for primary table")

	def getTableWithRole(self, role):
		try:
			for t in self.tables.values():
				if t.role==role:
					return t
		except base.StructureError:
			pass
		raise base.DataError("No table with role '%s'"%role)

	def getFeeder(self, **kwargs):
		return DataFeeder(self, **kwargs)


class _EnoughRows(base.ExecutiveAction):
	"""is an internal exception that allows processSource to tell makeData
	to stop handling more sources.
	"""


def processSource(res, source, feeder, opts):
	srcIter = res.dd.grammar.parse(source)
	if hasattr(srcIter, "getParameters"):  # is a "normal" grammar
		feeder.addParameters(srcIter.getParameters())
		nImported = 0
		for srcRow in srcIter:
			base.ui.notifyIncomingRow(srcRow)
			if opts.dumpRows:
				print srcRow
			try:
				feeder.add(srcRow)
			except:
				if opts.keepGoing:
					base.ui.notifyFailedRow(srcRow, sys.exc_info())
				else:
					raise
			if opts.maxRows:  # Count and bail if we're to stop somewhere
				nImported +=1
				if nImported>opts.maxRows:
					raise _EnoughRows
	else:  # magic grammars return a callable
		srcIter(res)


def makeData(dd, parseOptions=common.parseNonValidating,
		forceSource=None, connection=None):
	"""returns a data instance built from dd.

	It will arrange for the parsing of all tables generated from dd's grammar.
	If connection is passed in, the the entire operation will run within a 
	single transaction within this transaction.  The connection will be
	rolled back or committed depending on the success of the operation.
	"""
# this will become much prettier once we can use context managers
	res = Data.create(dd, parseOptions, connection=connection)
	res.recreateTables()
	feeder = res.getFeeder()
	try:
		if forceSource is None:
			for source in dd.iterSources():
				try:
					processSource(res, source, feeder, parseOptions)
				except _EnoughRows:
					break
		else:
			processSource(res, forceSource, feeder, parseOptions)
	except:
		excHandled = feeder.exit(*sys.exc_info())
		if connection is not None:
			connection.rollback()
		if not excHandled:
			raise
	else:
		feeder.exit(None, None, None)
		if connection:
			connection.commit()
	res.nAffected = feeder.getAffected()
	_makeDependents(dd, parseOptions, connection)
	return res


def _makeDependents(srcDD, parseOptions, connection):
	"""rebuilds all data dependent on srcDD with parseOptions and within
	connection.
	"""
	for dependentId in srcDD.dependents:
		makeDataById(dependentId, parseOptions, connection, inRD=srcDD.rd)


def makeDataById(ddId, parseOptions=common.parseNonValidating,
		connection=None, inRD=None):
	"""returns the data set built from the DD with ddId (which must be
	fully qualified).
	"""
	dd = base.resolveId(inRD, ddId)
	return makeData(dd, parseOptions=parseOptions, connection=connection)
