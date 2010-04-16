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
	only the first table is used.  This has to change.
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


def uploadVOTable(tableId, srcFile, connection, gunzip=False, **moreArgs):
	"""creates a temporary table with tableId containing the first table
	of the first resource in the VOTable that can be read from srcFile.

	The corresponding DBTable instance is returned.

	This function is very inefficient and cannot handle arbitrary
	VOTable names.  Use a TBD alterative.
	"""
	if gunzip:
		inputFile = StringIO(gzip.GzipFile(fileobj=srcFile, mode="r").read())
	else:
		inputFile = StringIO(srcFile.read())
	srcFile.close()
	vot = votable.readRaw(inputFile)
	myArgs = {"onDisk": True, "temporary": True}
	myArgs.update(moreArgs)
	dd = makeDDForVOTable(tableId, vot, **myArgs)
	inputFile.seek(0)
	return rsc.makeData(dd, forceSource=inputFile, connection=connection,
		).getPrimaryTable()
