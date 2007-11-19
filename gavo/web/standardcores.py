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
from gavo.web import common
from gavo.web import runner
from gavo.web import siap
from gavo.web import vizierexprs


class Core(record.Record):
	"""is something that does computations for a service.
	"""
	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"table": record.RequiredField,
			"condDescs": record.ListField,
		}
		fields.update(additionalFields)
		super(Core, self).__init__(fields, initvals=initvals)

	def run(self, inputData, queryMeta):
		"""returns a twisted deferred firing the result of running the core on
		inputData.
		"""


class ComputedCore(Core):
	"""is a core based on a DataDescriptor with a compute attribute.
	"""
	def __init__(self, dd):
		self.dd = dd
		super(ComputedCore, self).__init__()
	
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


class DbBasedCore(Core):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.

	Db cores must define a _getQuery(inputTable, queryMeta) method that
	returns a data descriptor for the expected SQL output, an SQL fragment 
	and a dictionary mapping the parameters of that
	query to values understandable by the DB interface.

	Db cores should try to define a getOutputFields(queryMeta) method returning
	the field defintions of the output fields, but clients should not rely
	on their presence.
	"""
	def __init__(self, rd, initvals):
		self.rd = weakref.proxy(rd)
		super(DbBasedCore, self).__init__(initvals=initvals)
	
	def set_table(self, val):
		self.dataStore["table"] = val
		self.tableDef = self.rd.getTableDefByName(self.get_table())

	def addto_condDescs(self, val):
		if isinstance(val, vizierexprs.CondDesc):
			self.dataStore["condDescs"].append(val)
		elif val=="fromOutput":
			for f in self.getOutputFields(common.QueryMeta({})):
				cd = vizierexprs.getAutoCondDesc(f)
				if cd:
					self.dataStore["condDescs"].append(cd)
		else:  # argument is field name
			self.dataStore["condDescs"].append(
				vizierexprs.FieldCondDesc(val, self.tableDef.getFieldByName(val)))

	def getInputFields(self):
		if not hasattr(self, "_inputFields"):
			self._inputFields = []
			for cd in self.get_condDescs():
				self._inputFields.extend(cd.getInputFields())
		return self._inputFields

	def _getFilteredOutputFields(self, tableDef, queryMeta=None):
		"""returns a sequence of field definitions in tableDef suitable for
		what is given in queryMeta.
		"""
		if queryMeta and queryMeta["format"]=="HTML":
			return [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if f.get_displayHint() and f.get_displayHint()!="suppress"]
		elif queryMeta and queryMeta["format"]=="internal":
			return [makeCopyingField(f) for f in tableDef.get_items()]
		else:  # Some sort of VOTable
			return [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if f.get_verbLevel()<=queryMeta["verbosity"] and 
					f.get_displayHint!="suppress"]

	def _getSQLWhere(self, inputTable, queryMeta):
		"""returns a where fragment and the appropriate parameters
		for the query defined by inputTable and queryMeta.
		"""
		pars, frags = {}, []
		docRec = inputTable.getDocRec()
		return vizierexprs.joinOperatorExpr("AND",
			[condDesc.getQueryFrag(docRec, pars, queryMeta)
				for condDesc in self.get_condDescs()]), pars
		
	def getOutputFields(self, queryMeta):
		return self._getFilteredOutputFields(self.tableDef, queryMeta)

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
		limtagsFrag, limtagsPars = queryMeta.asSql()
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
		qFields = self.getOutputFields(queryMeta)
		outputDef.set_items(qFields)
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(qFields),
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


class SiapCore(DbBasedCore):
	"""is a core doing simple image access protocol queries.

	As an extension to the standard, we automatically resolve simbad objects
	to positions.
	"""
	def __init__(self, rd, args):
		super(SiapCore, self).__init__(rd, args)
		self.addto_condDescs(siap.SiapCondition())


class SiapCutoutCore(SiapCore):
	"""is a core doing siap and handing through query parameters to
	the product delivery asking it to only retrieve certain portions
	of images.
	"""
	def _parseOutput(self, dbResponse, outputDef, sqlPars, queryMeta):
		res = super(SiapCutoutCore, self)._parseOutput(
			dbResponse, outputDef, sqlPars, queryMeta)
		for row in res.getPrimaryTable():
			row["datapath"] = row["datapath"]+"&ra=%s&dec=%s&sra=%s&sdec=%s"%(
				sqlPars["_ra"], sqlPars["_dec"], sqlPars["_sra"], sqlPars["_sdec"])
		return res


_coresRegistry = {
	"siap": SiapCore,
	"siapcutout": SiapCutoutCore,
}


def getStandardCore(coreName):
	return _coresRegistry[coreName]
