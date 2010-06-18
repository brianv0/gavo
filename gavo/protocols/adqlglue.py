"""
Code to bind the adql library to the data center software.
"""

import sys

from twisted.python import log

from gavo import adql
from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.base import sqlsupport
from gavo.base import typesystems


def makeFieldInfo(column):
	"""returns an adql.tree.FieldInfo object from a rscdef.Column.
	"""
	return adql.FieldInfo(
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
		desiredName = fi.userData[0].name
	else: 
		res = base.makeStruct(svcs.OutputField, name=colName)
		desiredName = colName
	res.name = ctx.getName(desiredName)
	res.ucd = fi.ucd
	res.unit = fi.unit

	# XXX TODO: do something with stc's broken attribute
	res.stc = fi.stc

	if len(fi.userData)>1:
		res.description = ("This field has traces of: %s"%("; ".join([
			f.description for f in fi.userData if f.description])))
		res.type = typesystems.getSubsumingType([f.type
			for f in fi.userData])
	# XXX TODO: how can we infer a type when no user data is available at all?

	if fi.tainted:
		res.description = (res.description+" -- *TAINTED*: the value"
			" was operated on in a way that unit and ucd may be severely wrong")

	# The xtype may be set by the node classes; this is used downstream
	# to transform to STC-S strings.
	if "xtype" in fi.properties:
		res.xtype = fi.properties["xtype"]
		res.needMunging = True

	res.verbLevel = 1
	return res


def _getTableDescForOutput(parsedTree):
	"""returns a sequence of Column instances describing the output of the
	parsed and annotated ADQL query parsedTree.
	"""
	ctx = TDContext()
	columns = [_makeColumnFromFieldInfo(ctx, *fi) 
			for fi in parsedTree.fieldInfos.seq]
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
		parts, lastInd = [], -1
		for index, col in stcsOutputCols:
			parts.append("row[%s:%s]"%(lastInd+1, index))
			parts.append("(row[%s].asSTCS(%r),)"%(index, adql.getTAPSTC(col.stc)))
			lastInd = index
		parts.append("row[%s:%s]"%(lastInd, len(table.tableDef.columns)))
		return utils.compileFunction(
			"def addTuple(row): table.addTuple(%s)"%("+".join(parts)), 
			"addTuple",
			locals())


def getFieldInfoGetter(accessProfile=None, tdsForUploads=[]):
	mth = rsc.MetaTableHandler(accessProfile)
	tap_uploadSchema = dict((td.id, td) for td in tdsForUploads)
	@utils.memoized
	def getFieldInfos(tableName):
		if _getSchema(tableName).upper()=="TAP_UPLOAD":
			try:
				td = tap_uploadSchema[tableName.name]
			except KeyError:
				raise adql.TableNotFound(tableName.qName)
		else:
			td = mth.getTableDefForTable(adql.flatten(tableName))
		return [(f.name, makeFieldInfo(f)) 
			for f in td]
	return getFieldInfos


def query(querier, query, timeout=15, metaProfile=None, tdsForUploads=[]):
	"""returns a DataSet for query (a string containing ADQL).

	This will set timeouts and other things for the connection in
	question.  You should have one allocated especially for this query.
	"""
	t = adql.parseToTree(query)
	if t.setLimit is None:
		t.setLimit = str(base.getConfig("adql", "webDefaultLimit"))
	adql.annotate(t, getFieldInfoGetter(metaProfile, tdsForUploads))
	q3cstatus, t = adql.insertQ3Calls(t)
# XXX FIXME: evaluate q3cstatus for warnings (currently, I think there are none)

	td = _getTableDescForOutput(t)
	table = rsc.TableForDef(td)
	# Fiddle in system metadata if unlucky enough to have STC-S in output
	addTuple = _getTupleAdder(table)

	morphStatus, morphedTree = adql.morphPG(t)
	# escape % to hide them form dbapi replacing
	query = adql.flatten(morphedTree).replace("%", "%%")
	querier.setTimeout(timeout)
	querier.configureConnection([("enable_seqscan", False)])

	log.msg("Sending ADQL query: %s"%query)
	for tuple in querier.query(query):
		addTuple(tuple)
	for warning in morphStatus.warnings:
		table.tableDef.addMeta("_warning", warning)
	return table


def mapADQLErrors(excType, excValue, excTb):
	if (isinstance(excValue, adql.ParseException)
			or isinstance(excValue, adql.ParseSyntaxException)):
		raise base.ValidationError("Could not parse your query: %s"%
			unicode(excValue), "query")
	elif isinstance(excValue, adql.ColumnNotFound):
		raise base.ValidationError("No such field known: %s"%
			unicode(excValue), "query")
	elif isinstance(excValue, adql.AmbiguousColumn):
		raise base.ValidationError("%s needs to be qualified."%
			unicode(excValue), "query")
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
		if self._querier is None:
			self._querier = base.SimpleQuerier(useProfile="untrustedquery")
		return self._querier

	def wantsTableWidget(self):
		return False

	def run(self, service, inputData, queryMeta):
		inRow = inputData.getPrimaryTable().rows[0]
		queryString = inRow["query"]
		try:
			res = query(self._getQuerier(), queryString, 
				timeout=queryMeta["timeout"])
			res.noPostprocess = True
			queryMeta["Matched"] = len(res.rows)
			if len(res.rows)==base.getConfig("adql", "webDefaultLimit"):
				res.addMeta("_warning", "Query result probably incomplete due"
					" to the default match limit kicking in.  Add a TOP clause"
					" to your query to retrieve more data.")
			return res
		except:
			mapADQLErrors(*sys.exc_info())


svcs.registerCore(ADQLCore)


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


def _makeSimbadRegion(regionSpec):
	if not _getRegionId(regionSpec)=="simbad":
		return
	object = "".join(regionSpec.split()[1:])
	resolver = base.caches.getSesame("web")
	try:
		alpha, delta = resolver.getPositionFor(object)
	except KeyError:
		raise adql.RegionError("No simbad position for '%s'"%object)
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
