"""
Parsing and translating VOTables to internal data structures.

This is glue code to the more generic votable library.
"""

import gzip
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import stc
from gavo import utils
from gavo import votable
from gavo.grammars import votablegrammar
from gavo.votable import V
from gavo.votable import modelgroups

MS = base.makeStruct


def makeTableDefForVOTable(tableId, votTable, **moreArgs):
	"""returns a TableDef for a Table element parsed from a VOTable.

	Pass additional constructor arguments for the table in moreArgs.
	stcColumns is a dictionary mapping IDs within the source VOTable
	to pairs of stc and utype.
	"""
	# Make columns
	columns = []
	nameMaker = votablegrammar.VOTNameMaker()
	for f in votTable.iterChildrenOfType(V.FIELD):
		colName = nameMaker.makeName(f)
		kwargs = {"name": colName,
			"tablehead": colName.capitalize(),
			"id": getattr(f, "a_ID", None),
			"type": base.voTableToSQLType(f.a_datatype, f.a_arraysize)}
		for attName in ["ucd", "description", "unit", "xtype"]:
			if getattr(f, "a_"+attName, None) is not None:
				kwargs[attName] = getattr(f, "a_"+attName)
		columns.append(MS(rscdef.Column, **kwargs))

	# Create the table definition
	tableDef = MS(rscdef.TableDef, id=tableId, columns=columns,
		**moreArgs)
	tableDef.hackMixinsAfterMakeStruct()

	# Build STC info
	for colInfo, ast in votable.modelgroups.unmarshal_STC(votTable):
		for colId, utype in colInfo.iteritems():
			try:
				col = tableDef.getColumnById(colId)
				col.stcUtype = utype
				col.stc = ast
			except utils.NotFoundError: # ignore broken STC
				pass

	return tableDef


def makeDDForVOTable(tableId, vot, gunzip=False, **moreArgs):
	"""returns a DD suitable for uploadVOTable.

	moreArgs are additional keywords for the construction of the target
	table.

	Only the first resource  will be turned into a DD.  Currently,
	only the first table is used.  This probably has to change.
	"""
	for res in vot.iterChildrenOfType(V.RESOURCE):
		tableDefs = []
		for table in res.iterChildrenOfType(V.TABLE):
			tableDefs.append(
				makeTableDefForVOTable(tableId, table, **moreArgs))
			break
		break
	return MS(rscdef.DataDescriptor,
		grammar=MS(votablegrammar.VOTableGrammar, gunzip=gunzip),
		makes=[MS(rscdef.Make, table=tableDefs[0])])


def uploadVOTable(tableId, srcFile, connection, gunzip=False, **tableArgs):
	"""creates a temporary table with tableId containing the first
	table in the VOTable in srcFile.

	The function returns a DBTable instance for the new file.

	srcFile must be an open file object (or some similar object).
	"""
	if gunzip:
		srcFile = gzip.GzipFile(fileobj=srcFile, mode="r")
	rows = votable.parse(srcFile).next()
	args = {"onDisk": True, "temporary": True}
	args.update(tableArgs)
	td = makeTableDefForVOTable(tableId, rows.tableDefinition, **args)
	table = rsc.TableForDef(td, connection=connection)
	for row in rows:
		table.addTuple(row)
	return table
