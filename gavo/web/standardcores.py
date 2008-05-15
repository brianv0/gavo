"""
Some standard cores for services.

A core receives and "input table" (usually just containing the query 
parameters in the doc rec) and returns an output data set (which is promoted
to a CoreResult in the service before being handed over to the renderer).

These then have to be picked up by renderers and formatted for delivery.
"""

import weakref
import cStringIO

from twisted.internet import defer
from twisted.python import log

import gavo
from gavo import config
from gavo import coords
from gavo import datadef
from gavo import interfaces
from gavo import resourcecache
from gavo import record
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
		super(CondDesc, self).__init__(fields, initvals=initvals)

	def addto_inputKeys(self, val):
		self.dataStore["inputKeys"].append(val)

	def inputReceived(self, inPars):
		"""returns True if all inputKeys can be filled from inPars.
		"""
		keysFound, keysMissing = [], []
		for f in self.get_inputKeys():
			if not inPars.has_key(f.get_source()) or inPars[f.get_source()]==None:
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
	def __init__(self, rd, initvals={}, additionalFields={}):
		self.rd = weakref.proxy(rd)
		fields = {
			"file": None,
		}
		fields.update(additionalFields)
		super(StaticCore, self).__init__(initvals=initvals, 
			additionalFields=fields)
		self.addto_outputFields(datadef.DataField(dest="filename", dbtype="text",
			source="filename", optional=False))

	def run(self, inputData, queryMeta):
		return defer.succeed(resource.InternalDataSet(
			resource.makeRowsetDataDesc(self.rd, self.getOutputFields(queryMeta)),
			dataSource=[(self.get_file(),)]))

core.registerCore("static", StaticCore)


class QueryingCore(core.Core):
	"""is an abstract core for anything working on a resource descriptor
	
	At the very least, you need to provide a run method to make this useful.
	"""
	def __init__(self, rd, initvals={}, additionalFields={}):
		self.rd = weakref.proxy(rd)
		fields = {
			"condDescs": record.ListField,
		}
		fields.update(additionalFields)
		super(QueryingCore, self).__init__(additionalFields=fields,
			initvals=initvals)

	def addDefaultCondDescs(self, queryMeta):
		"""adds condition descriptors matching what is currently defined as
		output fields.
		"""

	def addAutoOutputFields(self, queryMeta):
		"""adds field definitions in tableDef suitable for what is given in 
		queryMeta.
		"""

	def getInputFields(self):
		res = []
		for cd in self.get_condDescs():
			res.extend(cd.get_inputKeys())
		return res

	
class ComputedCore(core.Core):
	"""is a core based on a DataDescriptor with a compute attribute.
	"""
# XXX TODO: make this inherit from querying core, i.e., it's constructed
# with an RD, and the data descriptor is passed in by name, pretty much
# like UploadCore
	def __init__(self, dd, initvals):
		self.dd = dd
		super(ComputedCore, self).__init__(initvals=initvals)
	
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


class DbBasedCore(QueryingCore):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.

	Db cores must define a _getQuery(inputTable, queryMeta) method that
	returns a data descriptor for the expected SQL output, an SQL fragment 
	and a dictionary mapping the parameters of that
	query to values understandable by the DB interface.
	"""
	def __init__(self, rd, initvals):
		super(DbBasedCore, self).__init__(rd, additionalFields={
				"table": record.RequiredField,
				"sortOrder": common.Undefined,
				"limit": common.Undefined,
			}, initvals=initvals)
		self.validate()
	
	def set_table(self, val):
		self.dataStore["table"] = val
		self.tableDef = self.rd.getTableDefByName(self.get_table())

	def wantsTableWidget(self):
		return (self.get_sortOrder()==common.Undefined or 
			self.get_limit()==common.Undefined)

	def addDefaultCondDescs(self, *ignored):
# XXX this is a pain.  Do away with it, thinking of something better
		for f in self.get_outputFields():
			ik = contextgrammar.InputKey.makeAuto(f)
			if ik:
				self.addto_condDescs(CondDesc.fromInputKey(ik))

	def addAutoOutputFields(self, queryMeta):
		"""adds all fields matching verbLevel<=queryMeta["verbosity"].

		This is used by the import parser.
		"""
		verbLimit = queryMeta.get("verbosity", 20)
		for f in self.tableDef.get_items():
			if f.get_verbLevel()<=verbLimit:
				self.addto_outputFields(datadef.OutputField.fromDataField(f))

	def _getVOTableOutputFields(self, queryMeta):
		"""returns a list of OutputFields suitable for a VOTable response described
		by queryMeta
		"""
		verbLevel = queryMeta.get("verbosity", 20)
		fieldList = [datadef.OutputField.fromDataField(f) 
			for f in self.tableDef.get_items()
			if f.get_verbLevel()<=verbLevel and 
				f.get_displayHint().get("type")!="suppress"]
		return fieldList

	def _getHTMLOutputFields(self, queryMeta):
		"""returns a list of OutputFields suitable for an HTML response described
		by queryMeta
		"""
		res = self.get_outputFields()
		keysPresent = set([f.get_dest() for f in res])
		for dest in queryMeta.get("additionalFields", []):
			try:
				if dest in keysPresent:
					continue
				res.append(datadef.OutputField.fromDataField(
					self.tableDef.getFieldByName(dest)))
				keysPresent.add(dest)
			except KeyError:  # ignore orders for non-existent fields
				pass
		return res

	def _getTarOutputFields(self, queryMeta):
		reqFields = interfaces.Products.requiredFields
		res = [datadef.OutputField.fromDataField(f) 
			for f in self.tableDef.get_items() 
			if f.get_dest() in reqFields]
		if len(reqFields)!=len(res):
			raise gavo.Error("We're sorry, this table cannot produce tar files.")
		return res

	def _getAllOutputFields(self, queryMeta):
		"""returns a list of all OutputFields of the source table, with
		their sources set to their dests.
		"""
		return [datadef.OutputField.fromDataField(f) for f in self.tableDef]

	def getOutputFields(self, queryMeta):
		"""returns a list of OutputFields suitable for a response described by
		queryMeta.

		This evaluates stuff like verbosity and additionalFields.
		"""
		format = queryMeta.get("format")
		if format=="VOTable" or format=="VOPlot" or format=="FITS":
			return self._getVOTableOutputFields(queryMeta)
		elif format=="internal":
			return self._getAllFields(queryMeta)
		elif format=="tar":
			return self._getTarOutputFields(queryMeta)
		return self._getHTMLOutputFields(queryMeta)

	def _getSQLWhere(self, inputTable, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputTable and queryMeta.
		"""
		pars, frags = {}, []
		docRec = inputTable.getDocRec()
		return vizierexprs.joinOperatorExpr("AND",
			[cd.asSQL(docRec, pars)
				for cd in self.get_condDescs()]), pars

	def _getSelect(self, f):
		# This should go -- the recordDefs passed in here should be comprised
		# of OutputFields exclusively.
		if isinstance(f, datadef.OutputField):
			return f.get_select()
		else:
			return f.get_dest()

	def runDbQuery(self, condition, pars, recordDef, queryMeta):
		"""runs a db query with condition and pars to fill a table
		having the columns specified in recordDef.

		It returns a deferred firing when the result is in.
		"""
		schema = self.rd.get_schema()
		if schema:
			tableName = "%s.%s"%(schema, recordDef.get_table())
		else:
			tableName = recordDef.get_table()
		queryMeta.overrideDbOptions(limit=self.get_limit(), 
			sortKey=self.get_sortOrder())
		limtagsFrag, limtagsPars = queryMeta.asSql()
		pars.update(limtagsPars)
		if condition:
			condition = "WHERE %s"%condition
		else:
			condition = ""
		if not recordDef.get_items():
			raise gavo.ValidationError("No output fields with these settings",
				"_OUTPUT")
		query = "SELECT %(fields)s from %(table)s %(condition)s %(limtags)s"%{
			"fields": ", ".join([self._getSelect(f) for f in recordDef.get_items()]),
			"table": tableName,
			"condition": condition,
			"limtags": limtagsFrag,
		}
		if printQuery:
			print ">>>>", query, pars
		return resourcecache.getDbConnection(None).runQuery(query, pars,
			timeout=config.get("web", "sqlTimeout"))

	def run(self, inputTable, queryMeta):
		"""returns an InternalDataSet containing the result of the
		query.

		It requires a method _getQuery returning a RecordDef defining
		the result, an SQL WHERE-clause and its parameters.
		"""
		outputDef = resource.RecordDef()
		outputDef.updateFrom(self.tableDef)
# XXX TODO: It's possible that at some point we'd want constraints in
# query interpretation, and it's ugly to remove them anyway.  I think
# they should go into the grammar.
		outputDef.set_constraints([])
		qFields = self.getOutputFields(queryMeta)
		outputDef.set_items(qFields)
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(initvals={
				"dbFields": qFields}),
			"Semantics": resource.Semantics(initvals={
				"recordDefs": [outputDef]}),
			"id": "<generated>"})
		fragment, pars = self._getSQLWhere(inputTable, queryMeta)
		return self.runDbQuery(fragment, pars, 
				dd.getPrimaryRecordDef(), queryMeta).addCallback(
			self._parseOutput, dd, pars, queryMeta).addErrback(
			self._logFailedQuery)

	def _logFailedQuery(self, failure):
		if hasattr(failure.value, "cursor"):
			log.msg("Failed DB query: %s"%failure.value.cursor.query)
		return failure

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
