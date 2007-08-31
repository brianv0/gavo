"""
Functions for parsing and generating VOTables to and from data and metadata.

This module also serves as a q'n'd interface to VOTable.DataModel in that
it imports all names from there.  Thus, you can get DataModel.Table as
votable.Table.

The module provides the glue between the row lists and the DataField
based description from the core modules and pyvotable.  

An important task is the mapping of values.  To do this, we define coder
factories.  These are functions receiving an instance of a value to pack and a
description of the target field.  They return either None (meaning they don't
know how to do the conversion) or a callable that does the conversion.
They may change the description of the target field, e.g., to fix types
(see datetime) or to add nullvalues (see ints).  Note that the type we
operate on here still are python and/or SQL types.

The first factory providing such a callable wins.  The factories register
with a ValueEncoderFactoryRegistry object that's used by getCoder.
"""

import sys
import re
import itertools
try:
	import cElementTree as ElementTree
except ImportError:
	sys.stderr.write("Warning: Falling back to python elementtree\n")
	from elementtree import ElementTree

from gavo import typesystems
from gavo import config

from VOTable import Writer
from VOTable.DataModel import *
from VOTable import Encoders


class Error(Exception):
	pass


errorTemplate = """<?xml version="1.0" encoding="utf-8"?>
<VOTABLE version="1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
	xsi:noNamespaceSchemaLocation="xmlns=http://www.ivoa.net/xml/VOTable/v1.1">
	<RESOURCE>
		<INFO>%(errmsg)s</INFO>
	</RESOURCE>
</VOTABLE>"""


class ValueMapperFactoryRegistry(object):
	"""is an object clients can ask for functions fixing up values
	for encoding.

	A mapper factory is just a function that takes a "representative"
	instance and the column properties It must return either None
	(for "I don't know how to make a function for this combination
	of value and column properties") or a callable that takes a
	value of the given type and returns a mapped value.

	To add a mapper, call registerFactory.  To find a mapper for a
	given combination of value and column properties, call getMapper.

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

	def getMapper(self, instance, colProps):
		"""returns a mapper for values with the python value instance, 
		according to colProps.

		This method may change colProps (which is the usual dictionary
		mapping column property names to their values).

		We do a linear search here, so you shouldn't call this function too
		frequently.
		"""
		for factory in self.factories:
			mapper = factory(instance, colProps)
			if mapper:
				break
		else:
			mapper = self.identity
		return mapper


_defaultMapperRegistry = ValueMapperFactoryRegistry()
_registerDefaultMF = _defaultMapperRegistry.registerFactory


try:
	from mx import DateTime

	def _mxDatetimeMapperFactory(srcInstance, colProps):
		"""returns mapper for mxDateTime objects.

		Unit may be yr or a (produces julian fractional years like J2000.34),
		d (produces julian days), s (produces a unix timestamp, for whatever
		that's good), "Y:M:D" (produces an iso date).
		"""
		unit = colProps["unit"]
		if isinstance(srcInstance, DateTime.DateTimeType):
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
			colProps["type"] = destType
			return fun
	_registerDefaultMF(_mxDatetimeMapperFactory)

except ImportError:
	pass

import datetime

def _datetimeMapperFactory(srcInstance, colProps):
	import time

	def dtToJdn(val):
		"""returns a julian day number for the dateTime instance val.
		"""
		a = (14-val.month)//12
		y = val.year+4800-a
		m = val.month+12*a-3
		return val.day+(153*m)//5+365*y+y//4-y//100+y//400-32045

	if isinstance(srcInstance, datetime.date):
		unit = colProps["unit"]
		if unit=="yr" or unit=="a":
			fun, destType = lambda val: val and dtToJdn(val)/365.25-4712, "double"
		elif unit=="d":
			fun, destType = lambda val: val and val.jdn, "double"
		elif unit=="s":
			fun, destType = lambda val: val and time.mktime(val.timetuple()), "double"
		elif unit=="Y:M:D":
			fun, destType = lambda val: val and val.isoformat(), "text"
		else:   # Fishy, but not our fault
			fun, destType = lambda val: val and dtToJdn(val), "double"
		colProps["type"] = destType
		return fun
_registerDefaultMF(_datetimeMapperFactory)


def _booleanMapperFactory(srcInstance, colProps):
	if colProps["type"]=="boolean":
		def coder(val):
			if val:
				return "1"
			else:
				return "0"
		return coder
_registerDefaultMF(_booleanMapperFactory)


def _floatMapperFactory(srcInstance, colProps):
	if colProps["type"]=="real" or colProps["type"].startswith("double"):
		naN = float("NaN")
		def coder(val):
			if val==None:
				return naN
			return val
		return coder
_registerDefaultMF(_floatMapperFactory)


# XXX FIXME
# This is a bad hack that fixes nullvalues to some random values.
# I can't see a good way of doing this without first having a pass
# through the data -- which probably is what we'll need to have in 
# the end.
# Then again, this currently isn't supported by pyvotable anyway,
# so let's first fix VALUES there.
NULLVALUE_HACK = {
	"smallint": 255,
	"int": -9999,
	"integer": -99999999,
	"bigint": -99999999,
}

def _intMapperFactory(srcInstance, colProps):
	if colProps["type"] in NULLVALUE_HACK:
		nullvalue = NULLVALUE_HACK[colProps["type"]]
		def coder(val):
			if val==None:
				return nullvalue
			return val
		colProps["nullvalue"] = NULLVALUE_HACK[colProps["type"]]
		return coder
_registerDefaultMF(_intMapperFactory)


def getMapperRegistry():
	"""returns a copy of the default value mapper registry.
	"""
	return ValueMapperFactoryRegistry(
		_defaultMapperRegistry.getFactories())


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


def _getFieldItemsFor(colInd, colProps):
	"""returns a dictionary with keys for a DataModel.Field constructor.
	"""
	fieldItems = {
		"name": colProps["fieldName"],
		"ID": "col%02d"%colInd,
	}
	type, size = typesystems.sqltypeToVOTable(colProps["type"])
	fieldItems["datatype"] = type
	if size!="1":
		fieldItems["arraysize"] = size
	for fieldName in ["ucd", "utype", "unit", "width", "precision"]:
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


def _mapValues(colDesc, data, mapperFactory):
	"""fixes the values of data to match what is required by colDesc.

	As a side effect, the types given in colDesc may change.
	"""
	colTypes = _getValSeq(data)
	handlers = []
	for colType, colProps in zip(colTypes, colDesc):
		handler = mapperFactory.getMapper(colType, colProps)
		handlers.append(handler)
	if data:
		colInds = range(len(data[0]))
		for rowInd, row in enumerate(data):
			data[rowInd] = [handlers[colInd](row[colInd]) for colInd in colInds]
	

def buildTable(colDesc, data, metaInfo, tdEncoding=False, 
		mapperFactory=_defaultMapperRegistry):
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
	if tdEncoding:
		votEncoder = Encoders.TableDataEncoder
	else:
		votEncoder = Encoders.BinaryEncoder
	dataTable = Table(name=metaInfo.get("name", "data"),
		description=metaInfo.get("description", ""), coder=votEncoder)
	if metaInfo.has_key("id"):
		dataTable.id = id
	_mapValues(colDesc, data, mapperFactory)
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


def writeSimpleTable(colDesc, data, metaInfo, destination, tdEncoding=False,
		mapperFactory=_defaultMapperRegistry):
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
				buildTable(colDesc, data, metaInfo, tdEncoding, mapperFactory)])],
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
	writeSimpleTable(getFieldInfos(querier, "ppmx.autocorr"),
		result, {}, open("/dev/null", "w"))


if __name__=="__main__":
	#_test()
	_profilerun()
