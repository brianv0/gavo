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
from gavo import config
from gavo import utils
from gavo import valuemappers

from gavo.imp.VOTable import Writer
from gavo.imp.VOTable.DataModel import *
from gavo.imp.VOTable import Encoders
from gavo.imp.VOTable.Writer import namespace
from gavo import meta


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


# XXX TODO: most of the mapping code in here is obsolete and should be scapped
# in favour of the functions provided by valuemappers.

class TableData:
	"""is a tabular data for VOTables.

	It is constructed from a table.Table instance and
	a MapperFactoryRegistry.  It will do two sweeps through
	the complete data, first to establish value ranges including
	finding out if there's NULL values.  Then, it does another sweep
	converting the sequence of dicts to a sequence of properly typed
	and formatted tuples.
	"""
	def __init__(self, table, mFRegistry=valuemappers.defaultMFRegistry):
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
			colProps[field.get_dest()] = valuemappers.ColProperties(field)
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
					if row[key] is not None:
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


class VOTableMaker:
	"""is a facade wrapping the process of writing a VOTable.

	Its main method is makeVOT turning a DataSet into a VOTable.
	"""
	def __init__(self, tablecoding="binary",
			mapperFactoryRegistry=valuemappers.defaultMFRegistry):
		self.tablecoding = tablecoding
		self.mFRegistry = mapperFactoryRegistry

	def _addInfo(self, name, content, node, value="", id=None):
		"""adds info item "name" containing content having value to node
		unless both content and value are empty.
		"""
		if isinstance(content, meta.InfoItem):
			name, value, id = content.infoName, content.infoValue, content.infoId
		if content:
			content = str(content).strip()
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

	_voFieldCopyKeys = ["name", "ID", "datatype", "ucd",
		"utype", "unit", "description"]

	def _getVOFieldArgs(self, colProperties):
		"""returns a dictionary suitable for construction a VOTable field
		from colProperties.
		"""
		def _addValuesKey(cp, fieldArgs):
			"""adds a VOTable VALUES node to fieldArgs when interesting.
			"""
			valArgs = {}
			if cp["min"] is not valuemappers._Supremum:
				valArgs["min"] = Min(value=str(cp["min"]))
			if cp["max"] is not valuemappers._Infimum:
				valArgs["max"] = Max(value=str(cp["max"]))
			if cp["hasNulls"]:
				if cp.has_key("nullvalue"):
					valArgs["null"] = str(cp["nullvalue"])
			if valArgs:
				valArgs["type"] = "actual"
				vals = Values(**valArgs)
				# hasNulls could help the encoder optimize if necessary.
				# Since VOTable.VOObject doesn't serialize booleans, this won't show
				# in the final XML.
				vals.hasNulls = cp.nullSeen
				fieldArgs["values"] = vals
		res = {}
		for key in self._voFieldCopyKeys:
			res[key] = colProperties[key]
		if colProperties["arraysize"]!="1":
			res["arraysize"] = colProperties["arraysize"]
		if colProperties.has_key("value"):  # for PARAMs
			res["value"] = str(colProperties["value"])   # XXX TODO: use value mappers
		_addValuesKey(colProperties, res)
		return res

	def _defineFields(self, tableNode, colProperties):
		"""defines the fields in colProperties within the VOTable tableNode.

		colProperties is a sequence of ColProperties instances.  I need to
		work on my naming...
		"""

		for colProp in colProperties:
			tableNode.fields.append(
				Field(**self._getVOFieldArgs(colProp)))

	def _defineParams(self, resourceNode, items, values):
		for item in items:
			cp = valuemappers.ColProperties(item)
			if values.has_key(item.get_dest()):
				cp["value"] = values[item.get_dest()]
			resourceNode.params.append(Param(**self._getVOFieldArgs(cp)))
				
	def _makeTable(self, res, table):
		"""returns a Table node for the table.Table instance table.
		"""
		t = Table(name=table.getName(), coder=_tableEncoders[self.tablecoding],
			description=unicode(table.getMeta("description", propagate=False, 
				default="")))
		data = TableData(table, self.mFRegistry)
		self._defineFields(t, data.getColProperties())
		t.data = data.get()
		return t
	
	def _addResourceMeta(self, res, dataSet):
		"""adds resource metadata to the Resource res.
		"""
		res.description = unicode(dataSet.getMeta("description", propagate=False,
			default=""))
		self._addInfo("legal", dataSet.getMeta("_legal"), res)
		for infoItem in dataSet.getMeta("info", default=[]):
			self._addInfo(None, infoItem, res)
		self._addLink(dataSet.getMeta("_infolink"), res)

	def _makeResource(self, dataSet):
		"""returns a Resource node for dataSet.
		"""
		args = {}
		resType = dataSet.getMeta("_type")
		if resType:
			args["type"] = str(resType)
		res = Resource(**args)
		self._defineParams(res, dataSet.getDocFields(), dataSet.getDocRec())
		self._addResourceMeta(res, dataSet)
		for table in dataSet.getTables():
			if table.getFieldDefs():
				res.tables.append(self._makeTable(res, table))
		return res

	def _setGlobalMeta(self, vot, dataSet):
		"""add meta elements from the resource descriptor to vot.
		"""
		rd = dataSet.getDescriptor().getRd()
		vot.description = unicode(rd.getMeta("description", default=""))
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


if __name__=="__main__":
	_test()
	#_profilerun()
