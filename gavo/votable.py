"""
Functions for parsing and generating VOTables to and from data and metadata.

This module also serves as an interface to VOTable.DataModel in that
it imports all names from there.  Thus, you can get DataModel.Table as
votable.Table.

The module provides the glue between the row lists and the DataField
based description from the core modules and pyvotable.  

An important task is the mapping of values.  To do this, we define mapper
factories.  These are functions receiving instances of ColProperties that
they can query of properties of the target field.  

They then return either None (meaning they don't know how to do the conversion)
or a callable that does the conversion.  They may change the description of the
target field, e.g., to fix types (see datetime) or to add nullvalues (see
ints).

The first factory providing such a callable wins.  The factories register
with a ValueEncoderFactoryRegistry object that's used by getCoder.
"""

import sys
import re
import itertools
import urllib
import urlparse

from gavo import ElementTree
from gavo import typesystems
from gavo import config

from gavo.imp.VOTable import Writer
from gavo.imp.VOTable.DataModel import *
from gavo.imp.VOTable import Encoders
from gavo.imp.VOTable.Writer import namespace
from gavo.parsing import meta


class Error(Exception):
	pass


namespace = "http://www.ivoa.net/xml/VOTable/v1.1"

errorTemplate = """<?xml version="1.0" encoding="utf-8"?>
<VOTABLE version="1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
	xsi:noNamespaceSchemaLocation="xmlns=http://www.ivoa.net/xml/VOTable/v1.1">
	<RESOURCE>
		<INFO>%(errmsg)s</INFO>
	</RESOURCE>
</VOTABLE>"""


def voTag(tag):
	return "{%s}%s"%(namespace, tag)


_tableEncoders = {
	"td": Encoders.TableDataEncoder,
	"binary": Encoders.BinaryEncoder,
}

class ValueMapperFactoryRegistry(object):
	"""is an object clients can ask for functions fixing up values
	for encoding.

	A mapper factory is just a function that takes a "representative"
	instance and the column properties It must return either None
	(for "I don't know how to make a function for this combination
	of value and column properties") or a callable that takes a
	value of the given type and returns a mapped value.

	To add a mapper, call registerFactory.  To find a mapper for a
	set of column properties, call getMapper -- column properties should
	be an instance of ColProperties, but for now a dictionary with the
	right keys should mostly do.

	Mappers have both the sql type (in the sqltype entry) and the votable type
	(in the datatype and arraysize entries) to base their decision on.

	Coder factories are tried in the reverse order of registration,
	and the first that returns non-None wins, i.e., you should
	register coder factories first.  If no registred mapper declares
	itself responsible, getMapper returns an identity function.  If
	you want to catch such a situation, you can use somthing like
	res = vmfr.getMapper(...); if res is vmfr.identity ...
	"""
	def __init__(self, factories=None):
		if factories==None:
			self.factories = []
		else:
			self.factories = factories[:]

	def getFactories(self):
		"""returns the list of factories.

		This is *not* a copy.  It may be manipulated to remove or add
		factories.
		"""
		return self.factories

	def registerFactory(self, factory):
		self.factories.insert(0, factory)

	def identity(self, val):
		return val

	def getMapper(self, colProps):
		"""returns a mapper for values with the python value instance, 
		according to colProps.

		This method may change colProps (which is the usual dictionary
		mapping column property names to their values).

		We do a linear search here, so you shouldn't call this function too
		frequently.
		"""
		for factory in self.factories:
			mapper = factory(colProps)
			if mapper:
				break
		else:
			mapper = self.identity
		return mapper


_defaultMFRegistry = ValueMapperFactoryRegistry()
_registerDefaultMF = _defaultMFRegistry.registerFactory


try:
	from mx import DateTime

	def mxDatetimeMapperFactory(colProps):
		"""returns mapper for mxDateTime objects.

		Unit may be yr or a (produces julian fractional years like J2000.34),
		d (produces julian days), s (produces a unix timestamp, for whatever
		that's good), "Y:M:D" or "Y-M-D" (produces an iso date).
		"""
		unit = colProps["unit"]
		if isinstance(colProps["sample"], DateTime.DateTimeType):
			if unit=="yr" or unit=="a":
				fun, destType = lambda val: val and val.jdn/365.25-4712, ("double", 
					None)
			elif unit=="d":
				fun, destType = lambda val: val and val.jdn, ("double", None)
			elif unit=="s":
				fun, destType = lambda val: val and val.ticks(), ("double", None)
			elif unit=="Y:M:D" or unit=="Y-M-D":
				fun, destType = lambda val: val and val.date, ("char", "*")
			else:   # Fishy, but not our fault
				fun, destType = lambda val: val and val.jdn, ("double", None)
			colProps["datatype"], colProps["arraysize"] = destType
			return fun
	_registerDefaultMF(mxDatetimeMapperFactory)

except ImportError:
	pass

import datetime

def datetimeMapperFactory(colProps):
	import time

	def dtToJdn(val):
		# XXX TODO: add fractional days from time
		"""returns a julian day number for the dateTime instance val.
		"""
		a = (14-val.month)//12
		y = val.year+4800-a
		m = val.month+12*a-3
		return val.day+(153*m)//5+365*y+y//4-y//100+y//400-32045

	def dtToMJdn(val):
		"""returns the modified julian date number for the dateTime instance val.
		"""
		return dtToJdn(val)-2400000.5

	if isinstance(colProps["sample"], datetime.date):
		unit = colProps["unit"]
		if "MJD" in colProps.get("ucd", ""):  # like VOX:Image_MJDateObs
			colProps["unit"] = "d"
			fun, destType = lambda val: val and dtToMJdn(val), ("double", None)
		elif unit=="yr" or unit=="a":
			fun, destType = lambda val: val and dtToJdn(val)/365.25-4712, ("double",
				None)
		elif unit=="d":
			fun, destType = lambda val: val and val.jdn, ("double", None)
		elif unit=="s":
			fun, destType = lambda val: val and time.mktime(val.timetuple()), (
				"double", None)
		elif unit=="Y:M:D":
			fun, destType = lambda val: val and val.isoformat(), ("char", "*")
		else:   # Fishy, but not our fault
			fun, destType = lambda val: val and dtToJdn(val), ("double", "*")
		colProps["datatype"], colProps["arraysize"] = destType
		return fun
_registerDefaultMF(datetimeMapperFactory)


def _booleanMapperFactory(colProps):
	if colProps["dbtype"]=="boolean":
		def coder(val):
			if val:
				return "1"
			else:
				return "0"
		return coder
_registerDefaultMF(_booleanMapperFactory)


def _floatMapperFactory(colProps):
	if colProps["dbtype"]=="real" or colProps["dbtype"].startswith("double"):
		naN = float("NaN")
		def coder(val):
			if val==None:
				return naN
			return val
		return coder
_registerDefaultMF(_floatMapperFactory)


def _stringMapperFactory(colProps):
	if colProps.get("optional", True) and ("char(" in colProps["dbtype"] or 
			colProps["dbtype"]=="text"):
		def coder(val):
			if val==None:
				return ""
			return val
		return coder
_registerDefaultMF(_stringMapperFactory)

# Default nullvalues we use when we don't know anything about the ranges,
# by VOTable types.  The nullvalues should never be used, but the keys
# are used to recognize types with special nullvalue handling.
_defaultNullvalues = {
	"unsignedByte": 255,
	"char": '~',
	"short": -9999,
	"int": -999999999,
	"long": -9999999999,
}

def _intMapperFactory(colProps):
	if colProps["datatype"] in _defaultNullvalues:
		if not colProps.get("hasNulls"):
			return
		try:
			colProps.computeNullvalue()
		except AttributeError:
			colProps["nullvalue"] = _defaultNullvalues[colProps["datatype"]]
		def coder(val, nullvalue=colProps["nullvalue"]):
			if val==None:
				return nullvalue
			return val
		return coder
_registerDefaultMF(_intMapperFactory)


def _productMapperFactory(colProps):
	"""is a factory for columns containing product keys.

	The result are links to the product delivery.
	"""
	from nevow import url
	if colProps["ucd"]=="VOX:Image_AccessReference":
		def mapper(val):
			if val==None:
				return ""
			else:
				return urlparse.urljoin(
					urlparse.urljoin(config.get("web", "serverURL"),
						config.get("web", "nevowRoot")),
					"getproduct?key=%s&siap=true"%urllib.quote(val))
		return mapper
_registerDefaultMF(_productMapperFactory)


def getMapperRegistry():
	"""returns a copy of the default value mapper registry.
	"""
	return ValueMapperFactoryRegistry(
		_defaultMFRegistry.getFactories())


############# everything from here till XXX is deprecated

def _getValSeq(data):
	"""returns a sequence of python values for the columns of data.

	The function inspects as many rows as are necessary to have a row
	of all non-null values, so it may run for quite a while if you have
	at least one row with lots of NULLs.

	>>> _getValSeq([[1,None,None,None], [None,1,None,None], [2,2,"a",None]])
	[1, 1, 'a', None]
	"""
	if not data:
		return []
	vals = [None]*len(data[0])
	nullColumns = set(range(len(data[0])))
	for row in data:
		newColumns = set()
		for col in nullColumns:
			if row[col]!=None:
				vals[col] = row[col]
				newColumns.add(col)
		nullColumns -= newColumns
		if not nullColumns:
			break
	return vals


def _mapValues(colDesc, data, mapperFactory):
	"""fixes the values of data to match what is required by colDesc.

	As a side effect, the types given in colDesc may change.
	"""
	colTypes = _getValSeq(data)
	handlers = []
	for colType, colProps in zip(colTypes, colDesc):
		colProps["sample"] = colType
		handler = mapperFactory.getMapper(colProps)
		handlers.append(handler)
	if data:
		colInds = range(len(data[0]))
		for rowInd, row in enumerate(data):
			data[rowInd] = [handlers[colInd](row[colInd]) for colInd in colInds]
	

def writeTable(resources, metaInfo, destination):
	"""writes a VOTable for all DataModel.Resource instances in resource to
	destination.

	destination may be a file or a file name.

	metaInfo is currently ignored.
	"""
	table = VOTable()
	table.resources = resources
	writer = Writer()
	writer.write(table, destination)


def _mapTypes(colDesc):
	for colProps in colDesc:
		type, size = typesystems.sqltypeToVOTable(colProps["dbtype"])
		colProps["datatype"], colProps["arraysize"] = type, size


def _getFieldItemsFor(colInd, colProps):
	"""returns a dictionary with keys for a DataModel.Field constructor.

	For compatibility with newer code, this changes colProps.  Pain.
	"""
	fieldItems = {
		"name": colProps["fieldName"],
		"ID": "%03d-%s"%(colInd, colProps["fieldName"]),
	}
	for fieldName in ["ucd", "utype", "unit", "width", "precision", "datatype",
			"arraysize"]:
		if colProps.get(fieldName)!=None:
			fieldItems[fieldName] = colProps[fieldName]
	return fieldItems


def _defineFields(colDesc, dataTable):
	"""adds the field descriptions from colDesc dicts to the DataModel.Table
	instance dataTable.
	"""
	for colInd, colProps in enumerate(colDesc):
		dataTable.fields.append(
			Field(**_getFieldItemsFor(colInd, colProps)))


def buildTableColdesc(colDesc, data, metaInfo, tablecoding="binary", 
		mapperFactoryRegistry=_defaultMFRegistry):
	"""returns a DataModel.Table instance for data.

	This function can only handle 2d tables.

	target is either a file or a name, data is a sequence of
	sequence containing the data described by colDesc, with data values
	in the sequence defined by colDesc.

	metaInfo is a dictionary containing metadata; keys we currently support:
	* name
	* description
	* id
	Unknown keys are silently ignored.
	"""
	try:
		votEncoder = _tableEncoders[tablecoding]
	except KeyError:
		raise Error("Invalid table coding: %s"%tablecoding)
	dataTable = Table(name=metaInfo.get("name", "data"),
		description=metaInfo.get("description", ""), coder=votEncoder)
	if metaInfo.has_key("id"):
		dataTable.id = id
	_mapTypes(colDesc)
	_mapValues(colDesc, data, mapperFactoryRegistry)
	_defineFields(colDesc, dataTable)
	dataTable.data = data
	return dataTable


def writeSimpleTableColdesc(colDesc, data, metaInfo, destination, 
		tablecoding="binary",
		mapperFactoryRegistry=_defaultMFRegistry):
	"""writes a single-table, single-resource VOTable to destination.

	Arguments:

	* colDesc -- a sequence of dictionaries defining the fields, as
	  given by sqlsupport.metaTableHandler
	* data -- a sequence of sequences giving the rows to be formatted
	* metaInfo -- a dictionary containing meta information (more info coming up)
	* destination -- a file-like object to write the XML to
	"""
	try:
		writeTable([Resource(tables=[
				buildTableColdesc(colDesc, data, metaInfo, tablecoding, 
					mapperFactoryRegistry)])],
			{}, destination)
	except Exception, msg:
		import traceback
		traceback.print_exc()
		destination.write(errorTemplate%{
			"errmsg": "The creation of this resource failed.  The reason given"
				" by the program is: %s (%s).  You should report this failure"
				" to the operator of this site, %s"%(
					msg.__class__.__name__,
					str(msg),
					config.get("operator"))})


def writeVOTableFromTable(dataSet, table, destination, 
		tablecoding="binary", mapperFactoryRegistry=_defaultMFRegistry):
	"""returns a DataModel.Table constructed from a table.Table.
	"""
	colDesc = [df.getMetaRow() for df in table.getFieldDefs()]
	metaInfo = {
		"id": table.getName(),
		"name": "%s.%s"%(dataSet.getId(), table.getName()),
		"description": table.getRecordDef().getMeta("description"),
	}
	writeSimpleTableColdesc(colDesc, table.getRowsAsTuples(), metaInfo, 
		destination, tablecoding, mapperFactoryRegistry)


################# XXXXX end of deprecated section


class _CmpType(type):
	"""is a metaclass for *classes* that always compare in one way.
	"""
# Ok, that's just posing.  It's fun anyway.
	def __cmp__(cls, other):
		return cls.cmpRes

class _Comparer(object):
	__metaclass__ = _CmpType
	def __init__(self, *args, **kwargs):
		raise Error("%s classes can't be instanciated."%self.__class__.__name__)

class _Infimum(_Comparer):
	"""is a *class* smaller than anything.

	This will only work as the first operand.

	>>> _Infimum<-2333
	True
	>>> _Infimum<""
	True
	>>> _Infimum<None
	True
	>>> _Infimum<_Infimum
	True
	"""
	cmpRes = -1


class _Supremum(_Comparer):
	"""is a *class* larger than anything.

	This will only work as the first operand.

	>>> _Supremum>1e300
	True
	>>> _Supremum>""
	True
	>>> _Supremum>None
	True
	>>> _Supremum>_Supremum
	True
	"""
	cmpRes = 1


class ColProperties(dict):
	"""is a container for properties of columns in a table.

	Specifically, it gives maxima, minima and if null values occur.
	"""
	_nullvalueRanges = {
		"char": (' ', '~'),
		"unsignedByte": (0, 255),
		"short": (-2**15, 2**15-1),
		"int": (-2**31, 2**31-1),
		"long": (-2**63, 2**63-1),
	}
	def __init__(self, fieldDef):
		self["min"], self["max"] = _Supremum, _Infimum
		self["hasNulls"] = True # Safe default
		self.nullSeen = False
		self["sample"] = None
		self["name"] = fieldDef.get_dest()
		self["dbtype"] = fieldDef.get_dbtype()
		self["description"] = fieldDef.get_description()
		self["ID"] = fieldDef.get_dest()  # XXX TODO: qualify this guy
		type, size = typesystems.sqltypeToVOTable(fieldDef.get_dbtype())
		self["datatype"] = type
		self["arraysize"] = size
		self["displayHint"] = fieldDef.get_displayHint()
		for fieldName in ["ucd", "utype", "unit", "description"]:
			self[fieldName] = fieldDef.get(fieldName)

	def feed(self, val):
		if val is None:
			self.nullSeen = True
		else:
			if self["min"]>val:
				self["min"] = val
			if self["max"]<val:
				self["max"] = val

	def finish(self):
		"""has to be called after feeding is done.
		"""
		self.computeNullvalue()
		self["hasNulls"] = self.nullSeen

	def computeNullvalue(self):
		"""tries to come up with a null value for integral data.

		This is called by finish(), but you could call it yourself to find out
		if a nullvalue can be computed.
		"""
		if self["datatype"] not in self._nullvalueRanges:
			return
		if self["min"]>self._nullvalueRanges[self["datatype"]][0]:
			self["nullvalue"] = self._nullvalueRanges[self["datatype"]][0]
		elif self["max"]<self._nullvalueRanges[self["datatype"]][1]:
			self["nullvalue"] = self._nullvalueRanges[self["datatype"]][1]
		else:
			raise Error("Cannot compute nullvalue for column %s,"
				"range is %s..%s"%(self["name"], self["min"], self["max"]))

	def _addValuesKey(self, fieldArgs):
		"""adds a VOTable VALUES node to fieldArgs when interesting.
		"""
		valArgs = {}
		if self["min"] is not _Supremum:
			valArgs["min"] = Min(value=str(self["min"]))
		if self["max"] is not _Infimum:
			valArgs["max"] = Max(value=str(self["max"]))
		if self["hasNulls"]:
			if self.has_key("nullvalue"):
				valArgs["null"] = str(self["nullvalue"])
		if valArgs:
			valArgs["type"] = "actual"
			vals = Values(**valArgs)
			# hasNulls could help the encoder optimize if necessary.
			# Since VOTable.VOObject doesn't serialize booleans, this won't show
			# in the final XML.
			vals.hasNulls = self.nullSeen
			fieldArgs["values"] = vals

	_voFieldCopyKeys = ["name", "ID", "datatype", "ucd",
		"utype", "unit", "description"]

	def getVOFieldArgs(self):
		"""returns a dictionary suitable for construction a VOTable field
		that defines the instance's column.
		"""
		res = {}
		for key in self._voFieldCopyKeys:
			res[key] = self[key]
		if self["arraysize"]!="1":
			res["arraysize"] = self["arraysize"]
		if self.has_key("value"):  # for PARAMs
			res["value"] = str(self["value"])   # XXX TODO: use value mappers
		self._addValuesKey(res)
		return res


class TableData:
	"""is a tabular data for VOTables.

	It is constructed from a table.Table instance and
	a MapperFactoryRegistry.  It will do two sweeps through
	the complete data, first to establish value ranges including
	finding out if there's NULL values.  Then, it does another sweep
	converting the sequence of dicts to a sequence of properly typed
	and formatted tuples.
	"""
	def __init__(self, table, mFRegistry=_defaultMFRegistry):
		self.table = table
		self.mFRegistry = mFRegistry
		self.fieldNames = tuple(field.get_dest()
			for field in self.table.getFieldDefs())
		self.colProperties = self._computeColProperties()
		self.mappers = tuple(self.mFRegistry.getMapper(
				self.colProperties[fieldName])
			for fieldName in self.fieldNames)

	# Don't compute min, max, etc for these types
	_noValuesTypes = set(["boolean", "bit", "unicodeChar",
		"floatComplex", "doubleComplex"])

	def _computeColProperties(self):
		"""inspects self.table to find out types and ranges of the data
		living in it.

		The method returns a sequence of ColProperty instances containing
		all information necessary to set up VOTable Field definitions.
		"""
		colProps = {}
		for field in self.table.getFieldDefs():
			colProps[field.get_dest()] = ColProperties(field)
		valDesiredCols = [colProp["name"] for colProp in colProps.values()
			if colProp["datatype"] not in self._noValuesTypes and
				colProp["arraysize"]=="1"]
		noSampleCols = set(colProps)
		for row in self.table:
			for key in valDesiredCols:
				colProps[key].feed(row[key])
			if noSampleCols:
				newSampleCols = set()
				for key in noSampleCols:
					if row[key]!=None:
						colProps[key]["sample"] = row[key]
						newSampleCols.add(key)
				noSampleCols.difference_update(newSampleCols)
		for colProp in colProps.values():
			colProp.finish()
		return colProps

	def getColProperties(self):
		"""returns a sequence of ColProperties instances in the order of the
		VOTable row.
		"""
		return [self.colProperties[name] for name in self.fieldNames]

	def get(self):
		colIndices = range(len(self.fieldNames))
		def row2Tuple(row):
			return tuple(self.mappers[i](
				row[self.fieldNames[i]]) for i in colIndices)
		return [row2Tuple(row) for row in self.table]


def acquireSamples(colPropsIndex, table):
	"""fills the values in the colProps-valued dict colPropsIndex with non-null
	values from tables.
	"""
# this is a q'n'd version of what's done in TableData._computeColProperties
# -- that method should be refactored anyway.  You can then fold in this
# function.
	noSampleCols = set(colPropsIndex)
	for row in table:
		newSampleCols = set()
		for col in noSampleCols:
			if row[col]!=None:
				newSampleCols.add(col)
				colPropsIndex[col]["sample"] = row[col]
		noSampleCols.difference_update(newSampleCols)
		if not noSampleCols:
			break


class VOTableMaker:
	"""is a facade wrapping the process of writing a VOTable.

	Its main method is makeVOT turning a DataSet into a VOTable.

	You should usually use this to produce VOTables -- the other
	functions in the module are just q'n'd hacks.
	"""
	def __init__(self, tablecoding="binary",
			mapperFactoryRegistry=_defaultMFRegistry):
		self.tablecoding = tablecoding
		self.mFRegistry = mapperFactoryRegistry

	def _addInfo(self, name, content, node, value="", id=None):
		"""adds info item "name" containing content having value to node
		unless both content and value are empty.
		"""
		if isinstance(content, meta.MetaItem) and isinstance(content.content,
				meta.InfoItem):
			content, value = content.content.content, content.content.value
		if content or value:
			i = Info(name=name, text=content)
			i.value = value
			if id:
				i.ID = id
			node.info.append(i)

	def _addLink(self, href, node, contentRole=None, title=None,
			value=None):
		"""adds a link item with href to node.

		Apart from title, the further arguments are ignored right now.
		"""
		if href:
			l = Link(href=href, title=title)
			node.links.append(l)

	def _defineFields(self, tableNode, colProperties):
		"""defines the fields in colProperties within the VOTable tableNode.

		colProperties is a sequence of colProperties instances.
		"""
		for colProp in colProperties:
			tableNode.fields.append(
				Field(**colProp.getVOFieldArgs()))

	def _defineParams(self, resourceNode, items, values):
		for item in items:
			cp = ColProperties(item)
			if values.has_key(item.get_dest()):
				cp["value"] = values[item.get_dest()]
			resourceNode.params.append(Param(**cp.getVOFieldArgs()))
				
	def _makeTable(self, res, table):
		"""returns a Table node for the table.Table instance table.
		"""
		t = Table(name=table.getName(), coder=_tableEncoders[self.tablecoding],
			description=table.getMeta("description", propagate=False))
		data = TableData(table, self.mFRegistry)
		self._defineFields(t, data.getColProperties())
		t.data = data.get()
		return t
	
	def _addResourceMeta(self, res, dataSet):
		"""adds resource metadata to the Resource res.
		"""
		res.description = dataSet.getMeta("description", propagate=False)
		foo = dataSet.getMeta("_legal") 
		self._addInfo("legal", dataSet.getMeta("_legal"), res)
		self._addInfo("QUERY_STATUS", dataSet.getMeta("_query_status"), res)
		self._addInfo("Error", dataSet.getMeta("_error"), res, id="Error")
		self._addLink(dataSet.getMeta("_infolink"), res)

	def _makeResource(self, dataSet):
		"""returns a Resource node for dataSet.
		"""
		res = Resource()
		self._defineParams(res, dataSet.getDocFields(), dataSet.getDocRec())
		self._addResourceMeta(res, dataSet)
		for table in dataSet.getTables():
			if table.getFieldDefs():
				res.tables.append(self._makeTable(res, table))
		return res

	def _setGlobalMeta(self, vot, dataSet):
		"""add meta elements from the resource descriptor to vot.
		"""
		rd = dataSet.getDescriptor().getRD()
		vot.description = rd.getMeta("description")
		for id, equ, epoch, system in rd.get_systems():
			vot.coosys.append(CooSys(ID=id, equinox=equ, epoch=epoch, system=system))
		self._addInfo("legal", rd.getMeta("_legal"), vot)

	def makeVOT(self, dataSet):
		"""returns a VOTable object representing dataSet.
		"""
		vot = VOTable()
		self._setGlobalMeta(vot, dataSet)
		vot.resources.append(self._makeResource(dataSet))
		return vot

	def writeVOT(self, vot, destination, encoding="utf-8"):
		writer = Writer(encoding)
		writer.write(vot, destination)


def _test():
	import doctest, votable
	doctest.testmod(votable)


def _profilerun():
	from gavo import sqlsupport, config
	config.setDbProfile("querulator")

	def getFieldInfos(querier, tableName):
		metaTable = sqlsupport.MetaTableHandler(querier)
		return metaTable.getFieldInfos(tableName)

	querier = sqlsupport.SimpleQuerier()
	result = querier.query(
		"SELECT * from ppmx.autocorr").fetchall()
	print result[0]
	writeSimpleTableColDesc(getFieldInfos(querier, "ppmx.autocorr"),
		result, {}, open("/dev/null", "w"))


if __name__=="__main__":
	_test()
	#_profilerun()
