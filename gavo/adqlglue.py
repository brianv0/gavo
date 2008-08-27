"""
Code to bind the adql library to the data center software.
"""

from gavo import adql
from gavo import datadef
from gavo import sqlsupport
from gavo.parsing import resource


def makeFieldInfo(dataField):
	"""returns an adql.tree.FieldInfo object from a dataField.
	"""
	return adql.FieldInfo(
		dataField.get_unit(), dataField.get_ucd(), (dataField,))


def makeDataFieldFromFieldInfo(colName, fi):
	"""constructs a DataField from a field info pair as left by the
	ADQL machinery.

	The strategy:  If there's only one userData, we copy the DataField
	contained in there, update the unit and the ucd, plus a warning
	if the DataField has been tainted.

	If there's more or less than one userData, we create a new
	DataField, use the data provided by fi and make up a description
	consisting of the source descriptions.	Add a taint warning
	if necessary.

	Since we cannot assign sensible verbLevels and assume the user wants
	to see what s/he selected, all fields get verbLevel 1.
	"""
	if len(fi.userData)==1:
		res = fi.userData[0].copy()
	else: 
		res = datadef.DataField(dest=colName)
	res.set_ucd(fi.ucd)
	res.set_unit(fi.unit)
	if len(fi.userData)>1:
		res.set_description("This field has traces of: %s"%("; ".join([
			f.get_description() for f in fi.userData if f.get_description()])))
	if fi.tainted:
		res.set_description(res.get_description()+" -- *TAINTED*: the value"
			" was operated on in a way that unit and ucd may be severely wrong")
	res.set_verbLevel(1)
	return res


def _getTableDescForOutput(parsedTree):
	"""returns a sequence of DataFields describing the output of the
	parsed and annotated ADQL query parsedTree.
	"""
	return [makeDataFieldFromFieldInfo(*fi) for fi in parsedTree.fieldInfos.seq]


def getFieldInfoGetter():
	mth = sqlsupport.MetaTableHandler()
	def getFieldInfos(tableName):
		return [(f.get_dest(), makeFieldInfo(f)) 
			for f in mth.getFieldInfos(tableName)]
	return getFieldInfos


def query(query):
	"""returns a DataSet for query (a string containing ADQL).
	"""
	t = adql.parseToTree(query)
	adql.addFieldInfos(t, getFieldInfoGetter())
	adql.insertQ3Calls(t)
	adql.morphPG(t)
# XXX TODO: select an appropriate RD from the tables queried.
	rd = resource.ResourceDescriptor("inMemory")
	dd = resource.makeRowsetDataDesc(rd, _getTableDescForOutput(t))
	data = sqlsupport.SimpleQuerier().runIsolatedQuery(adql.flatten(t))
	return resource.InternalDataSet(dd, dataSource=data, silent=True)
