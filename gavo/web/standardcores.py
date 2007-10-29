"""
Some standard cores for services.

These implement IVOA or other standards, where communication with
the rest is defined via dictionaries containing the defined parameters on
input and Tables on output.  Thus, at least on output, it is the 
responsibility of the wrapper to produce standards-compliant output.
"""

import weakref
import cStringIO

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import resourcecache
from gavo import table
from gavo import utils
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.web import runner
from gavo.web import siap


class ComputedCore(object):
	"""is a core based on a DataDescriptor with a compute attribute.
	"""
	def __init__(self, dd):
		self.dd = dd
	
	def run(self, inputTable, queryMeta):
		"""starts the computing process if this is a computed data set.
		"""
		return runner.run(dd, inputTable).addCallback(
			self._parseOutput, queryMeta).addErrback(
			lambda failure: failure)
	
	def _parseOutput(self, rawOutput, queryMeta):
		"""parses the output of a computing process and returns a table
		if this is a computed dataSet.
		"""
		return resource.InternalDataSet(self, table.Table, 
			cStringIO.StringIO(input), tablesToBuild=["output"])


class DbBasedCore(object):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.
	"""
	def _getFields(self, tableDef, queryMeta):
		"""returns a sequence of field definitions in tableDef suitable for
		queryMeta.
		"""
		if queryMeta["format"]=="HTML":
			return [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if f.get_displayHint() and f.get_displayHint()!="suppress"]
		elif queryMeta["format"]=="internal":
			return [makeCopyingField(f) for f in tableDef.get_items()]
		else:  # Some sort of VOTable
			return [datadef.makeCopyingField(f) for f in tableDef.get_items()
				if f.get_verbLevel()<=queryMeta["verbosity"] and 
					f.get_displayHint!="suppress"]


	def runDbQuery(self, condition, pars, recordDef):
		"""runs a db query with condition and pars to fill a table
		having the columns specified in recordDef.

		It returns a deferred firing when the result is in.
		"""
		schema = self.rd.get_schema()
		if schema:
			tableName = "%s.%s"%(schema, recordDef.get_table())
		else:
			tableName = recordDef.get_table()
		return resourcecache.getDbConnection().runQuery(
			"SELECT %(fields)s from %(table)s WHERE %(condition)s"%{
				"fields": ", ".join([f.get_dest() for f in recordDef.get_items()]),
				"table": tableName,
				"condition": condition}, pars)

	def run(self, inputTable, queryMeta):
		"""returns an InternalDataSet containing the result of the
		query.

		It requires a method _getQuery returning a RecordDef defining
		the result, an SQL WHERE-clause and its parameters.
		"""
		tableDef, fragment, pars = self._getQuery(inputTable, queryMeta)
		outputDef = resource.RecordDef()
		outputDef.updateFrom(tableDef)
		qFields = self._getFields(tableDef, queryMeta)
		outputDef.set_items(qFields)
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(qFields),
			"Semantics": resource.Semantics(initvals={
				"recordDefs": [outputDef]}),
			"id": "<generated>"})
		return self.runDbQuery(fragment, pars, 
				dd.getPrimaryRecordDef()).addCallback(
			self._parseOutput, dd, pars, queryMeta).addErrback(
			lambda failure: failure)

	def _parseOutput(self, dbResponse, outputDef, sqlPars, queryMeta):
		"""builds an InternalDataSet out of the DataDef outputDef
		and the row sequence dbResponse.

		You can retrieve the values used in the SQL query from the dictionary
		sqlPars.
		"""
		return resource.InternalDataSet(outputDef, table.Table, dbResponse)


class SiapCore(DbBasedCore):
	"""is a core doing simple image access protocol queries.

	As an extension to the standard, we automatically resolve simbad objects
	to positions.
	"""
	def __init__(self, rd, tableName="images"):
		self.rd = weakref.proxy(rd)
		self.table = self.rd.getTableDefByName(tableName)

	def getInputFields(self):
		return [
			datadef.DataField(dest="POS", dbtype="text", unit="deg,deg",
				ucd="pos.eq", description="J2000.0 Position, RA,DEC decimal degrees"
				" (e.g., 234.234,-32.45)", tablehead="Position", optional=False,
				source="POS"),
			datadef.DataField(dest="SIZE", dbtype="text", unit="deg,deg",
				description="Size in decimal degrees"
				" (e.g., 0.2 or 1,0.1)", tablehead="Field size", optional=False,
				source="SIZE"),
			datadef.DataField(dest="INTERSECT", dbtype="text", 
				description="Should the image cover, enclose, overlap the ROI or"
				" contain its center?",
				tablehead="Intersection type", default="OVERLAPS", 
				widgetFactory='widgetFactory(SimpleSelectChoice, ['
					'"COVERS", "ENCLOSED", "CENTER"], "OVERLAPS")',
				source="INTERSECT"),
		]

	def _getQuery(self, inputTable, queryMeta):
		return (self.table,)+siap.getBboxQuery(inputTable.getDocRec())

	def _parseOutput(self, dbResponse, outputDef, sqlPars, queryMeta):
		result = super(SiapCore, self)._parseOutput(dbResponse, outputDef,
			sqlPars, queryMeta)
		result.addMeta(name="_type", content="result")
		result.addMeta(name="_query_status", content="OK")
		return result


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
