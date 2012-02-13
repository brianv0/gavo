"""
Generation of VODataService 1.1 tablesets from resources, plus 1.0 hacks.

Fudge note: sprinkled in below are lots of lower()s for column names and the
like.  These were added for the convenience of TAP clients that may
want to use these names quoted.  Quoted identifiers match regular identifiers
only if case-normalized (i.e., all-lower in DaCHS).
"""

import operator

from gavo import base
from gavo import svcs
from gavo.base import typesystems
from gavo.registry import capabilities
from gavo.registry.model import VS0, VS


def getSchemaForRD(rd):
	"""returns a VS.schema instance for an rd.

	No tables are added.  You need to pick and choose them yourself.
	"""
	return VS.schema[
		VS.name[rd.schema.lower()],
		VS.title[rd.getMeta("title")],
		VS.description[rd.getMeta("description")],
	]


def getForeignKeyForForeignKey(fk):
	"""returns a VS.foreignKey for a rscdef.ForeignKey.
	"""
	return VS.foreignKey[
		VS.targetTable[fk.parent.expand(fk.table).lower()], [
			VS.fkColumn[
				VS.fromColumn[fromColName.lower()],
				VS.targetColumn[toColName.lower()]]
			for fromColName,toColName in zip(fk.source, fk.dest)]]


def getTableColumnFromColumn(column, typeElement):
	"""returns a VS.column instance for an rscdef.Column instance.

	typeElement is a factory for types that has to accept an internal (SQL)
	type as child and generate whatever is necessary from that.
	VS.voTableDataType is an example for such a factory.
	"""
	flags = []
	if column.isIndexed():
		flags.append("indexed")
	if column.isPrimary():
		flags.append("primary")
	elif not column.required:
		flags.append("nullable")
	return VS.column[
		VS.name[column.name.lower()],
		VS.description[column.description],
		VS.unit[column.unit],
		VS.ucd[column.ucd],
		VS.utype[column.utype],
		typeElement[column.type],
		[VS.flag[f] for f in flags]]


def getTableForTableDef(tableDef):
	"""returns a VS.table instance for a rscdef.TableDef.
	"""
	return VS.table[
		VS.name[tableDef.getQName().lower()],
		VS.title[tableDef.getMeta("title", propagate=False)],
		VS.description[tableDef.getMeta("description", propagate=True)],
		VS.utype[tableDef.getMeta("utype")], [
			getTableColumnFromColumn(col, VS.voTableDataType)
				for col in tableDef], [
			getForeignKeyForForeignKey(fk)
				for fk in tableDef.foreignKeys]]


def getTablesetForService(service):
	"""returns a VS.tableset for a dbCore-based service.

	This is for VOSI queries.  It uses the service's getTableset
	method to find out the service's table set.
	"""
	tables = service.getTableSet()
	# it's possible that multiple RDs define the same schema (don't do
	# that, it's going to cause all kinds of pain).  To avoid
	# generating bad tablesets in that case, we have the separate
	# account of schema names; the schema meta is random when
	# more than one RD exists for the schema.
	bySchema, rdForSchema = {}, {}
	for t in tables:
		bySchema.setdefault(t.rd.schema, []).append(t)
		rdForSchema[t.rd.schema] = t.rd
	
	if tables:
		return VS.tableset[[ 
				getSchemaForRD(rdForSchema[schema])[[
					getTableForTableDef(t) 
						for t in sorted(tables, key=operator.attrgetter("id"))]]
			for schema, tables in sorted(bySchema.iteritems())]]
	else:
		return VS.tableset[
			VS.schema[
				VS.name["default"]]]


def getVS1_0type(col):
	"""returns a VODataSet 1.0 type for col.

	This should go away with VS1.0 support.
	"""
	dt, arrsize = typesystems.sqltypeToVOTable(col.type)
	if arrsize==1:
		arrsize = None
	return VS.dataType(arraysize=arrsize)[dt]


def getVS1_0TablesetForService(service):
	"""returns a sequence of VS.Table elements for tables related to service.

	This is for VODataService 1.0.  It's not used any more and should be
	removed as soon as we're sure we can really get away with supporting
	1.1 exclusively.
	"""
	return [
		VS0.table[
			VS0.name[td.getQName()],
			VS0.description[base.getMetaText(td, "description")], [
				VS0.column[
					VS0.name[col.name],
					VS0.description[col.description],
					VS0.unit[col.unit],
					VS0.ucd[col.ucd],
					getVS1_0type(col)]
				for col in td]]
		for td in service.getTableSet()]
