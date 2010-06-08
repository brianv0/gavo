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


class QuotedNameMaker(object):
	"""A name maker for makeTableDefForVOTable implementing TAP's requirements.
	"""
	def __init__(self):
		self.index, self.seenNames = 0, set()

	def makeName(self, field):
		self.index += 1
		res = getattr(field, "a_name", None)
		if res is None:
			raise base.ValidationError("Field without name in upload.",
				"UPLOAD")
		if res in self.seenNames:
			raise base.ValidationError("Duplicate column name illegal in"
				" uploaded tables (%s)"%res, "UPLOAD")
		self.seenNames.add(res)
		return utils.QuotedName(res)


class AutoQuotedNameMaker(object):
	"""A name maker for makeTableDefForVOTable quoting names as necessary.
	"""
	def __init__(self, forRowmaker=False):
		self.seenNames = set()
	
	def makeName(self, field):
		name = getattr(field, "a_name", None)
		if name is None:
			raise base.ValidationError("Field without name in upload.",
				"UPLOAD")
		if votablegrammar.needsQuoting(name):
			if name in self.seenNames:
				raise base.ValidationError("Duplicate column name illegal in"
					" uploaded tables (%s)"%name, "UPLOAD")
			self.seenNames.add(name)
			return utils.QuotedName(name)
		else:
			if name.lower() in self.seenNames:
				raise base.ValidationError("Duplicate column name illegal in"
					" uploaded tables (%s)"%name, "UPLOAD")
			self.seenNames.add(name.lower())
			return name


def makeTableDefForVOTable(tableId, votTable, nameMaker=None,
		**moreArgs):
	"""returns a TableDef for a Table element parsed from a VOTable.

	Pass additional constructor arguments for the table in moreArgs.
	stcColumns is a dictionary mapping IDs within the source VOTable
	to pairs of stc and utype.

	nameMaker is an optional argument; if given, it must be an object
	having a makeName(field) -> string or utils.QuotedName method.
	It must return unique objects from VOTable fields and to that
	reproducibly, i.e., for a given field the same name is returned.

	The default corresponds to votablegrammar.VOTNameMaker, but
	you can also use InventinQuotedNameMaker, QuotedNameMaker, or
	AutoQuotedNameMaker from this module.
	"""
	if nameMaker is None:
		nameMaker = votablegrammar.VOTNameMaker()

	# make columns
	columns = []
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
