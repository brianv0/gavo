"""
Generation of VODataService 1.1 tablesets from resources, plus 1.0 hacks.
"""

from gavo import base
from gavo import svcs
from gavo.base import typesystems
from gavo.registry import capabilities
from gavo.registry.model import VS1, VS


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
		VS1.targetTable[fk.parent.expand(fk.table)], [
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
	flags = []
	if column.isIndexed():
		flags.append("indexed")
	if column.isPrimary():
		flags.append("primary")
	elif not column.required:
		flags.append("nullable")
	return VS1.column[
		VS1.name[column.name],
		VS1.description[column.description],
		VS1.unit[column.unit],
		VS1.ucd[column.ucd],
		typeElement[column.type],
		[VS1.flag[f] for f in flags]]


def getTableForTableDef(tableDef):
	"""returns a VS1.table instance for a rscdef.TableDef.
	"""
	return VS1.table[
		VS1.name[tableDef.getQName()],
		VS1.title[tableDef.getMeta("title", propagate=False)],
		VS1.title[tableDef.getMeta("description", propagate=False)], [
			getTableColumnFromColumn(col, VS1.voTableDataType)
				for col in tableDef], [
			getForeignKeyForForeignKey(fk)
				for fk in tableDef.foreignKeys]]


def getTablesetForService(service):
	"""returns a VS1.tableset for a dbCore-based service.

	This is for VOSI queries.  It uses the service's getTableset
	method to find out the service's table set.
	"""
	tables = service.getTableSet()
	byRD = {}
	for t in tables:
		byRD.setdefault(t.rd.sourceId, []).append(t)
	if tables:
		return VS1.tableset[[ 
				getSchemaForRD(base.caches.getRD(rdId))[[
					getTableForTableDef(t) for t in tables]]
			for rdId, tables in byRD.iteritems()]]
	else:
		return VS1.tableset[
			VS1.schema[
				VS1.name["default"]]]


def getVS1type(col):
	dt, arrsize = typesystems.sqltypeToVOTable(col.type)
	if arrsize==1:
		arrsize = None
	return VS.dataType(arraysize=arrsize)[dt]


def getVS1_0TablesetForService(service):
	"""returns a sequence of VS.Table elements for tables related to service.

	This is for VODataService 1.0.  Let's hope we can soon kill it.
	"""
	return [
		VS.table[
			VS.name[td.getQName()],
			VS.description[base.getMetaText(td, "description")], [
				VS.column[
					VS.name[col.name],
					VS.description[col.description],
					VS.unit[col.unit],
					VS.ucd[col.ucd],
					getVS1type(col)]
				for col in td]]
		for td in service.getTableSet()]
