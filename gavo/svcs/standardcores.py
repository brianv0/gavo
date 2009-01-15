"""
Some standard cores for services.

A core receives and "input table" (usually just containing the query 
parameters in the doc rec) and returns an output data set (which is promoted
to a SvcResult in the service before being handed over to the renderer).

These then have to be picked up by renderers and formatted for delivery.
"""

import itertools
import os
import sys
import traceback
import weakref

from twisted.python import log

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.base import sqlsupport
from gavo.base import vizierexprs
from gavo.svcs import core
from gavo.svcs import inputdef
from gavo.svcs import outputdef


class Error(base.Error):
	pass


printQuery = False

MS = base.makeStruct


class CondDesc(base.Structure):
	"""a CondDesc is part of the semantics of a DbBasedCore.  
	
	It defines inputs as InputKeys, so they can be used "naked" if necessary,
	and provide an asSQL method that returns a query fragment.

	"silent" condDescs only contribute widgets, no SQL.  This can be used
	for "meta" input for renderers (as opposed to the core).
	"""
	name_ = "condDesc"

	_inputKeys = base.StructListAttribute("inputKeys", 
		childFactory=inputdef.InputKey, copyable=True)
	_silent = base.BooleanAttribute("silent", default=False,
		copyable=True)
	_required = base.BooleanAttribute("required", default=False,
		copyable=True)
	_fixedSQL = base.UnicodeAttribute("fixedSQL", default=None,
		copyable=True)
	_inputKey = base.ReferenceAttribute("buildFrom", default=None)
	_predefined = base.UnicodeAttribute("predefined", default=None)

	def __init__(self, parent, **kwargs):
		base.Structure.__init__(self, parent, **kwargs)
		# copy parent's resolveName if present for buildFrom resolution
		if hasattr(self.parent, "resolveName"):
			self.resolveName = self.parent.resolveName

	def completeElement(self):
		if self.predefined:
			raise base.Replace(getCondDesc(self.predefined)(None).finishElement())
		if self.buildFrom:
			self.feedFrom(CondDesc.fromColumn(self.buildFrom))
			self.buildFrom = None
		self._completeElementNext(CondDesc)

	@property
	def name(self):
		"""returns some key for uniqueness of condDescs.
		"""
		# This is necessary for ColumnLists that are used
		# for CondDescs as well.  Ideally, we'd do this on an
		# InputKeys basis and yield their names (because that's what
		# formal counts on), but it's probably not worth the effort.
		return "+".join([f.name for f in self.inputKeys])

	def inputReceived(self, inPars):
		"""returns True if all inputKeys can be filled from inPars.

		As a side effect, inPars will receive defaults form the input keys
		if there are any.
		"""
		keysFound, keysMissing = [], []
		for f in self.inputKeys:
			if f.name not in inPars or inPars[f.name] is None:
				if f.values is not None and f.values.default:
					inPars[f.name] = f.values.default
					keysFound.append(f)
				else:
					keysMissing.append(f)
			else:
				keysFound.append(f)
		if not keysMissing:
			return True
		# keys are missing.  That's ok if none were found and we're required
		if not self.required and not keysFound:
			return False
		if self.required:
			raise base.ValidationError("A value is necessary here", 
				fieldName=keysMissing[0].name)
		# we're optional, but a value was given and others are missing
# XXX TODO: it'd be nicer if we'd complain about all missing keys at once.
		raise base.ValidationError("When you give a value for %s,"
			" you must give value(s) for %s, too"%(keysFound[0].tablehead, 
					", ".join(k.name for k in keysMissing)),
				colName=keysMissing[0].name)

	def asSQL(self, inPars, sqlPars):
		if self.silent:
			return ""
		res = []
		for ik in self.inputKeys:
			res.append(vizierexprs.getSQL(ik, inPars, sqlPars))
		sql = vizierexprs.joinOperatorExpr("AND", res)
		if self.fixedSQL:
			sql = vizierexprs.joinOperatorExpr("AND", [sql, self.fixedSQL])
		return sql

	@classmethod
	def fromInputKey(cls, ik, **kwargs):
		return base.makeStruct(CondDesc, inputKeys=[ik], **kwargs)

	@classmethod
	def fromColumn(cls, col, **kwargs):
		return cls.fromInputKey(ik=inputdef.InputKey.fromColumn(col), **kwargs)


_condDescRegistry = {}

def registerCondDesc(name, condDesc):
	_condDescRegistry[name] = condDesc

def getCondDesc(name):
	return _condDescRegistry[name]


def mapDBErrors(excType, excValue, excTb):
	"""translates exception into something we can display properly.
	"""
# This is a helper to all DB-based cores and should probably become
# a method of a baseclass of them when we refactor this mess
	if hasattr(excValue, "cursor"):
		log.msg("Failed DB query: %s"%excValue.cursor.query)
# XXX TODO: Alejandro's pgsql timeout patch somehow doesn't expose 
# TimeoutError, and I don't have time to fix this now.  So, I check the 
# exception type the rough way.
	if excValue.__class__.__name__.endswith("TimeoutError"):
		raise base.ValidationError("Query timed out (took too long).  See"
			" our help.", "query")
	elif isinstance(excValue, base.DBError):
		raise base.ValidationError(unicode(excValue), "query")
	else:
		traceback.print_exc()
		raise


class TableBasedCore(core.Core):
	"""is a core knowing a DB table it operates on and allowing the definition
	of condDescs.
	"""
	_queriedTable = base.ReferenceAttribute("queriedTable",
		default=base.Undefined, description="A reference to the table"
			" this core queries", copyable=True, callbacks=["_fixNamePath"])
	_condDescs = base.StructListAttribute("condDescs", childFactory=CondDesc,
		description="Descriptions of the SQL and input generating entities"
			" for this core; if not given, they will be generated from the"
			" table columns", copyable=True)

	def completeElement(self):
		# if no condDescs have been given, make them up from the table columns.
		if not self.condDescs and self.queriedTable:
			self.condDescs = [self.adopt(CondDesc.fromColumn(c))
				for c in self.queriedTable]

		# if no inputDD has been given, generate one from the condDescs
		if self.inputDD is base.Undefined:
			iks = []
			for cd in self.condDescs:
				iks.extend(cd.inputKeys)
			self.inputDD = MS(inputdef.InputDescriptor,
				grammar=MS(inputdef.ContextGrammar, inputKeys=iks))

		# if not outputTable has been given, make it up from the table columns.
		if self.outputTable is base.Undefined:
			self.outputTable = self.adopt(outputdef.OutputTableDef.fromTableDef(
				self.queriedTable))

		self._completeElementNext(TableBasedCore)

	def _fixNamePath(self, qTable):
# callback from queriedTable to make it the default for namePath as well
		if self.namePath is None:
			self.namePath = qTable.id


class DBCore(TableBasedCore):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.

	Db cores must define a _getQuery(inputData, queryMeta) method that
	returns a data descriptor for the expected SQL output, an SQL fragment 
	and a dictionary mapping the parameters of that
	query to values understandable by the DB interface.
	"""
	name_ = "dbCore"

	_sortKey = base.UnicodeAttribute("sortKey",
		description="A pre-defined sort order (suppresses DB options widget)",
		copyable=True)
	_limit = base.IntAttribute("limit", description="A pre-defined"
		" match limit (suppresses DB options widget)", copyable=True)
	_distinct = base.BooleanAttribute("distinct", description="Add a"
		" 'distinct' modifier to the query?", default=False, copyable=True)
	_feedbackColumn = base.UnicodeAttribute("feedbackColumn", description=
		"Add this name to query to enable selection for feedback (this"
		" basically only works for atomic primary keys)", copyable=True)
	_namePath = rscdef.NamePathAttribute()

	def wantsTableWidget(self):
		return self.sortKey is None and self.limit is None

	def _getSQLWhere(self, inputData, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputData and queryMeta.
		"""
		sqlPars, frags = {}, []
		inputPars = inputData.getPrimaryTable().rows[0]
		return vizierexprs.joinOperatorExpr("AND",
			[cd.asSQL(inputPars, sqlPars)
				for cd in self.condDescs]), sqlPars

	def getQueryCols(self, service, queryMeta):
		"""returns the fields we need in the output table.

		The normal DbBased core just returns whatever the service wants.
		Derived cores, e.g., for special protocols, could override this
		to make sure they have some fields in the result they depend on.
		"""
		return service.getCurOutputFields(queryMeta)

	def _makeTable(self, rowIter, resultTableDef, queryMeta):
		"""returns a table from the row iterator rowIter, updating queryMeta
		as necessary.
		"""
		rows = list(rowIter)
		if len(rows)>queryMeta.get("dbLimit", 1e10): # match limit overflow
			del rows[-1]
			queryMeta["Overflow"] = True
		queryMeta["Matched"] = len(rows)
		return rsc.TableForDef(resultTableDef, rows=rows)
	
	def _runQuery(self, resultTableDef, fragment, pars, queryMeta,
			**kwargs):
		queriedTable = rsc.TableForDef(self.queriedTable, nometa=True,
			create=False, role="primary")
		iqArgs = {"limits": queryMeta.asSQL(), "distinct": self.distinct}
		iqArgs.update(kwargs)
		try:
			try:
				return self._makeTable(
					queriedTable.iterQuery(resultTableDef, fragment, pars,
						**iqArgs), resultTableDef, queryMeta)
			except:
				mapDBErrors(*sys.exc_info())
		finally:
			queriedTable.close()

	def run(self, service, inputData, queryMeta):
		"""does the DB query and returns an InMemoryTable containing
		the result.
		
		It requires a method _getQuery returning a TableDef defining
		the result, an SQL WHERE-clause and its parameters.
		"""
		resultTableDef = base.makeStruct(outputdef.OutputTableDef,
			parent_=self.queriedTable.parent,
			onDisk=False, columns=self.getQueryCols(service, queryMeta)
			)
		if not resultTableDef.columns:
			raise base.ValidationError("No output fields with these settings",
				"_OUTPUT")
		queryMeta.overrideDbOptions(limit=self.limit, sortKey=self.sortKey)
		fragment, pars = self._getSQLWhere(inputData, queryMeta)
		queryMeta["sqlQueryPars"] = pars
		return self._runQuery(resultTableDef, fragment, pars, queryMeta)

core.registerCore(DBCore)


def makeFeedbackColumn(cols, columnName):
	ff = outputdef.OutputField.fromColumn(cols.getColumnByName(columnName))
	ff.name = "feedbackSelect"
	ff.select = columnName
	ff.tablehead = "F"
	ff.description = "Check to include row in feedback set"
	ff.feed("displayHint", "type=feedbackSelect")
	return ff


class FixedQueryCore(core.Core):
	name_ = "fixedQueryCore"

	_timeout = base.FloatAttribute("timeout", default=15., description=
		"Seconds until the query is aborted")
	_query = base.UnicodeAttribute("query", default=base.Undefined,
		description="The query to be executed.  You must define the"
			" output fields in the core's output table.")

	def completeElement(self):
		# default to empty inputDD
		if self.inputDD is base.Undefined:
			self.inputDD = base.makeStruct(inputdef.InputDescriptor,
				grammar=base.makeStruct(inputdef.ContextGrammar))
		self._completeElementNext(FixedQueryCore)

	def run(self, service, inputData, queryMeta):
		querier = base.SimpleQuerier()
		try:
			return self._parseOutput(querier.runIsolatedQuery(self.query,
				timeout=self.timeout), queryMeta)
		except:
			mapDBErrors(*sys.exc_info())

	def _parseOutput(self, dbResponse, queryMeta):
		"""builds an InternalDataSet out of dbResponse and the outputFields
		of our service.
		"""
		if dbResponse is None:
			dbResponse = []
		queryMeta["Matched"] = len(dbResponse)
		fieldNames = self.outputTable.dictKeys
		return rsc.TableForDef(self.outputTable,
			rows=[dict((k,v) 
					for k,v in itertools.izip(fieldNames, row))
				for row in dbResponse])

core.registerCore(FixedQueryCore)

