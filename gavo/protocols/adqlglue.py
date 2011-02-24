"""
Code to bind the adql library to the data center software.
"""

import sys

from twisted.python import log

from gavo import adql
from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import stc
from gavo import svcs
from gavo import utils
from gavo.base import sqlsupport
from gavo.base import typesystems


def makeFieldInfo(column):
	"""returns an adql.tree.FieldInfo object from a rscdef.Column.
	"""
	return adql.FieldInfo(column.type,
		column.unit, column.ucd, (column,), stc=column.stc)


class TDContext(object):
	"""An object keeping track of the generation of a table definition
	for ADQL output.
	"""
	def __init__(self):
		self.existingNames = set()
	
	def getName(self, desiredName):
		while desiredName in self.existingNames:
			desiredName = desiredName+"_"
		self.existingNames.add(desiredName)
		return desiredName


# For columns of types that have no automatic VOTable null value,
# we make up some when we don't have any yet.  This is governed by
# the following dictionary (plus, there's special handling for
# bytea in _makeColumnFromFieldInfo: single byteas get promoted to shorts)
#
# This largely follows what Mark Taylor does in topcat.
_artificialNULLs = {
	"bytea": "-32768",
	"smallint": "-32768",
	"integer": "-2147483648",
	"bigint": "-9223372036854775808",
}

def _makeColumnFromFieldInfo(ctx, colName, fi):
	"""constructs a rscdef.Column from a field info pair as left by the
	ADQL machinery.

	The strategy:  If there's only one userData, we copy the Column
	contained in there, update the unit and the ucd, plus a warning
	if the Column has been tainted.

	If there's more or less than one userData, we create a new
	Column, use the data provided by fi and make up a description
	consisting of the source descriptions.	Add a taint warning
	if necessary.

	Since we cannot assign sensible verbLevels and assume the user wants
	to see what s/he selected, all fields get verbLevel 1.

	Types are a serious problem, handled by typesystems.
	"""
	if len(fi.userData)==1:
		res = svcs.OutputField.fromColumn(fi.userData[0])
	else: 
		res = base.makeStruct(svcs.OutputField, name=colName)
	res.name = ctx.getName(colName)
	res.ucd = fi.ucd
	res.unit = fi.unit
	res.type = fi.type

	# XXX TODO: do something with stc's "broken" attribute
	res.stc = fi.stc

	if len(fi.userData)>1:
		res.description = ("This field has traces of: %s"%("; ".join([
			f.description for f in fi.userData if f.description])))

	if fi.tainted:
		res.description = (res.description+" -- *TAINTED*: the value"
			" was operated on in a way that unit and ucd may be severely wrong")

	# The xtype may be set by the node classes; this is used downstream
	# to transform to STC-S strings.
	if "xtype" in fi.properties:
		res.xtype = fi.properties["xtype"]
		res.type = "text"
		res.needMunging = True
	
	# dates and timestamps should be ISO format for TAP or consistency with it
	if res.type=="date" or res.type=="timestamp":
		res.xtype = "adql:TIMESTAMP"
	
	# integral types must have a null value set since we can't be
	# sure that a query yields defined results for all of them.
	if (res.type in _artificialNULLs 
			and (
				not (res.values and res.values.nullLiteral)
				or fi.tainted)):
		if res.type=="bytea":
			res.type = "smallint"
		nullLiteral = _artificialNULLs[res.type]
		if res.values:
			res.values = res.values.change(nullLiteral=nullLiteral)
		else:
			res.values = base.makeStruct(rscdef.Values, 
				nullLiteral=nullLiteral)

	res.verbLevel = 1
	res.finishElement()
	return res


def _getTableDescForOutput(parsedTree):
	"""returns a sequence of Column instances describing the output of the
	parsed and annotated ADQL query parsedTree.
	"""
	ctx = TDContext()
	columns = [_makeColumnFromFieldInfo(ctx, *fi) 
			for fi in parsedTree.fieldInfos.seq]
	# TODO: Fiddle in system metadata if unlucky enough to have STC-S in output
	return base.makeStruct(rscdef.TableDef, columns=columns)


def _getSchema(tableName):
# tableName is a nodes.TableName instance
	return tableName.schema or ""


def _getTupleAdder(table):
	"""returns a function that adds a tuple as returned by the database
	to table.

	This thing is only necessary because of the insanity of having to
	mash metadata into table rows when STC-S strings need to be generated
	for TAP.  Sigh.
	"""
	stcsOutputCols = []
	for colInd, col in enumerate(table.tableDef):
		# needMunging set above.  Sigh.
		if getattr(col, "needMunging", False):
			stcsOutputCols.append((colInd, col))
	if not stcsOutputCols: # Yay!
		return table.addTuple
	else:  # Sigh.  I need to define a function fumbling the mess together.
		parts, lastInd = [], 0
		for index, col in stcsOutputCols:
			if lastInd!=index:
				parts.append("row[%s:%s]"%(lastInd, index))
			parts.append("(row[%s].asSTCS(%r),)"%(index, stc.getTAPSTC(col.stc)))
			lastInd = index+1
		if lastInd!=index:
			parts.append("row[%s:%s]"%(lastInd, len(table.tableDef.columns)))
		return utils.compileFunction(
			"def addTuple(row): table.addTuple(%s)"%("+".join(parts)), 
			"addTuple",
			locals())


def getFieldInfoGetter(accessProfile=None, tdsForUploads=[]):
	mth = base.caches.getMTH(accessProfile)
	tap_uploadSchema = dict((td.id, td) for td in tdsForUploads)
	@utils.memoized
	def getFieldInfos(tableName):
		if _getSchema(tableName).upper()=="TAP_UPLOAD":
			try:
				td = tap_uploadSchema[tableName.name]
			except KeyError:
				raise base.ui.logOldExc(adql.TableNotFound(tableName.qName))
		else:
			td = mth.getTableDefForTable(adql.flatten(tableName))
		return [(f.name, makeFieldInfo(f)) 
			for f in td]
	return getFieldInfos


def morphADQL(query, metaProfile=None, tdsForUploads=[], 
		externalLimit=None, hardLimit=None):
	"""returns an postgres query and an (empty) result table for the
	ADQL in query.
	"""
	t = adql.parseToTree(query)
	if t.setLimit is None:
		if externalLimit is None:
			t.setLimit = str(base.getConfig("adql", "webDefaultLimit"))
		else:
			t.setLimit = str(int(externalLimit))

	adql.annotate(t, getFieldInfoGetter(metaProfile, tdsForUploads))
	q3cstatus, t = adql.insertQ3Calls(t)

	table = rsc.TableForDef(_getTableDescForOutput(t))
	if hardLimit and t.setLimit>hardLimit:
		table.addMeta("_warning", "This service as a hard row limit"
			" of %s.  Your row limit was decreased to this value."%hardLimit)
		t.setLimit = str(hardLimit)

	morphStatus, morphedTree = adql.morphPG(t)
	for warning in q3cstatus.warnings:
		table.addMeta("_warning", warning)
	for warning in morphStatus.warnings:
		table.addMeta("_warning", warning)

	# escape % to hide them form dbapi replacing
	query = adql.flatten(morphedTree).replace("%", "%%")
	table.tableDef.setLimit = t.setLimit and int(t.setLimit)
	return query, table


def query(querier, query, timeout=15, metaProfile=None, tdsForUploads=[],
		externalLimit=None, hardLimit=None):
	"""returns a DataSet for query (a string containing ADQL).

	This will set timeouts and other things for the connection in
	question.  You should have one allocated especially for this query.
	"""
	query, table = morphADQL(query, metaProfile, tdsForUploads, externalLimit,
		hardLimit=hardLimit)
	addTuple = _getTupleAdder(table)
	try:
		querier.setTimeout(timeout)
		# XXX Hack: this is a lousy fix for postgres' seqscan love with
		# limit.  See if we still want this with newer postgres...
		querier.configureConnection([("enable_seqscan", False)])

		for tuple in querier.query(query):
			addTuple(tuple)
	finally:
		querier.rollback()
	if len(table)==int(table.tableDef.setLimit):
		table.addMeta("_overflow", table.setLimit)
	return table


def mapADQLErrors(excType, excValue, excTb):
	if (isinstance(excValue, adql.ParseException)
			or isinstance(excValue, adql.ParseSyntaxException)):
		raise base.ui.logOldExc(
			base.ValidationError("Could not parse your query: %s"%
				unicode(excValue), "query"))
	elif isinstance(excValue, adql.ColumnNotFound):
		raise base.ui.logOldExc(base.ValidationError("No such field known: %s"%
			unicode(excValue), "query"))
	elif isinstance(excValue, adql.AmbiguousColumn):
		raise base.ui.logOldExc(base.ValidationError("%s needs to be qualified."%
			unicode(excValue), "query"))
	else:
		svcs.mapDBErrors(excType, excValue, excTb)


class ADQLCore(svcs.Core, base.RestrictionMixin):
	"""A core taking an ADQL query from its query argument and returning the
	result of that query in a standard table.

	Since the columns returned depend on the query, the outputTable of an
	ADQL core must not be defined.
	"""
	name_ = "adqlCore"

	_querier = None

	def _getQuerier(self):
		return base.SimpleQuerier(useProfile="untrustedquery")

	def wantsTableWidget(self):
		return False

	def run(self, service, inputTable, queryMeta):
		inRow = inputTable.getParamDict()
		queryString = inRow["query"]
		base.ui.notifyInfo("Incoming ADQL query: %s"%queryString)
		try:
			res = query(self._getQuerier(), queryString, 
				timeout=queryMeta["timeout"], hardLimit=100000)
			res.noPostprocess = True
			queryMeta["Matched"] = len(res.rows)
			if len(res.rows)==base.getConfig("adql", "webDefaultLimit"):
				res.addMeta("_warning", "Query result probably incomplete due"
					" to the default match limit kicking in.  Add a TOP clause"
					" to your query to retrieve more data.")
			return res
		except:
			mapADQLErrors(*sys.exc_info())



################ region makers (maybe put these in a separate module later)
# The region maker should in general either call the parser with an ADQL
# fragment (see _makeSimbadRegion) or return a complete FieldInfoedNode
# including any info required with a node type of psqlLiteral (for
# postgres, let's see what happens if we want to support other DBs).
# 
# There are no guarantees that we won't parse out more symbols later,
# and hardcoded trees would break then.

import re

from gavo.adql import nodes

def _getRegionId(regionSpec, pat=re.compile("[A-Za-z_]+")):
	mat = pat.match(regionSpec)
	if mat:
		return mat.group()

# simbadregion needs sesame services, so have them register themselves in
# the cache
from gavo.protocols import simbadinterface

def _makeSimbadRegion(regionSpec):
	if not _getRegionId(regionSpec)=="simbad":
		return
	object = "".join(regionSpec.split()[1:])
	resolver = base.caches.getSesame("web")
	try:
		alpha, delta = resolver.getPositionFor(object)
	except KeyError:
		raise base.ui.logOldExc(
			adql.RegionError("No simbad position for '%s'"%object))
	return adql.getSymbols()["point"].parseString("POINT('ICRS',"
		"%.10f, %.10f)"%(alpha, delta))
adql.registerRegionMaker(_makeSimbadRegion)


################### local query interface #########################

def localquery():
	"""run the argument as an ADQL query.
	"""
	from gavo import formats

	q = sys.argv[1]
	base.setDBProfile("trustedquery")
	querier = base.SimpleQuerier()
	table = query(querier, q, timeout=1000)
	formats.formatData("votable", table, sys.stdout)
