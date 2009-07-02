"""
Code to bind the adql library to the data center software.
"""

import sys

from gavo import adql
from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo.base import sqlsupport
from gavo.base import typesystems


def makeFieldInfo(column):
	"""returns an adql.tree.FieldInfo object from a rscdef.Column.
	"""
	return adql.FieldInfo(
		column.unit, column.ucd, (column,))


def makeColumnFromFieldInfo(colName, fi):
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
	res.ucd = fi.ucd
	res.unit = fi.unit
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
	return [makeColumnFromFieldInfo(*fi) for fi in parsedTree.fieldInfos.seq]


def getFieldInfoGetter(accessProfile=None):
	mth = rsc.MetaTableHandler(accessProfile)
	def getFieldInfos(tableName):
		return [(f.name, makeFieldInfo(f)) 
			for f in mth.getColumnsForTable(tableName)]
	return getFieldInfos


def query(query, timeout=15, queryProfile="untrustedquery", metaProfile=None):
	"""returns a DataSet for query (a string containing ADQL).
	"""
	t = adql.parseToTree(query)
	if t.setLimit is None:
		t.setLimit = str(base.getConfig("adql", "webDefaultLimit"))
	adql.addFieldInfos(t, getFieldInfoGetter(metaProfile))
	adql.insertQ3Calls(t)
# XXX TODO: select an appropriate RD from the tables queried.
	td = base.makeStruct(rscdef.TableDef, columns=_getTableDescForOutput(t))
	table = rsc.TableForDef(td)
	# escape % to hide them form dbapi replacing
	query = adql.flatten(adql.morphPG(t)).replace("%", "%%")
	for tuple in base.SimpleQuerier(useProfile=queryProfile).runIsolatedQuery(
			query, timeout=timeout, silent=True):
		table.addTuple(tuple)
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

	def wantsTableWidget(self):
		return False

	def run(self, service, inputData, queryMeta):
		queryString = inputData.getPrimaryTable().rows[0]["query"]
		try:
			res = query(queryString,
				timeout=base.getConfig("adql", "webTimeout"),
				queryProfile="untrustedquery")
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
