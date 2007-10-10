"""
Some standard cores for services.

These implement IVOA or other standards, where communication with
the rest is defined via dictionaries containing the defined parameters on
input and Tables on output.  Thus, at least on output, it is the 
responsibility of the wrapper to produce standards-compliant output.
"""

import weakref

from gavo import coords
from gavo import datadef
from gavo import resourcecache
from gavo import table
from gavo import utils
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar


class DbBasedCore(object):
	"""is a base class for cores doing database queries.

	It provides for querying the database and returning a table from it.
	"""
	def parseOutput(self, dbResponse, tableDef):
		"""builds an InternalDataSet out of the RecordDef tableDef and the
		row set dbResponse.

		Note that this method is *not* suitable for cooperation with Service
		since service doesn't provide tableDef.  You'll have to override
		this method in derived classes and fill in table.
		"""
		dd = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(tableDef),
			"Semantics": resource.Semantics(initvals={
				"recordDefs": [tableDef]}),
			"id": "<generated>"})
		return resource.InternalDataSet(dd, table.Table, dbResponse)


class SiapCore(DbBasedCore):
	"""is a core doing simple image access protocol queries.
	"""
	def __init__(self, rd, tableName):
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
				source="POS"),
			datadef.DataField(dest="INTERSECT", dbtype="text", 
				description="Should the image cover, enclose, overlap the ROI?",
				tablehead="Intersection type", default="OVERLAPS", 
				widgetFactory='widgetFactory(SimpleSelectChoice, ['
					'"COVERS", "ENCLOSED", "CENTER"], "OVERLAPS")',
				source="INTERSECT"),
		]

	intersectQueries = {
		"COVERS": "bbox_xmin<%(PREFIXxmin)s AND bbox_xmax>%(PREFIXxmax)s"
			" AND bbox_ymin<%(PREFIXymin)s AND bbox_ymax>%(PREFIXymax)s"
			" AND bbox_zmin<%(PREFIXzmin)s AND bbox_zmax>%(PREFIXzmax)s",
		"ENCLOSED": "bbox_xmin>%(PREFIXxmin)s AND bbox_xmax<%(PREFIXxmax)s"
			" AND bbox_ymin>%(PREFIXymin)s AND bbox_ymax<%(PREFIXymax)s"
			" AND bbox_zmin>%(PREFIXzmin)s AND bbox_zmax<%(PREFIXzmax)s",
		"CENTER": "bbox_centerx>%(PREFIXxmin)s AND bbox_centerx<%(PREFIXxmax)s"
			" AND bbox_centery>%(PREFIXymin)s AND bbox_centery<%(PREFIXymax)s"
			" AND bbox_centerz>%(PREFIXzmin)s AND bbox_centerz<%(PREFIXzmax)s",
		"OVERLAPS": "NOT (%(PREFIXxmin)s>bbox_xmax OR %(PREFIXxmax)s<bbox_xmin"
			" OR %(PREFIXymin)s>bbox_ymax OR %(PREFIXymax)s<bbox_ymin"
			" OR %(PREFIXzmin)s>bbox_zmax OR %(PREFIXzmax)s<bbox_zmin)"}

	def _getBboxQuery(self, parameters, prefix="sia"):
		"""returns an SQL fragment for a SIAP query via this interface.

		The SQL is returned as a WHERE-fragment in a string and a dictionary
		to fill the variables required.

		parameters is a dictionary that maps the SIAP keywords to the
		values in the query.  Parameters not defined by SIAP are ignored.
		"""
		cPos = coords.computeUnitSphereCoords(
			*map(float, parameters["POS"].split(",")))
		try:
			sizeAlpha, sizeDelta = [utils.degToRad(float(p)) 
				for p in parameters["SIZE"].split(",")]
		except ValueError:
			size = utils.degToRad(float(parameters["SIZE"]))
			sizeAlpha, sizeDelta = size, size
		intersect = parameters.get("INTERSECT", "OVERLAPS")
		unitAlpha, unitDelta = coords.getTangentialUnits(cPos)
		cornerPoints = [
			cPos-sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
			cPos+sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta,
			cPos-sizeAlpha/2*unitAlpha+sizeDelta/2*unitDelta,
			cPos+sizeAlpha/2*unitAlpha-sizeDelta/2*unitDelta
		]
		xCoos, yCoos, zCoos = [[cp[i] for cp in cornerPoints] 
			for i in range(3)]
		return self.intersectQueries[intersect].replace("PREFIX", prefix), {
			prefix+"xmin": min(xCoos), prefix+"xmax": max(xCoos),
			prefix+"ymin": min(yCoos), prefix+"ymax": max(yCoos),
			prefix+"zmin": min(zCoos), prefix+"zmax": max(zCoos)}

	def run(self, inputTable):
		fragment, pars = self._getBboxQuery(inputTable.getDocRec())
		query = "SELECT * FROM %s.%s WHERE "%(self.rd.get_schema(), 
			self.tableName)+fragment
		return resourcecache.getDbConnection().runQuery(query, pars)

	def parseOutput(self, dbResponse):
		return super(SiapCore, self).parseOutput(dbResponse, 
			self.rd.getTableDefByName("images"))


_coresRegistry = {
	"siap": SiapCore,
}


def getStandardCore(coreName):
	return _coresRegistry[coreName]
