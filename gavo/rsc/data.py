"""
Making data out of descriptors and sources.
"""

import sys

from gavo import base
from gavo import rscdef
from gavo import utils
from gavo.base import sqlsupport
from gavo.rsc import common
from gavo.rsc import dbtable
from gavo.rsc import table
from gavo.rsc import tables


MS = base.makeStruct


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
			makeRow = make.rowmaker.compileForTableDef(table.tableDef)
			def addRow(srcRow, feeder=feeder, makeRow=makeRow):
				try:
					procRow = makeRow(srcRow, table)
					feeder.add(procRow)
				except rscdef.IgnoreThisRow, msg:
					pass
			if make.rowSource=="parameters":
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


class Data(base.MetaMixin, common.ParamMixin):
	"""is a collection of data parsed from a consistent set of sources.

	That is, Data is the instanciation of a DataDescriptor.  In consists
	of a couple of tables which may have certain roles.
	"""
	def __init__(self, dd, tables, parseOptions=common.parseNonValidating):
		base.MetaMixin.__init__(self)  # we're not a structure
		self.dd, self.parseOptions = dd, parseOptions
		self.tables = tables
		self.setMetaParent(self.dd)
		self._initParams(self.dd)

	def __iter__(self):
		for make in self.dd.makes:
			yield self.tables[make.table.id]

	@classmethod 	
	def create(cls, dd, parseOptions=common.parseNonValidating,
			connection=None):
		"""returns a new data instance for dd.

		Existing tables on the database are not touched.  To actually
		re-create them, call recrateTables.
		"""
		controlledTables = {}
		for make in dd.makes:
			controlledTables[make.table.id
				] = make.create(connection, parseOptions, tables.TableForDef)
		return cls(dd, controlledTables, parseOptions)

	@classmethod
	def drop(cls, dd, parseOptions=common.parseNonValidating, connection=None):
		"""drops all tables made by dd if necessary.
		"""
		controlledTables = {}
		for make in dd.makes:
			controlledTables[make.table.id
				] = tables.TableForDef(make.table, create=False, connection=connection)
			# The next line is necessary to have the table's beforeDrop scripts
			# exectued -- this is all far too ugly to be the right way.  I guess
			# beforeDrop really is a property of the table rather than of the
			# make, and makes and tables should have different runners...
			controlledTables[make.table.id]._runScripts = make.getRunner()
		data = cls(dd, controlledTables, parseOptions)
		data.dropTables()

	def dropTables(self):
		for t in self:
			if t.tableDef.system and not self.parseOptions.systemImport:
				continue
			if t.tableDef.onDisk:
				t.drop()

	def updateMeta(self, updateIndices=False):
		"""updates meta information kept in the DB on the contained tables.
		"""
		for t in self:
			if hasattr(t, "updateMeta"):
				t.updateMeta()
				if updateIndices:
					t.dropIndices()
					t.makeIndices()
		return self

	def recreateTables(self, connection):
		"""drops and recreates all table that are onDisk.

		System tables are only recreated when the systemImport parseOption
		is true.
		"""
		if self.parseOptions.updateMode or self.dd.updating:
			if self.parseOptions.dropIndices:
				for t in self:
					if t.tableDef.onDisk:
						t.dropIndices()
			return

		for t in self:
			if t.tableDef.system and not self.parseOptions.systemImport:
				continue
			if t.tableDef.onDisk:
				t.runScripts("preImport")
				t.recreate()

	def commitAll(self):
		"""commits all dependent tables.

		You only need to do this if you let the DBTables get their own
		connections, i.e., didn't create them with a connection argument.

		The method returns the data itself in order to let you do a
		commitAll().closeAll().
		"""
		for t in self:
			if t.tableDef.onDisk:
				t.commit()
		return self

	def closeAll(self):
		"""closes the connections of all dependent tables.

		No implicit commit will be done, so this implies a rollback unless
		you committed before.

		You only need to do this if you let the DBTables get their own
		connections, i.e., didn't create them with a connection argument.
		"""
		for t in self:
			if t.tableDef.onDisk:
				try:
					t.close()
				except sqlsupport.InterfaceError: # probably shared connection
					pass                            # was already closed.

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

	def feedGrammarParameters(self, grammarParameters):
		"""feeds grammarParameters to the parmakers of all makes that have one.
		"""
		for m in self.dd.makes:
			m.runParmakerFor(grammarParameters, self.tables[m.table.id])

	def getFeeder(self, **kwargs):
		return DataFeeder(self, **kwargs)

	def runScripts(self, phase, **kwargs):
		for t in self:
			t.runScripts(phase, **kwargs)


class _EnoughRows(base.ExecutiveAction):
	"""is an internal exception that allows processSource to tell makeData
	to stop handling more sources.
	"""


def _pipeRows(srcIter, feeder, opts):
	feeder.addParameters(srcIter.getParameters())
	for srcRow in srcIter:
		if srcIter.notify:
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
		if opts.maxRows:
			if base.ui.totalRead>opts.maxRows:
				raise _EnoughRows


def processSource(data, source, feeder, opts):
	"""ingests source into the Data instance data.
	"""
	if data.dd.grammar is None:
		raise base.ReportableError("The data descriptor %s cannot be used"
			" to make data since it has no defined grammar."%data.dd.id)
	data.runScripts("newSource", sourceToken=source)
	srcIter = data.dd.grammar.parse(source, data)
	if hasattr(srcIter, "getParameters"):  # is a "normal" grammar
		data.feedGrammarParameters(srcIter.getParameters())
		try:
			_pipeRows(srcIter, feeder, opts)
		except (base.Error,base.ExecutiveAction):
			raise
		except Exception, msg:
			raise base.ui.logOldExc(
				base.SourceParseError(str(msg), 
					source=utils.makeEllipsis(unicode(source), 80)))
	else:  # magic grammars (like those of boosters) return a callable
		srcIter(data)


def makeData(dd, parseOptions=common.parseNonValidating,
		forceSource=None, connection=None, data=None):
	"""returns a data instance built from dd.

	It will arrange for the parsing of all tables generated from dd's grammar.
	If connection is passed in, the the entire operation will run within a 
	single transaction within this transaction.  The connection will be
	rolled back or committed depending on the success of the operation.

	You can pass in a data instance created by yourself in data.  This
	makes sense if you want to, e.g., add some meta information up front.
	"""
# this will become much prettier once we can use context managers
	if data is None:
		res = Data.create(dd, parseOptions, connection=connection)
	else:
		res = data
	res.recreateTables(connection)
	feeder = res.getFeeder(batchSize=parseOptions.batchSize)
	try:
		if forceSource is None:
			for source in dd.iterSources(connection):
				try:
					processSource(res, source, feeder, parseOptions)
				except _EnoughRows:
					break
				except base.SkipThis:
					continue
		else:
			processSource(res, forceSource, feeder, parseOptions)
	except:
		if connection:
			connection.rollback()
		excHandled = feeder.exit(*sys.exc_info())
		if not excHandled:
			raise
	else:
		feeder.exit(None, None, None)
		if connection:
			connection.commit()
		else:
			res.commitAll()
	res.nAffected = feeder.getAffected()

	if parseOptions.buildDependencies:
		makeDependentsFor([dd], parseOptions, connection)

	return res


def makeDependentsFor(dds, parseOptions, connection):
	"""rebuilds all data dependent on one of the DDs in the dds sequence.
	"""
	toBuild = set()

	def gatherDependents(dd):
		for dependentId in dd.dependents:
			try:
				dependentDD = base.resolveId(dd.rd, dependentId)
				if dependentDD not in toBuild:
					toBuild.add(dependentDD)
					gatherDependents(dependentDD)
			except (base.StructureError, base.NotFoundError), msg:
				base.ui.notifyWarning("Ignoring dependent %s of %s (%s)"%(
					dependentId, dd.id, unicode(msg)))

	for dd in dds:
		gatherDependents(dd)
	if parseOptions.buildDependencies:
		parseOptions = parseOptions.change(buildDependencies=False)
	for dd in toBuild:
		makeData(dd, parseOptions=parseOptions, connection=connection)


def makeDataById(ddId, parseOptions=common.parseNonValidating,
		connection=None, inRD=None):
	"""returns the data set built from the DD with ddId (which must be
	fully qualified).
	"""
	dd = base.resolveId(inRD, ddId)
	return makeData(dd, parseOptions=parseOptions, connection=connection)


def wrapTable(table, rdSource=None):
	"""returns a Data instance containing only table (or table if it's already
	a data instance).

	If table has no rd, you must pass rdSource, which must be an object having
	and rd attribute (rds, tabledefs, etc, work).
	"""
	if isinstance(table, Data):
		return table
	if rdSource is None:
		rd = table.tableDef.rd
	elif hasattr(rdSource, "rd"):
		rd = rdSource.rd
	else:
		raise TypeError("Invalid RD source: %s"%rdSource)
	newDD = MS(rscdef.DataDescriptor, makes=[
		MS(rscdef.Make, table=table.tableDef, rowmaker=None)], parent_=rd)
	if rdSource:
		newDD.adopt(table.tableDef)
	res = Data(newDD, tables={table.tableDef.id: table})
	res.meta_ = table.meta_
	return res
