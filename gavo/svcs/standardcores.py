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

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.base import sqlsupport
from gavo.svcs import core
from gavo.svcs import inputdef
from gavo.svcs import outputdef
from gavo.svcs import pql
from gavo.svcs import vizierexprs


class Error(base.Error):
	pass


printQuery = False

MS = base.makeStruct


_RENDERER_ADAPTORS = {
	'form': vizierexprs.adaptInputKey,
	'pql': pql.adaptInputKey,
}

def getRendererAdaptor(renderer):
	"""returns a function that returns input keys adapted for renderer.

	The function returns None if no adapter is necessary.  This
	only takes place for inputKeys within a buildFrom condDesc.
	"""
	return _RENDERER_ADAPTORS.get(renderer.parameterStyle)


class PhraseMaker(rscdef.ProcApp):
	"""A procedure application for generating SQL expressions from input keys.

	PhraseMaker code must *yield* SQL fragments that can occur in WHERE
	clauses, i.e., boolean expressions (thus, they must be generator
	bodies).

	The following names are available to them:

		- inputKeys -- the list of input keys for the parent CondDesc
		- inPars -- a dictionary mapping inputKey names to the values
		  provided by the user
		- outPars -- a dictionary that is later used as the parameter
			dictionary to the query.
	
	To get the standard SQL a single key would generate, say::

		yield base.getSQLForField(inputKeys[0], inPars, outPars)
	
	To insert some value into outPars, do not simply use some key into
	outParse, since, e.g., the condDesc might be used multiple times.
	Instead, use getSQLKey, maybe like this::

		ik = inputKeys[0]
		yield "%s BETWEEN %%(%s)s AND %%(%s)s"%(ik.name,
			base.getSQLKey(ik.name, inPars[ik.name]-10, outPars),
			base.getSQLKey(ik.name, inPars[ik.name]+10, outPars))
	
	getSQLKey will make sure unique names in outPars are chosen and
	enters the values there.
	"""
	name_ = "phraseMaker"

	requiredType = "phraseMaker"
	formalArgs = "self, inputKeys, inPars, outPars"


class CondDesc(base.Structure):
	"""A query specification for cores talking to the database.
	
	CondDescs define inputs as a sequence of InputKeys (see `Element InputKey`_).
	Internally, the values in the InputKeys can be translated to SQL.
	"""
	name_ = "condDesc"

	_inputKeys = rscdef.ColumnListAttribute("inputKeys", 
		childFactory=inputdef.InputKey, copyable=True,
		description="One or more InputKeys defining the condition's input.")
	_silent = base.BooleanAttribute("silent", default=False,
		copyable=True, description="Do not produce SQL from this CondDesc.  This"
			" can be used to convey meta information to the core.  However,"
			" in general, a service is a more appropriate place to deal with"
			" such information, and thus you should prefer service InputKeys"
			" to silent CondDescs.")
	_required = base.BooleanAttribute("required", default=False,
		copyable=True, description="Reject queries not filling the InputKeys"
			" of this CondDesc")
	_fixedSQL = base.UnicodeAttribute("fixedSQL", default=None,
		copyable=True, description="Always insert this SQL statement into"
			" the query.  Deprecated.")
	_buildFrom = base.ReferenceAttribute("buildFrom", 
		description="A reference to an InputKey to define this CondDesc",
		default=None)
	_phraseMaker = base.StructAttribute("phraseMaker", default=None,
		description="Code to generate custom SQL from the input keys", 
		childFactory=PhraseMaker, copyable=True)
	_combining = base.BooleanAttribute("combining", default="False",
		description="Allow some input keys to be missing when others are given?"
			" (you want this for pseudo-condDescs just collecting random input"
			" keys)",   # (and I wish I had a better idea)
		copyable="True")
	_original = base.OriginalAttribute()
	
	def __init__(self, parent, **kwargs):
		base.Structure.__init__(self, parent, **kwargs)
		# copy parent's resolveName if present for buildFrom resolution
		if hasattr(self.parent, "resolveName"):
			self.resolveName = self.parent.resolveName

	@classmethod
	def fromInputKey(cls, ik, **kwargs):
		return base.makeStruct(CondDesc, inputKeys=[ik], **kwargs)

	@classmethod
	def fromColumn(cls, col, **kwargs):
		return base.makeStruct(cls, buildFrom=col, **kwargs)

	@property
	def name(self):
		"""returns some key for uniqueness of condDescs.
		"""
		# This is necessary for ColumnLists that are used
		# for CondDescs as well.  Ideally, we'd do this on an
		# InputKeys basis and yield their names (because that's what
		# formal counts on), but it's probably not worth the effort.
		return "+".join([f.name for f in self.inputKeys])

	def completeElement(self):
		if self.buildFrom and not self.inputKeys:
			# use the column as input key; special renderers may want
			# to do type mapping, but the default is to have plain input
			self.inputKeys = [inputdef.InputKey.fromColumn(self.buildFrom)]
		self._completeElementNext(CondDesc)

	def expand(self, *args, **kwargs):
		"""hands macro expansion requests (from phraseMakers) upwards.

		This is to the queried table if the parent has one (i.e., we're
		part of a core), or to the RD if not (i.e., we're defined within
		an rd).
		"""
		if hasattr(self.parent, "queriedTable"):
			return self.parent.queriedTable.expand(*args, **kwargs)
		else:
			return self.parent.rd.expand(*args, **kwargs)

	def _makePhraseDefault(self, ignored, inputKeys, inPars, outPars):
		# the default phrase maker uses whatever the individual input keys
		# come up with.
		for ik in self.inputKeys:
			yield base.getSQLForField(ik, inPars, outPars)

	# We only want to compile the phraseMaker if actually necessary.
	# condDescs may be defined within resource descriptors (e.g., in
	# scs.rd), and they can't be compiled there (since macros may
	# be missing); thus, we dispatch on the first call.
	def _getPhraseMaker(self):
		try:
			return self.__compiledPhrase
		except AttributeError:
			if self.phraseMaker is not None:
				val = self.phraseMaker.compile()
			else:
				val = self._makePhraseDefault
			self.__compiledPhrase = val
		return self.__compiledPhrase
	makePhrase = property(_getPhraseMaker)

	def _isActive(self, inPars):
		"""returns True if the dict inPars contains input to all our input keys.
		"""
		for f in self.inputKeys:
			if f.name not in inPars:
				return False
		return True

	def inputReceived(self, inPars, queryMeta):
		"""returns True if all inputKeys can be filled from inPars.

		As a side effect, inPars will receive defaults form the input keys
		if there are any.
		"""
		if not self._isActive(inPars):
			return False
		keysFound, keysMissing = [], []
		for f in self.inputKeys:
			if inPars.get(f.name) is None:
				keysMissing.append(f)
			else:
				keysFound.append(f)
		if not keysMissing:
			return True
		# keys are missing.  That's ok if none were found and we're not required
		if not self.required and not keysFound:
			return False
		if self.required:
			raise base.ValidationError("A value is necessary here", 
				colName=keysMissing[0].name)
		# we're optional, but a value was given and others are missing
		if not self.combining:
			raise base.ValidationError("When you give a value for %s,"
				" you must give value(s) for %s, too"%(keysFound[0].tablehead, 
						", ".join(k.name for k in keysMissing)),
					colName=keysMissing[0].name)

	def asSQL(self, inPars, sqlPars, queryMeta):
		if self.silent or not self.inputReceived(inPars, queryMeta):
			return ""
		res = list(self.makePhrase(self, self.inputKeys, inPars, sqlPars))
		sql = base.joinOperatorExpr("AND", res)
		if self.fixedSQL:
			sql = base.joinOperatorExpr("AND", [sql, self.fixedSQL])
		return sql

	def adaptForRenderer(self, renderer):
		"""returns a changed version of self if renderer suggests such a
		change.

		This only happens if buildFrom is non-None.  The method must
		return a "defused" version that has buildFrom None.
		"""
		if not self.buildFrom:
			return self
		adaptor = getRendererAdaptor(renderer)
		if adaptor is None:
			return self

		newInputKeys = []
		for ik in self.inputKeys:
			newInputKeys.append(adaptor(ik))
		if self.inputKeys==newInputKeys:
			return self
		else:
			return self.change(inputKeys=newInputKeys, buildFrom=None)


def mapDBErrors(excType, excValue, excTb):
	"""translates exception into something we can display properly.
	"""
# This is a helper to all DB-based cores and should probably become
# a method of a baseclass of them when we refactor this mess
	if getattr(excValue, "cursor", None) is not None:
		base.ui.notifyWarning("Failed DB query: %s"%excValue.cursor.query)
	if isinstance(excValue, sqlsupport.QueryCanceledError):
		raise base.ui.logOldExc(base.ValidationError("Query timed out"
			" (took too long).  See our help.", "query"))
	elif isinstance(excValue, base.NotFoundError):
		raise base.ui.logOldExc(base.ValidationError("Could not locate %s '%s'"%(
			excValue.what, excValue.lookedFor), "query"))
	elif isinstance(excValue, base.DBError):
		raise base.ui.logOldExc(base.ValidationError(unicode(excValue), "query"))
	else:
		raise


class TableBasedCore(core.Core):
	"""is a core knowing a DB table it operates on and allowing the definition
	of condDescs.
	"""
	_queriedTable = base.ReferenceAttribute("queriedTable",
		default=base.Undefined, description="A reference to the table"
			" this core queries.", copyable=True, callbacks=["_fixNamePath"])
	_condDescs = base.StructListAttribute("condDescs", childFactory=CondDesc,
		description="Descriptions of the SQL and input generating entities"
			" for this core; if not given, they will be generated from the"
			" table columns.", copyable=True)
	_namePath = rscdef.NamePathAttribute(description="Id of an element"
		" that will be used to located names in id references.  Defaults"
		" to the queriedTable's id.")

	def completeElement(self):
		# if no condDescs have been given, make them up from the table columns.
		if not self.condDescs and self.queriedTable:
			self.condDescs = [self.adopt(CondDesc.fromColumn(c))
				for c in self.queriedTable]

		# if an inputTable is given, trust it fits the condDescs, else
		# build the input table
		if self.inputTable is base.NotGiven:
			iks = []
			for cd in self.condDescs:
				iks.extend(cd.inputKeys)
			self.inputTable = MS(inputdef.InputTable, params=iks)

		# if no outputTable has been given, make it up from the columns
		# of the queried table unless a prototype is defined (which is
		# handled by core itself).
		if self.outputTableXML is None and self.outputTable is base.NotGiven:
			self.outputTable = outputdef.OutputTableDef.fromTableDef(
				self.queriedTable)

		self._completeElementNext(TableBasedCore)

	def _fixNamePath(self, qTable):
# callback from queriedTable to make it the default for namePath as well
		if self.namePath is None:
			self.namePath = qTable.getFullId()

	def _getSQLWhere(self, inputTable, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputTable and queryMeta.
		"""
		sqlPars, frags = {}, []
		inputPars = dict((p.name, p.value) for p in inputTable.iterParams())
		return base.joinOperatorExpr("AND",
			[cd.asSQL(inputPars, sqlPars, queryMeta)
				for cd in self.condDescs]), sqlPars

	def _makeTable(self, rowIter, resultTableDef, queryMeta):
		"""returns a table from the row iterator rowIter, updating queryMeta
		as necessary.
		"""
		rows = list(rowIter)
		isOverflowed =  len(rows)>queryMeta.get("dbLimit", 1e10)
		if isOverflowed:
			del rows[-1]
		queryMeta["Matched"] = len(rows)
		res = rsc.TableForDef(resultTableDef, rows=rows)
		if isOverflowed:
			queryMeta["Overflow"] = True
			res.addMeta("_warning", "The query limit was reached.  Increase it"
				" to retrieve more matches.  Note that unsorted truncated queries"
				" are not reproducible (i.e., might return a different result set"
				" at a later time).")
		return res
	
	def adaptForRenderer(self, renderer):
		"""returns a core tailored to renderer renderers.

		This mainly means asking the condDescs to build themselves for
		a certain renderer.  If no polymorphous condDescs are ther,
		self is returned.
		"""
		newCondDescs = []
		for cd in self.condDescs:
			newCondDescs.append(cd.adaptForRenderer(renderer))
		if newCondDescs!=self.condDescs:
			return self.change(condDescs=newCondDescs, inputTable=base.NotGiven
				).adaptForRenderer(renderer)
		else:
			return core.Core.adaptForRenderer(self, renderer)


class FancyQueryCore(TableBasedCore, base.RestrictionMixin):
	"""A core executing a pre-specified query with fancy conditions.

	Unless you select \*, you *must* define the outputTable here; 
	Weird things will happen if you don't.

	The queriedTable attribute is ignored.
	"""
	name_ = "fancyQueryCore"

	_query = base.UnicodeAttribute("query", description="The query to"
		" execute.  It must contain exactly one %s where the generated"
		" where clause is to be inserted.  Do not write WHERE yourself."
		" All other percents must be escaped by doubling them.", 
		default=base.Undefined,
		copyable=True)

	def run(self, service, inputTable, queryMeta):
		fragment, pars = self._getSQLWhere(inputTable, queryMeta)
		querier = base.SimpleQuerier(connection=getTableConn())
		if fragment:
			fragment = " WHERE "+fragment
		else:
			fragment = ""
		try:
			try:
				return self._makeTable(
					querier.runIsolatedQuery(self.query%fragment, pars,
							silent=True, timeout=queryMeta["timeout"], asDict=True), 
						self.outputTable, queryMeta)
			except:
				mapDBErrors(*sys.exc_info())
		finally:
			querier.close()


class DBCore(TableBasedCore):
	"""A core performing database queries on one table or view.

	DBCores ask the service for the desired output schema and adapt their
	output.  The DBCore's output table, on the other hand, lists all fields 
	available from the queried table.
	"""
	name_ = "dbCore"

	_sortKey = base.UnicodeAttribute("sortKey",
		description="A pre-defined sort order (suppresses DB options widget)."
		"  The sort key accepts multiple columns, separated by commas.",
		copyable=True)
	_limit = base.IntAttribute("limit", description="A pre-defined"
		" match limit (suppresses DB options widget).", copyable=True)
	_distinct = base.BooleanAttribute("distinct", description="Add a"
		" 'distinct' modifier to the query?", default=False, copyable=True)
	_groupBy = base.UnicodeAttribute("groupBy", description=
		"A group by clause.  You shouldn't generally need this, and if"
		" you use it, you must give an outputTable to your core.",
		default=None)

	def wantsTableWidget(self):
		return self.sortKey is None and self.limit is None

	def getQueryCols(self, service, queryMeta):
		"""returns the fields we need in the output table.

		The normal DbBased core just returns whatever the service wants.
		Derived cores, e.g., for special protocols, could override this
		to make sure they have some fields in the result they depend on.
		"""
		return service.getCurOutputFields(queryMeta)

	def _runQuery(self, resultTableDef, fragment, pars, queryMeta,
			**kwargs):
		queriedTable = rsc.TableForDef(self.queriedTable, nometa=True,
			create=False, role="primary", connection=getTableConn())
		queriedTable.setTimeout(queryMeta["timeout"])
		iqArgs = {"limits": queryMeta.asSQL(), "distinct": self.distinct,
			"groupBy": self.groupBy}
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

	def run(self, service, inputTable, queryMeta):
		"""does the DB query and returns an InMemoryTable containing
		the result.
		"""
		resultTableDef = base.makeStruct(outputdef.OutputTableDef,
			parent_=self.queriedTable.parent, id="result",
			onDisk=False, columns=self.getQueryCols(service, queryMeta)
			)
		if not resultTableDef.columns:
			raise base.ValidationError("No output fields with these settings",
				"_OUTPUT")
		sortKeys = None
		if self.sortKey:
			sortKeys = self.sortKey.split(",")
		queryMeta.overrideDbOptions(limit=self.limit, sortKeys=sortKeys)
		try:
			fragment, pars = self._getSQLWhere(inputTable, queryMeta)
		except base.LiteralParseError, ex:
			raise base.ui.logOldExc(base.ValidationError(str(ex),
				colName=ex.attName))
		queryMeta["sqlQueryPars"] = pars
		return self._runQuery(resultTableDef, fragment, pars, queryMeta)


class FixedQueryCore(core.Core, base.RestrictionMixin):
	"""A core executing a predefined query.

	This usually is not what you want, unless you want to expose the current
	results of a specific query, e.g., for log or event data.
	"""
	name_ = "fixedQueryCore"

	_timeout = base.FloatAttribute("timeout", default=15., description=
		"Seconds until the query is aborted")
	_query = base.UnicodeAttribute("query", default=base.Undefined,
		description="The query to be executed.  You must define the"
			" output fields in the core's output table.")

	def completeElement(self):
		if self.inputTable is base.NotGiven:
			self.inputTable = base.makeStruct(inputdef.InputTable)
		self._completeElementNext(FixedQueryCore)

	def run(self, service, inputTable, queryMeta):
		querier = base.SimpleQuerier(connection=getTableConn())
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


class NullCore(core.Core):
	"""A core always returning None.

	This core will not work with the common renderers.  It is really
	intended to go with coreless services (i.e. those in which the
	renderer computes everthing itself and never calls service.runX).
	As an example, the external renderer could go with this.
	"""

	name_ = "nullCore"

	inputTableXML = "<inputTable/>"
	outputTableXML = "<outputTable/>"

	def run(self, service, inputTable, queryMeta):
		return None


class _TableCoreConnectionManager(object):
	"""the database cores all share one autocommitted connection.

	We only make sure it's still open before getting it.  There's
	one instance of this class, instanciated below.
	"""
	def __init__(self):
		self.conn = self._getNewConnection()

	def _getNewConnection(self):
		return base.getDBConnection("trustedquery", autocommitted=True)

	def getConnection(self):
		return self._getNewConnection()
		if self.conn.closed:
			self.conn = self._getNewConnection()
		return self.conn


getTableConn = _TableCoreConnectionManager().getConnection
