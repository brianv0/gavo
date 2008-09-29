"""
Some standard cores for services.

A core receives and "input table" (usually just containing the query 
parameters in the doc rec) and returns an output data set (which is promoted
to a SvcResult in the service before being handed over to the renderer).

These then have to be picked up by renderers and formatted for delivery.
"""

import weakref
import cStringIO

from twisted.internet import defer
from twisted.internet import threads
from twisted.python import log

import gavo
from gavo import adql
from gavo import adqlglue
from gavo import config
from gavo import coords
from gavo import datadef
from gavo import interfaces
from gavo import resourcecache
from gavo import record
from gavo import sqlsupport
from gavo import table
from gavo import utils
from gavo import web
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import contextgrammar
from gavo.web import adbapiconn
from gavo.web import core
from gavo.web import common
from gavo.web import runner
from gavo.web import vizierexprs


printQuery = False

class CondDesc(record.Record):
	"""a CondDesc is part of the semantics of a DbBasedCore.  
	
	It defines inputs as InputKeys, so they can be used "naked" if necessary,
	and provide an asSQL method that returns a query fragment.

	"silent" condDescs only contribute widgets, no SQL.  This can be used
	for "meta" input for renderers (as opposed to the core).
	"""
	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"inputKeys": record.ListField,
			"silent": record.BooleanField,
			"optional": record.TrueBooleanField,
			"fixedSQL": None,
		}
		fields.update(additionalFields)
		record.Record.__init__(self, fields, initvals=initvals)

	def get_dest(self):
		"""returns some key for uniqueness of condDescs.
		"""
		# This is necessary for record.DataFieldLists that are used
		# for CondDescs as well.  Ideally, we'd do this on an
		# InputKeys basis and yield their dests (because that's what
		# formal counts on), but it's probably not worth the effort.
		return "+".join([f.get_dest() for f in self.get_inputKeys()])

	def addto_inputKeys(self, val):
		self.dataStore["inputKeys"].append(val)

	def inputReceived(self, inPars):
		"""returns True if all inputKeys can be filled from inPars.
		"""
		keysFound, keysMissing = [], []
		for f in self.get_inputKeys():
			if not inPars.has_key(f.get_source()) or inPars[f.get_source()] is None:
				keysMissing.append(f)
			else:
				keysFound.append(f)
		if not keysMissing:
			return True
		# keys are missing.  That's ok if none were found and we're not optional
		if self.get_optional() and not keysFound:
			return False
		if not self.get_optional():
			raise gavo.ValidationError("A value is necessary here", 
				fieldName=keysMissing[0].get_source())
		# we're optional, but a value was given
# XXX TODO: it'd be nicer if we'd complain about all missing keys at once.
		raise gavo.ValidationError("When you give a value for %s,"
			" you must give a value here, too"%keysFound[0].get_tablehead(), 
				fieldName=keysMissing[0].get_source())

	def asSQL(self, inPars, sqlPars):
		if self.get_silent():
			return ""
		res = []
		for ik in self.get_inputKeys():
			res.append(vizierexprs.getSQL(ik, inPars, sqlPars))
		sql = vizierexprs.joinOperatorExpr("AND", res)
		if self.get_fixedSQL():
			sql = vizierexprs.joinOperatorExpr("AND", [sql, self.get_fixedSQL()])
		return sql

	@classmethod
	def fromInputKey(cls, ik, attrs={}):
		initvals={
			"inputKeys": [ik],
		}
		initvals.update(attrs)
		return cls(initvals=initvals)
	

class StaticCore(core.Core):
	"""is a core that always returns a static file.
	"""
	outputFields = [datadef.DataField(dest="filename", dbtype="text",
			source="filename", optional=False)]

	def __init__(self, rd, initvals={}, additionalFields={}):
		self.rd = weakref.proxy(rd)
		fields = {
			"file": None,
		}
		fields.update(additionalFields)
		self.avOutputKeys = [f.get_dest() for f in self.outputFields]
		core.Core.__init__(self, initvals=initvals, 
			additionalFields=fields)

	def run(self, inputData, queryMeta):
		return defer.succeed(resource.InternalDataSet(
			resource.makeRowsetDataDesc(self.rd, self.outputFields),
			dataSource=[(self.get_file(),)]))

core.registerCore("static", StaticCore)


class QueryingCore(core.Core):
	"""is an abstract core for anything working on a resource descriptor
	
	At the very least, you need to provide a run method to make this useful.
	"""
	def __init__(self, rd, initvals={}, additionalFields={}):
		self.rd = weakref.proxy(rd)
		fields = {
		}
		fields.update(additionalFields)
		core.Core.__init__(self, additionalFields=fields,
			initvals=initvals)

	
class ComputedCore(QueryingCore):
	"""is a core based on a DataDescriptor with a compute attribute.
	"""
	def __init__(self, rd, initvals):
		QueryingCore.__init__(self, rd, additionalFields={
			"ddId": record.RequiredField,     # dd describing our in- and output.
			"computer": record.RequiredField, # our binary
			}, initvals=initvals)
		self.dd = self.rd.getDataById(self.get_ddId())
		self.avInputKeys = set() # FIXME: We don't know these, they're not in the DD
		self.outputFields = self.dd.getTableDefByName("output").get_items()
		self.avOutputKeys = set([f.get_dest() 
			for f in self.outputFields])

	def getOutputFields(self):
		return self.outputFields

	def run(self, inputData, queryMeta):
		"""starts the computing process if this is a computed data set.
		"""
		inputData.validate()
		return runner.run(self.dd, inputData).addCallback(
			self._parseOutput, queryMeta).addErrback(
			lambda failure:
				gavo.raiseTb(web.Error, failure))
	
	def _parseOutput(self, rawOutput, queryMeta):
		"""parses the output of a computing process and returns a table
		if this is a computed dataSet.
		"""
		return resource.InternalDataSet(self.dd, table.Table, 
			cStringIO.StringIO(rawOutput), tablesToBuild=["output"])
core.registerCore("computed", ComputedCore)


def mapDbErrors(failure):
	"""logs the failure and translates the exception into something our
	system can display more beautifully.
	"""
	failure.printTraceback()
# This is a helper to all DB-based cores and should probably become
# a method of a baseclass of them when we refactor this mess
	if hasattr(failure.value, "cursor"):
		log.msg("Failed DB query: %s"%failure.value.cursor.query)
# XXX TODO: Alejandro's pgsql timeout patch somehow doesn't expose 
# TimeoutError, and I don't have time to fix this now.  So, I check the 
# exception type the rough way.
	if failure.value.__class__.__name__.endswith("TimeoutError"):
		raise gavo.ValidationError("Query timed out (took too long).  See"
			" our help.", "query")
	elif isinstance(failure.value, sqlsupport.DbError):
		raise gavo.ValidationError(failure.getErrorMessage(), "query")
	elif isinstance(failure.value, adqlglue.ParseException):
		raise gavo.ValidationError("Could not parse your query: %s"%
			failure.getErrorMessage(), "query")
	elif isinstance(failure.value, adql.ColumnNotFound):
		raise gavo.ValidationError("No such field known: %s"%
			failure.getErrorMessage(), "query")
	elif isinstance(failure.value, adql.AmbiguousColumn):
		raise gavo.ValidationError("%s needs to be qualified."%
			failure.getErrorMessage(), "query")
	else:
		raise failure.value


class DbBasedCore(QueryingCore):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.

	Db cores must define a _getQuery(inputData, queryMeta) method that
	returns a data descriptor for the expected SQL output, an SQL fragment 
	and a dictionary mapping the parameters of that
	query to values understandable by the DB interface.
	"""
	def __init__(self, rd, initvals):
		QueryingCore.__init__(self, rd, additionalFields={
				"table": record.RequiredField,
				"sortOrder": common.Undefined,
				"limit": common.Undefined,
				"distinct": record.BooleanField,
				"feedbackField": None,
			}, initvals=initvals)
		self.validate()
		self.avOutputKeys = set([f.get_dest() for f in self.tableDef.get_items()])
		self.avInputKeys = self.avOutputKeys

	def getInputFields(self):
		return self.tableDef.get_items()
	
	def getOutputFields(self):
		return record.DataFieldList([datadef.OutputField.fromDataField(f) 
			for f in self.tableDef.get_items()])

	def set_table(self, val):
		self.dataStore["table"] = val
		self.tableDef = self.rd.getTableDefByName(self.get_table())

	def wantsTableWidget(self):
		return (self.get_sortOrder()==common.Undefined or 
			self.get_limit()==common.Undefined)

	def _getSQLWhere(self, inputData, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputData and queryMeta.
		"""
		pars, frags = {}, []
		docRec = inputData.getDocRec()
		return vizierexprs.joinOperatorExpr("AND",
			[cd.asSQL(docRec, pars)
				for cd in self.get_service().get_condDescs()]), pars

	def runDbQuery(self, condition, pars, tableDef, queryMeta):
		"""runs a db query with condition and pars to fill a table
		having the columns specified in tableDef.

		It returns a deferred firing when the result is in.
		"""
		tableName = tableDef.getQName()
		queryMeta.overrideDbOptions(limit=self.get_limit(), 
			sortKey=self.get_sortOrder())
		limtagsFrag, limtagsPars = queryMeta.asSql()
		pars.update(limtagsPars)
		if condition:
			condition = "WHERE %s"%condition
		else:
			condition = ""
		distinctTerm = ""
		if self.get_distinct():
			distinctTerm = "DISTINCT "
		if not tableDef.get_items():
			raise gavo.ValidationError("No output fields with these settings",
				"_OUTPUT")
		query = ("SELECT %(distinctTerm)s%(fields)s from %(table)s"
				" %(condition)s %(limtags)s")%{
			"fields": ", ".join([f.get_select() for f in tableDef.get_items()
				if f.get_select()!="NULL"]),
			"table": tableName,
			"condition": condition,
			"limtags": limtagsFrag,
			"distinctTerm": distinctTerm,
		}
		if printQuery:
			print ">>>>", query, pars
		return resourcecache.getDbConnection(None).runQuery(query, pars,
			timeout=config.get("web", "sqlTimeout"))

	def getQueryFields(self, queryMeta):
		"""returns the fields we need in the output table.

		The normal DbBased core just returns whatever the service wants.
		Derived cores, e.g., for special protocols, could override this
		to make sure they have some fields in the result they depend on.
		"""
		fields = self.get_service().getCurOutputFields(queryMeta)
		if self.get_feedbackField():
			fields.insert(0, makeFeedbackField(fields, self.get_feedbackField()))
		return fields

	def run(self, inputData, queryMeta):
		"""returns an InternalDataSet containing the result of the
		query.

		It requires a method _getQuery returning a TableDef defining
		the result, an SQL WHERE-clause and its parameters.
		"""
		outputDef = resource.TableDef(self.rd)
		outputDef.updateFrom(self.tableDef)
# XXX TODO: It's possible that at some point we'd want constraints in
# query interpretation, and it's ugly to remove them anyway.  I think
# they should go into the grammar.
		outputDef.set_constraints([])
		qFields = self.getQueryFields(queryMeta)
		outputDef.set_items(qFields)
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(initvals={
				"dbFields": qFields}),
			"Semantics": resource.Semantics(initvals={
				"tableDefs": [outputDef]}),
			"id": "<generated>"})
		fragment, pars = self._getSQLWhere(inputData, queryMeta)
		return self.runDbQuery(fragment, pars, 
				dd.getPrimaryTableDef(), queryMeta).addCallback(
			self._parseOutput, dd, pars, queryMeta).addErrback(
			mapDbErrors)

	def _parseOutput(self, dbResponse, outputDef, sqlPars, queryMeta):
		"""builds an InternalDataSet out of the DataDef outputDef
		and the row sequence dbResponse.

		You can retrieve the values used in the SQL query from the dictionary
		sqlPars.
		"""
		queryMeta["sqlQueryPars"] = sqlPars
		res = resource.InternalDataSet(outputDef, table.Table, dbResponse)
		if queryMeta.get("dbLimit"):
			if len(res.getPrimaryTable().rows)>queryMeta.get("dbLimit"):
				del res.getPrimaryTable().rows[-1]
				queryMeta["Overflow"] = True
		return res
core.registerCore("db", DbBasedCore)


def makeFeedbackField(fields, fieldName):
	ff = datadef.OutputField.fromDataField(fields.getFieldByName(fieldName))
	ff.set_dest("feedbackSelect")
	ff.set_select(fieldName)
	ff.set_tablehead("F")
	ff.set_description("Check to include row in feedback set")
	ff.set_displayHint("type=feedbackSelect")
	return ff


class FeedbackCore(DbBasedCore):
	rangeTypes = frozenset(["vexpr-date", "vexpr-float"])
	enumeratedTypes = frozenset(["vexpr-string"])

	def __init__(self, tableDef, service, feedbackColN):
		self.tableDef = tableDef
		self.service = service
		self.feedbackColN = feedbackColN

	@classmethod
	def fromCore(cls, core):
		return cls(core.tableDef, core.get_service(), core.get_feedbackField())

	def _getFeedbackableNames(self):
		rangedNames, enumeratedNames = [], []
		for f in self.service.getInputFields():
			if f.get_dbtype() in self.rangeTypes:
				rangedNames.append(f.get_dest())
			if f.get_dbtype() in self.enumeratedTypes:
				enumeratedNames.append(f.get_dest())
		return rangedNames, enumeratedNames

	def run(self, inData, queryMeta):
		feedbackKeys = [r["feedbackSelect"] 
			for r in inData.getPrimaryTable().rows]
		rangeNames, enumeratedNames = self._getFeedbackableNames()
		return resourcecache.getDbConnection(None).runQuery(
			"SELECT %s FROM %s WHERE %s IN %%(feedbackKeys)s"%(
				", ".join(["MIN(%s), MAX(%s)"%(n,n) for n in rangeNames]),
				self.tableDef.getQName(), self.feedbackColN),
			{"feedbackKeys": feedbackKeys}
			).addCallback(self._processRanged, rangeNames, enumeratedNames,
					feedbackKeys
			).addErrback(mapDbErrors)
		
	def _processRanged(self, result, rangeNames, enumeratedNames, feedbackKeys):
		result = result[0]
		rowdict = {}
		for index, n in enumerate(rangeNames):
			rowdict[n] = "%s .. %s"%(result[2*index], result[2*index+1])
		return self._queryEnumerated(rowdict, enumeratedNames, feedbackKeys)
	
	def _queryEnumerated(self, rowdict, enumeratedNames, feedbackKeys):
# XXX I'm lazy here and return a dict, since FeedbackForm is the only
#			renderer possible for this core.   Should be fixed, I guess.
		if not enumeratedNames:
			return rowdict
		name = enumeratedNames.pop()
		return resourcecache.getDbConnection(None).runQuery(
			"SELECT DISTINCT %s FROM %s WHERE %s IN %%(feedbackKeys)s"%(name,
				self.tableDef.getQName(), self.feedbackColN),
			{"feedbackKeys": feedbackKeys}
			).addCallback(self._processEnumQuery, name, rowdict, enumeratedNames,
				feedbackKeys)

	def _processEnumQuery(self, dbRes, name, rowdict, 
			enumeratedNames, feedbackKeys):
		keys = [r[0] for r in dbRes]
		if len(keys)<15: # Ignore field if too many items matched to avoid
				# gargantuous strings
			rowdict[name] = "=,%s"%(','.join(keys))
		return self._queryEnumerated(rowdict, enumeratedNames, feedbackKeys)


class FixedQueryCore(QueryingCore):
	def __init__(self, rd, initvals):
		QueryingCore.__init__(self, rd, additionalFields={
				"query": record.RequiredField,
				"timeout": 15,
			}, initvals=initvals)

	def set_timeout(self, val):
		self.dataStore["timeout"] = int(val)

	def run(self, inputData, queryMeta):
		if self.get_query().upper().startswith("SELECT"):
			fun = resourcecache.getDbConnection(None).runQuery
		else:
			fun = resourcecache.getDbConnection(None).runOperation
		return fun(self.get_query(), timeout=self.get_timeout()
			).addCallback(self._parseOutput, queryMeta
			).addErrback(mapDbErrors)

	def _parseOutput(self, dbResponse, queryMeta):
		"""builds an InternalDataSet out of dbResponse and the outputFields
		of our service.
		"""
		if dbResponse is None:
			dbResponse = []
		outputDD = resource.makeRowsetDataDesc(self.rd, 
			self.get_service().get_outputFields(), mungeFields=False)
		res = resource.InternalDataSet(outputDD, table.Table, 
			dataSource=dbResponse)
		return res

core.registerCore("runFixedQuery", FixedQueryCore)


class ADQLCore(QueryingCore):
	"""is a core that takes an ADQL query from its query argument and
	returns the query result.
	"""
	noPostprocess = True

	def __init__(self, rd, initvals):
		QueryingCore.__init__(self, rd)
		self.validate()

	def getInputFields(self):
		return [
			contextgrammar.InputKey(dest="query", tablehead="ADQL query",
				description="A query in the Astronomical Data Query Language",
				dbtype="text", source="query", 
				widgetFactory="widgetFactory(TextArea, rows=10, cols=60)"),
		]
	
	def getOutputFields(self):
		return []
	
	def wantsTableWidget(self):
		return False

	def run(self, inputData, queryMeta):
		return threads.deferToThread(adqlglue.query,
				inputData.getDocRec()["query"],
				timeout=config.get("web", "adqlTimeout"),
				queryProfile="untrustedquery"
			).addErrback(mapDbErrors)
core.registerCore("adql", ADQLCore)
