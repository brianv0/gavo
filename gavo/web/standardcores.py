"""
Some standard cores for services.

These implement IVOA or other standards, where communication with
the rest is defined via dictionaries containing the defined parameters on
input and Tables on output.  Thus, at least on output, it is the 
responsibility of the wrapper to produce standards-compliant output.
"""

import weakref
import cStringIO

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
		runner.run(dd, inputTable)
	
	def parseOutput(self, rawOutput, queryMeta):
		"""parses the output of a computing process and returns a table
		if this is a computed dataSet.
		"""
		return resource.InternalDataSet(self, table.Table, 
			cStringIO.StringIO(input), tablesToBuild=["output"])


class DbBasedCore(object):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table
	from it.

	To use the methods, your deriving class currently needs to provide a
	tableName attribute (since an RD can provide more than one table).  That's a
	bad wart that needs to be fixed.

	Note that the methods provided here (run, parseOutput) are *not*
	immediately suitable for cooperation with Service since service
	doesn't provide tableDef or query.  You'll have to override this
	method in derived classes and fill in tableDef.
	"""
	def _getFields(self, tableDef, queryMeta):
		"""returns a sequence of field definitions in tableDef suitable for
		queryMeta.
		"""
		def makeCopyingField(field):
			newField = datadef.DataField()
			newField.updateFrom(field)
			newField.set_source(field.get_dest())
			return newField
		if queryMeta["format"]=="HTML":
			return [makeCopyingField(f) for f in tableDef.get_items()
				if f.get_displayHint() and f.get_displayHint()!="suppress"]
		elif queryMeta["format"]=="internal":
			return [makeCopyingField(f) for f in tableDef.get_items()]
		else:  # Some sort of VOTable
			return [makeCopyingField(f) for f in tableDef.get_items()
				if f.get_verbLevel()<=queryMeta["verbosity"] and 
					f.get_displayHint!="suppress"]

	def run(self, condition, pars, queryMeta):
		schema = self.rd.get_schema()
		if schema:
			tableName = "%s.%s"%(schema, self.tableName)
		else:
			tableName = self.tableName
		tableDef = self.rd.getTableDefByName(self.tableName)
		fields = ", ".join([f.get_dest() 
			for f in self._getFields(tableDef, queryMeta)])
		return resourcecache.getDbConnection().runQuery(
			"SELECT %(fields)s from %(table)s WHERE %(condition)s"%{
				"fields": fields,
				"table": tableName,
				"condition": condition}, pars)

	def parseOutput(self, dbResponse, tableDef, queryMeta):
		"""builds an InternalDataSet out of the RecordDef tableDef
		and the row set dbResponse.

		"""
		outputDef = resource.RecordDef()
		outputDef.updateFrom(tableDef)
		qFields = self._getFields(tableDef, queryMeta)
		outputDef.set_items(qFields)
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(qFields),
			"Semantics": resource.Semantics(initvals={
				"recordDefs": [outputDef]}),
			"id": "<generated>"})
		return resource.InternalDataSet(dd, table.Table, dbResponse)


class SiapCore(DbBasedCore):
	"""is a core doing simple image access protocol queries.

	As an extension to the standard, we automatically resolve simbad objects
	to positions.
	"""
	def __init__(self, rd, tableName="images"):
		self.tableName = tableName
		self.rd = weakref.proxy(rd)

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

	def run(self, inputTable, queryMeta):
		fragment, pars = siap.getBboxQuery(inputTable.getDocRec())
		return super(SiapCore, self).run(fragment, pars, queryMeta)

	def parseOutput(self, dbResponse, queryMeta):
		result = super(SiapCore, self).parseOutput(dbResponse, 
			self.rd.getTableDefByName(self.tableName), queryMeta)
		result.addMeta(name="_type", content="result")
		result.addMeta(name="_query_status", content="OK")
		return result


_coresRegistry = {
	"siap": SiapCore,
}


def getStandardCore(coreName):
	return _coresRegistry[coreName]
