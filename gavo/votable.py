"""
Functions for parsing and generating VOTables to and from data and metadata.

This module also serves as a q'n'd interface to VOTable.DataModel in that
it imports all names from there.  Thus, you can get DataModel.Table as
votable.Table.
"""

import sys
import re
import itertools
try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree

from VOTable import Writer
from VOTable.DataModel import *


class Error(Exception):
	pass

class ValueEncoderFactoryRegistry(object):
	"""is a container for functions encoding single values to text.

	To register a coder factory, call addCoderFactory.  A coder
	factory usually is just a function that takes a type object,
	a unit and a ucd.  It should return either None (for "I don't
	know how to make a function for this combination of type, unit
	and ucd") or a callable that takes a value of the given type
	and returns a string serializing the value.

	Coder factories are tried in the reverse order of registration,
	and the first that returns non-None wins, i.e., you should
	register more general coder factories first.
	"""
	def __init__(self):
		self.factories = []
	
	def addCoderFactory(self, factory):
		self.factories.insert(0, factory)
	
	def getCoder(self, type, destType, unit, ucd):
		"""returns a coder for values with the python data type type, given in
		unit and with ucd.

		We do a linear search here, so you shouldn't call this function too
		frequently.
		"""
		for factory in self.factories:
			handler = factory(type, destType, unit, ucd)
			if handler:
				break
		else:
			handler = str
		return handler


_coderRegistry = ValueEncoderFactoryRegistry()

registerCoderFactory = _coderRegistry.addCoderFactory
getCoder = _coderRegistry.getCoder


def _catchallFactory(srcType, destType, unit, ucd):
	return str, destType
registerCoderFactory(_catchallFactory)

try:
	from mx import DateTime

	def _datetimeCoderFactory(srcType, destType, unit, ucd):
		"""returns coders for mxDateTime objects.

		Unit may be yr or a (produces julian fractional years like J2000.34),
		d (produces julian days), s (produces a unix timestamp, for whatever
		that's good), "Y:M:D" (produces an iso date).
		"""
		if isinstance(srcType, DateTime.DateTimeType):
			fun = None
			if unit=="yr" or unit=="a":
				fun, destType = lambda val: val and val.jdn/365.25-4712, "double"
			elif unit=="d":
				fun, destType = lambda val: val and val.jdn, "double"
			elif unit=="s":
				fun, destType = lambda val: val and val.ticks(), "double"
			elif unit=="Y:M:D":
				fun, destType = lambda val: val and val.date, "text"
			else:   # Fishy, but not our fault
				fun, destType = lambda val: val and val.jdn, "double"
			return fun, destType
	
	registerCoderFactory(_datetimeCoderFactory)
except ImportError:
	pass


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


def _getVoTypeForSqlType(dbtype, simpleMap={
		"smallint": ("short", "1"),
		"integer": ("int", "1"),
		"int": ("int", "1"),
		"bigint": ("long", "1"),
		"real": ("float", "1"),
		"float": ("float", "1"),
		"boolean": ("boolean", "1"),
		"double precision": ("double", "1"),
		"double": ("double", "1"),
		"text": ("char", "*"),
		"char": ("char", "1"),
		"date": ("char", "*"),
		"timestamp": ("char", "*"),
	}):
	"""returns a VOTable type and a length for an SQL type description.
	"""
	if dbtype in simpleMap:
		return simpleMap[dbtype]
	else:
		mat = re.match(r"(.*)\((\d+)\)", dbtype)
		if mat:
			if mat.group(1) in ["character varying", "varchar", "character",
					"char"]:
				return "char", mat.group(2)
		raise Error("No VOTable type for %s"%dbtype)


def _getFieldItemsFor(colInd, colOpts):
	"""returns a dictionary with keys for a DataModel.Field constructor.
	"""
	fieldItems = {
		"name": colOpts["fieldName"],
		"ID": "col%02d"%colInd,
	}
	type, size = _getVoTypeForSqlType(colOpts["type"])
	fieldItems["datatype"] = type
	if size!="1":
		fieldItems["arraysize"] = size
	for fieldName in ["ucd", "utype", "unit", "width", "precision"]:
		if colOpts.get(fieldName)!=None:
			fieldItems[fieldName] = colOpts[fieldName]
	return fieldItems


def _defineFields(colDesc, dataTable):
	"""adds the field descriptions from colDesc dicts to the DataModel.Table
	instance dataTable.
	"""
	for colInd, colOpts in enumerate(colDesc):
		dataTable.fields.append(
			Field(**_getFieldItemsFor(colInd, colOpts)))


def _mapValues(colDesc, data):
	"""fixes the values of data to match what is required by colDesc.

	As a side effect, the types given in colDesc may change.
	"""
	colTypes = _getValSeq(data)
	handlers = []
	for colType, colOpts in zip(colTypes, colDesc):
		handler, newType = getCoder(colType, colOpts["type"], colOpts["unit"],
			colOpts["ucd"])
		colOpts["type"] = newType
		handlers.append(handler)
	if data:
		rowIndices = range(len(data[0]))
		for row in data:
			for ind in rowIndices:
				row[ind] = handlers[ind](row[ind])
	

def buildTable(colDesc, data, metaInfo):
	"""returns a DataModel.Table instance for data.

	This function can only handle 2d tables.

	target is either a file or a name,  colDesc is a list of triples
	(name, type, optDict) like in sqlsupport, data is a sequence of
	sequence containing the data described by colDesc, with data values
	in the sequence defined by colDesc.

	metaInfo is a dictionary containing metadata; keys we currently support:
	* name
	* description
	* id
	Unknown keys are silently ignored.
	"""
	dataTable = Table(name=metaInfo.get("name", "data"),
		description=metaInfo.get("description", ""))
	if metaInfo.has_key("id"):
		dataTable.id = id
	_mapValues(colDesc, data)
	_defineFields(colDesc, dataTable)
	dataTable.data = data
	return dataTable


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


def writeSimpleTable(colDesc, data, metaInfo, destination):
	"""writes a single-table, single-resource VOTable to destination.

	Arguments:

	* colDesc -- a sequence of dictionaries defining the fields, as
	  given by sqlsupport.metaTableHandler
	* data -- a sequence of sequences giving the rows to be formatted
	* metaInfo -- a dictionary containing meta information (more info coming up)
	* destination -- a file-like object to write the XML to
	"""
	writeTable([Resource(tables=[
			buildTable(colDesc, data, metaInfo)])],
		{}, destination)


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
	writeSimpleTable(getFieldInfos(querier, "ppmx.autocorr"),
		result, {}, open("/dev/null", "w"))

	

if __name__=="__main__":
	_test()
