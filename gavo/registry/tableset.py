"""
Generation of VODataService 1.1 tablesets from resources.
"""

from gavo import svcs
from gavo.registry import capabilities
from gavo.registry.model import VS1


def getSchemaForRD(rd):
	"""returns a VS1.schema instance for an rd.

	No tables are added.  You need to pick and choose them yourself.
	"""
	return VS1.schema[
		VS1.name[rd.schema],
		VS1.title[rd.getMeta("title")],
		VS1.description[rd.getMeta("description")],
	]


def getForeignKeyForForeignKey(fk):
	"""returns a VS1.foreignKey for a rscdef.ForeignKey.
	"""
	return VS1.foreignKey[
		VS1.targetTable[fk.table], [
			VS1.fkColumn[
				VS1.fromColumn[fromColName],
				VS1.targetColumn[toColName]]
			for fromColName,toColName in zip(fk.source, fk.dest)]]


def getTableColumnFromColumn(column, typeElement):
	"""returns a VS1.column instance for an rscdef.Column instance.

	typeElement is a factory for types that has to accept an internal (SQL)
	type as child and generate whatever is necessary from that.
	VS1.dataType children should be able to do that.
	"""
	return VS1.column[
		VS1.name[column.name],
		VS1.description[column.description],
		VS1.unit[column.unit],
		VS1.ucd[column.ucd],
		typeElement[column.type]]


def getTableForTableDef(tableDef):
	"""returns a VS1.table instance for a rscdef.TableDef.
	"""
	return VS1.table[
		VS1.name["%s.%s"%(tableDef.rd.schema, tableDef.id)],
		VS1.title[tableDef.getMeta("title", propagate=False)],
		VS1.title[tableDef.getMeta("description", propagate=False)], [
			getTableColumnFromColumn(col, VS1.voTableDataType)
				for col in tableDef], [
			getForeignKeyForForeignKey(fk)
				for fk in tableDef.foreignKeys]]


def getTablesetForService(service):
	"""returns a VS1.tableset for a service.

	This is for VOSI queries.  It uses the service's getTableset
	method to find out the service's table set.
	"""
	return VS1.tableset[
		getSchemaForRD(service.rd)[[
			getTableForTableDef(t) for t in service.getTableSet()]]]
