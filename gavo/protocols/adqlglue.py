"""
Code to bind the adql library to the data center software.
"""

import sys

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
	if fi.tainted:
		res.description = (res.description+" -- *TAINTED*: the value"
			" was operated on in a way that unit and ucd may be severely wrong")
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


def getFieldInfoGetter(accessProfile=None):
	mth = rsc.MetaTableHandler(accessProfile)
	@utils.memoized
	def getFieldInfos(tableName):
		return [(f.name, makeFieldInfo(f)) 
			for f in mth.getTableDefForTable(tableName)]
	return getFieldInfos


def query(querier, query, timeout=15, metaProfile=None):
	"""returns a DataSet for query (a string containing ADQL).
	"""
	t = adql.parseToTree(query)
	if t.setLimit is None:
		t.setLimit = str(base.getConfig("adql", "webDefaultLimit"))
	adql.annotate(t, getFieldInfoGetter(metaProfile))
	q3cstatus, t = adql.insertQ3Calls(t)
# XXX FIXME: evaluate q3cstatus for warnings (currently, I think there are none)
	td = _getTableDescForOutput(t)
	table = rsc.TableForDef(td)
	morphStatus, morphedTree = adql.morphPG(t)
	# escape % to hide them form dbapi replacing
	query = adql.flatten(morphedTree).replace("%", "%%")
	for tuple in querier.runIsolatedQuery(
			query, timeout=timeout, silent=True, 
			settings=[("enable_seqscan", False)]):
		table.addTuple(tuple)
	for warning in morphStatus.warnings:
		table.tableDef.addMeta("_warning", warning)
	return table


def mapADQLErrors(excType, excValue, excTb):
	if isinstance(excValue, adql.ParseException):
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


class ADQLCore(svcs.Core):
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
		timeout = base.getConfig("adql", "webTimeout")
		if "timeout" in inRow:
			timeout = inRow["timeout"]
		try:
			res = query(self._getQuerier(), queryString,
				timeout=timeout)
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
	querier = base.SimpleQuerier(useProfile="untrustedquery")
	table = querier.query(q, timeout=1000)
	formats.formatData("votable", table, sys.stdout)

