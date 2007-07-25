"""
Functions for parsing and generating VOTables to and from data and metadata.

This module also serves as a q'n'd interface to VOTable.DataModel in that
it imports all names from there.  Thus, you can get DataModel.Table as
votable.Table.
"""

import sys
import re
try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree

from VOTable import Writer
from VOTable.DataModel import *


class Error(Exception):
	pass


def _getVoTypeForSqlType(dbtype, simpleMap={
		"smallint": ("short", "1"),
		"integer": ("int", "1"),
		"int": ("int", "1"),
		"bigint": ("long", "1"),
		"real": ("float", "1"),
		"float": ("float", "1"),
		"boolean": ("boolean", "1"),
		"double precision": ("double", "1"),
		"text": ("char", "*"),
		"date": ("double", "1"),
		"timestamp": ("double", "1"),
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


def _addFields(colDesc, dataTable):
	"""adds the field descriptions from colDesc triples to the DataModel.Table
	instance dataTable.
	"""
	for colInd, colOpts in enumerate(colDesc):
		dataTable.fields.append(
			Field(**_getFieldItemsFor(colInd, colOpts)))
			

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
	_addFields(colDesc, dataTable)
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
	"""
	writeTable([Resource(tables=[
			buildTable(colDesc, data, metaInfo)])],
		{}, destination)
