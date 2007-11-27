"""
Some standard cores for services.

These implement IVOA or other standards, where communication with
the rest is defined via dictionaries containing the defined parameters on
input and Tables on output.  Thus, at least on output, it is the 
responsibility of the wrapper to produce standards-compliant output.
"""

import weakref
import cStringIO

from twisted.python import log

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import resourcecache
from gavo import record
from gavo import table
from gavo import utils
from gavo import web
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import contextgrammar
from gavo.web import core
from gavo.web import common
from gavo.web import runner
from gavo.web import vizierexprs


class CondDesc(record.Record):
	"""a CondDesc is part of the semantics of a DbBasedCore.  
	
	It defines inputs as InputKeys, so they can be used "naked" if necessary,
	and provide an asSQL method that returns a query fragment.
	"""
	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"inputKeys": record.ListField,
			"silent": record.BooleanField,
		}
		fields.update(additionalFields)
		super(CondDesc, self).__init__(fields, initvals=initvals)

	def addto_inputKeys(self, val):
		self.dataStore["inputKeys"].append(val)

	def asSQL(self, inPars, sqlPars):
		if self.get_silent():
			return ""
		res = []
		for ik in self.get_inputKeys():
			res.append(vizierexprs.getSQL(ik, inPars, sqlPars))
		return vizierexprs.joinOperatorExpr("AND", res)

	@classmethod
	def fromInputKey(cls, ik, attrs={}):
		initvals={
			"inputKeys": [ik],
		}
		initvals.update(attrs)
		return cls(initvals=initvals)


class CondDescFromRd(CondDesc):
	"""is a CondDesc defined in the resource descriptor.
	"""
	pass


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
				utils.raiseTb(web.Error, failure))
	
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
				"sortOrder": None,
				"limit": None,
			}, initvals=initvals)
	
	def set_table(self, val):
		self.dataStore["table"] = val
		self.tableDef = self.rd.getTableDefByName(self.get_table())

	def wantsTableWidget(self):
		return self.get_sortOrder()==None or self.get_limit()==None

	def addDefaultCondDescs(self, *ignored):
		for f in self.get_outputFields():
			ik = contextgrammar.InputKey.makeAuto(f)
			if ik:
				self.addto_condDescs(CondDesc.fromInputKey(ik))

	def addAutoOutputFields(self, queryMeta):
		"""adds field definitions in tableDef suitable for what is given in 
		queryMeta.
		"""
		tableDef = self.tableDef
		if queryMeta:
			verbLevel = queryMeta.get("verbosity", 20)
		if queryMeta and queryMeta["format"]=="HTML":
			fieldList = [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if not (f.get_displayHint()=="suppress" or 
						f.get_verbLevel()>verbLevel)]
		elif queryMeta and queryMeta["format"]=="internal":
			fieldList = [makeCopyingField(f) for f in tableDef.get_items()]
		else:  # Some sort of VOTable
			fieldList = [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if f.get_verbLevel()<=verbLevel and 
					f.get_displayHint()!="suppress"]
		for f in fieldList:
			self.addto_outputFields(f)

	def _getSQLWhere(self, inputTable, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputTable and queryMeta.
		"""
		pars, frags = {}, []
		docRec = inputTable.getDocRec()
		return vizierexprs.joinOperatorExpr("AND",
			[cd.asSQL(docRec, pars)
				for cd in self.get_condDescs()]), pars

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
		limtagsFrag, limtagsPars = queryMeta.asSql(limitOverride=self.get_limit(),
			orderOverride=self.get_sortOrder())
		pars.update(limtagsPars)
		if condition:
			condition = "WHERE %s"%condition
		else:
			condition = ""
		return resourcecache.getDbConnection().runQuery(
			"SELECT %(fields)s from %(table)s %(condition)s %(limtags)s"%{
				"fields": ", ".join([f.get_dest() for f in recordDef.get_items()]),
				"table": tableName,
				"condition": condition,
				"limtags": limtagsFrag,
				}, pars)

	def run(self, inputTable, queryMeta):
		"""returns an InternalDataSet containing the result of the
		query.

		It requires a method _getQuery returning a RecordDef defining
		the result, an SQL WHERE-clause and its parameters.
		"""
		outputDef = resource.RecordDef()
		outputDef.updateFrom(self.tableDef)
# XXX TODO: It's possible that at some point we'd want constraints in
# query interpretation, and it'd ugly to remove them anyway.  I think
# they should go into the grammar.
		outputDef.set_constraints([])
		qFields = self.get_outputFields()
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
		res = resource.InternalDataSet(outputDef, table.Table, dbResponse)
		if queryMeta.get("dbLimit"):
			if len(res.getPrimaryTable().rows)>queryMeta.get("dbLimit"):
				del res.getPrimaryTable().rows[-1]
				queryMeta["Overflow"] = True
		return res


core.registerCore("db", DbBasedCore)
