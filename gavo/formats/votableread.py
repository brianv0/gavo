"""
Parsing and translating VOTables to internal data structures.

This is glue code to the more generic votable library.  In general, you
should access this module through formats.votable.
"""

import gzip
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import stc
from gavo import utils
from gavo import votable
from gavo.base import valuemappers
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
		res = getattr(field, "name", None)
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
		name = getattr(field, "name", None)
		if name is None:
			raise base.ValidationError("Field without name in upload.",
				"UPLOAD")
		if valuemappers.needsQuoting(name):
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


def addQ3CIndex(tableDef):
	"""if td as unique main positions (by UCD), add an index to the table
	definition.
	"""
	try:
		raField = tableDef.getColumnByUCDs("pos.eq.ra;meta.main", 
			"POS_EQ_RA_MAIN").name
		decField = tableDef.getColumnByUCDs("pos.eq.dec;meta.main", 
			"POS_EQ_RA_MAIN").name
	except ValueError: # No unique positions
		return
	base.resolveId(None, "//scs#q3cindex").applyToFinished(tableDef)


def _getColArgs(votInstance, name):
	"""returns constructor arguments for an RD column or param from
	a VOTable FIELD or PARAM.
	"""
	kwargs = {"name": name,
		"tablehead": name.capitalize(),
		"id": getattr(votInstance, "ID", None),
		"type": base.voTableToSQLType(
			votInstance.datatype, votInstance.arraysize, votInstance.xtype)}
	for attName in ["ucd", "description", "unit", "xtype"]:
		if getattr(votInstance, attName, None) is not None:
			kwargs[attName] = getattr(votInstance, attName)
	if getattr(votInstance, "value", None) is not None:
		kwargs["content_"] = votInstance.value
	return kwargs
	

def makeTableDefForVOTable(tableId, votTable, nameMaker=None, rd=None,
		**moreArgs):
	"""returns a TableDef for a Table element parsed from a VOTable.

	Pass additional constructor arguments for the table in moreArgs.
	stcColumns is a dictionary mapping IDs within the source VOTable
	to pairs of stc and utype.

	nameMaker is an optional argument; if given, it must be an object
	having a makeName(field) -> string or utils.QuotedName method.
	It must return unique objects from VOTable fields and to that
	reproducibly, i.e., for a given field the same name is returned.

	The default is valuemappers.VOTNameMaker, but
	you can also use InventinQuotedNameMaker, QuotedNameMaker, or
	AutoQuotedNameMaker from this module.

	If unique "main" positions are given, a spatial q3c index will be
	added.
	"""
	if nameMaker is None:
		nameMaker = valuemappers.VOTNameMaker()

	# make columns
	columns = []
	for f in votTable.iterChildrenOfType(V.FIELD):
		columns.append(MS(rscdef.Column,
			**_getColArgs(f, nameMaker.makeName(f))))

	# make params
	params = []
	for f in votTable.iterChildrenOfType(V.PARAM):
		try:
			params.append(MS(rscdef.Param, **_getColArgs(f, f.name)))
		except Exception, ex:  # never die because of failing params
			base.ui.notifyError("Unsupported PARAM ignored (%s)"%ex)

	# Create the table definition
	tableDef = MS(rscdef.TableDef, id=tableId, columns=columns,
		params=params, parent_=rd, **moreArgs)
	addQ3CIndex(tableDef)

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


def makeDDForVOTable(tableId, vot, gunzip=False, rd=None, **moreArgs):
	"""returns a DD suitable for uploadVOTable.

	moreArgs are additional keywords for the construction of the target
	table.

	Only the first resource  will be turned into a DD.  Currently,
	only the first table is used.  This probably has to change.
	"""
	tableDefs = []
	for res in vot.iterChildrenOfType(V.RESOURCE):
		for table in res.iterChildrenOfType(V.TABLE):
			tableDefs.append(
				makeTableDefForVOTable(tableId, table, rd=rd, **moreArgs))
			break
		break
	if tableDefs:
		makes = [MS(rscdef.Make, table=tableDefs[0])]
	else:
		makes = []
	return MS(rscdef.DataDescriptor,
		grammar=MS(votablegrammar.VOTableGrammar, gunzip=gunzip),
		makes=makes)


_xtypeParsers = {
	'adql:POINT': "parseSimpleSTCS",
	'adql:REGION': "parseSimpleSTCS", # actually, this is not used since
		                                # there is not column type for these
	'adql:TIMESTAMP': "parseDefaultDatetime",
}


# XXX TODO: quite parallel code in adqlglue: can we abstract a bit?
def _getTupleAdder(table):
	"""returns a function adding a row to table.

	This is necessary for xtype handling (for everything else, the VOTable
	library returns the right types).
	"""
	from gavo.base.literals import parseDefaultDatetime
	from gavo.stc import parseSimpleSTCS

	xtypeCols = []
	for colInd, col in enumerate(table.tableDef):
		if _xtypeParsers.get(col.xtype):
			xtypeCols.append((colInd, col))
	if not xtypeCols:
		return table.addTuple
	else:
		parts, lastInd = [], 0 
		for index, col in xtypeCols:
			if lastInd!=index:
				parts.append("row[%s:%s]"%(lastInd, index))
			parts.append("(%s(row[%s]),)"%(_xtypeParsers[col.xtype], index))
			lastInd = index+1
		if lastInd!=index:
			parts.append("row[%s:%s]"%(lastInd, len(table.tableDef.columns)))
		return utils.compileFunction(
			"def addTuple(row): table.addTuple(%s)"%("+".join(parts)), 
			"addTuple",
			locals())



def uploadVOTable(tableId, srcFile, connection, gunzip=False, 
		rd=None, **tableArgs):
	"""creates a temporary table with tableId containing the first
	table in the VOTable in srcFile.

	The function returns a DBTable instance for the new file.

	srcFile must be an open file object (or some similar object).
	"""
	if gunzip:
		srcFile = gzip.GzipFile(fileobj=srcFile, mode="r")
	try:
		rows = votable.parse(srcFile).next()
	except StopIteration: # no table contained, not our problem
		return
	args = {"onDisk": True, "temporary": True}
	args.update(tableArgs)
	td = makeTableDefForVOTable(tableId, rows.tableDefinition, 
		rd=rd, **args)
	table = rsc.TableForDef(td, connection=connection)
	addTuple = _getTupleAdder(table)
	for row in rows:
		addTuple(tuple(row))
	return table
