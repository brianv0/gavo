"""
Functions for parsing and generating VOTables to and from data and metadata.

This module also serves as an interface to VOTable.DataModel in that
it imports all names from there.  Thus, you can get DataModel.Table as
votable.Table.

The module provides the glue between the row lists and the Column
based description from the core modules and pyvotable.  
"""

import gzip
import sys
import re
import itertools
import urllib
import urlparse
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import stc
from gavo import utils
from gavo.base import valuemappers
from gavo.formats import common
from gavo.grammars import votablegrammar
from gavo.utils import ElementTree

from gavo.imp import VOTable
from gavo.imp.VOTable import DataModel as DM
from gavo.imp.VOTable import Writer
from gavo.imp.VOTable import Encoders
from gavo.imp.VOTable.Writer import namespace


class Error(base.Error):
	pass


MS = base.makeStruct

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


class VOTableMaker(utils.IdManagerMixin):
	"""A process wrapper for writing a VOTable.

	Its main method is makeVOT turning a Data instance into a VOTable.
	"""
	def __init__(self, tablecoding="binary",
			mapperFactoryRegistry=valuemappers.defaultMFRegistry):
		self.tablecoding = tablecoding
		self.mFRegistry = mapperFactoryRegistry

	def _addInfo(self, name, node, content=None, value="", id=None):
		"""adds info item "name" containing content having value to node
		unless both content and value are empty.
		"""
		if isinstance(content, base.MetaInfoItem):
			name, value, id = content.infoName, content.infoValue, content.infoId
		if content:
			content = unicode(content).strip()
		if content or value:
			i = DM.Info(name=name, text=unicode(content))
			i.value = unicode(value)
			if id:
				i.ID = id
			node.info.append(i)

	def _addLink(self, href, node, contentRole=None, title=None,
			value=None):
		"""adds a link item with href to node.

		Apart from title, the further arguments are ignored right now.
		"""
		if href:
			l = DM.Link(href=href, title=title)
			node.links.append(l)

	_voFieldCopyKeys = ["name", "ID", "datatype", "ucd",
		"utype", "unit", "description"]

	def _getVOFieldArgs(self, colDesc):
		"""returns a dictionary suitable for construction a VOTable field
		from colDesc.
		"""
		def _addValuesKey(cp, fieldArgs):
			"""adds a VOTable VALUES node to fieldArgs when interesting.
			"""
			valArgs = {}
			if cp["min"] is not valuemappers._Supremum:
				valArgs["min"] = DM.Min(value=str(cp["min"]))
			if cp["max"] is not valuemappers._Infimum:
				valArgs["max"] = DM.Max(value=str(cp["max"]))
			if cp["hasNulls"]:
				if cp.has_key("nullvalue"):
					valArgs["null"] = str(cp["nullvalue"])
			if valArgs:
				valArgs["type"] = "actual"
				vals = DM.Values(**valArgs)
				# hasNulls could help the encoder optimize if necessary.
				# Since VOTable.VOObject doesn't serialize booleans, this won't show
				# in the final XML.
				vals.hasNulls = cp.nullSeen
				fieldArgs["values"] = vals
		res = {}
		for key in self._voFieldCopyKeys:
			if key in colDesc:
				res[key] = colDesc[key]
		res["arraysize"] = colDesc["arraysize"]
		if colDesc.has_key("value"):  # for PARAMs
			res["value"] = str(colDesc["value"])   # XXX TODO: use value mappers
# Only if we absolutely must (obsolete standard)
#		if colDesc["stc"]:
#			res["ref"] = colDesc["stc"].id
#			res["utype"] = colDesc["stcUtype"]
		_addValuesKey(colDesc, res)
		return res

	def _defineFields(self, tableNode, serManager):
		"""defines the FIELDS in VOTable tableNode based on serManger's columns.
		"""
		for colDesc in serManager:
			tableNode.fields.append(
				DM.Field(**self._getVOFieldArgs(colDesc)))

	def _defineParams(self, resourceNode, items, values):
		for item in items:
			cp = valuemappers.VColDesc(item)
			if values.has_key(item.name):
				cp["value"] = values[itemname]
			resourceNode.params.append(DM.Param(**self._getVOFieldArgs(cp)))

	def _addSTC(self, votTable, tableDef, serManager):
		"""adds STC groups for the systems to votTable fetching data from 
		tableDef.
		"""
		for stcId, system in tableDef.getSTCSystems(self):
			stcGroup = DM.Group(utype="stc:AstroCoordSystem", ID=stcId)
			for utype, val in stc.getUtypesForSystem(system)[0]:
				stcGroup.params.append(DM.Param(utype=utype, value=val,
					datatype="char", arraysize="*"))
			votTable.groups.append(stcGroup)
			cooGroup = DM.Group(utype="stc:AstroCoords", ref=stcId,
				ID=stcId+"_coo")
			for col in serManager:
				# add column reference if column is described by this system
				if col["stcUtype"]:
					if col["stc"].id==stcId:
						cooGroup.groups.append(
							DM.Group(utype=col["stcUtype"], ref=col["ID"]))
			votTable.groups.append(cooGroup)

	def _makeTable(self, res, table):
		"""returns a Table node for the table.Table instance table.
		"""
		t = DM.Table(name=table.tableDef.id, 
			coder=_tableEncoders[self.tablecoding],
			description=unicode(table.tableDef.getMeta("description", 
				propagate=False, default="")))
		sm = valuemappers.SerManager(table, mfRegistry=self.mFRegistry)
		self._addSTC(t, table.tableDef, sm)
		self._defineFields(t, sm)
		t.data = list(sm.getMappedTuples())
		return t
	
	def _addResourceMeta(self, res, dataSet):
		"""adds resource metadata to the Resource res.
		"""
		res.description = unicode(dataSet.getMeta("description", 
			propagate=False, default=""))
		self._addInfo("legal", res, value=dataSet.getMeta("copyright"))
		for infoItem in dataSet.getMeta("info", default=[]):
			self._addInfo(None, res, content=infoItem)
		for table in dataSet.tables.values():
			for warning in table.getMeta("_warning", propagate=False, default=[]):
				self._addInfo("warning", res, value="In table %s: %s"%(
					table.tableDef.id, str(warning)))
		self._addLink(dataSet.dd.getMeta("_infolink"), res)

	def _makeResource(self, dataSet):
		"""returns a Resource node for dataSet.
		"""
		args = {}
		resType = dataSet.getMeta("_type")
		if resType:
			args["type"] = str(resType)
		res = DM.Resource(**args)
		try:
			parTable = dataSet.getTableWithRole("parameters")
			if parTable.rows:
				values = parTable.rows[0]
			else:
				values = {}
			self._defineParams(res, parTable.tableDef, values)
		except base.DataError: # no parameters
			pass
		self._addResourceMeta(res, dataSet)
		for table in dataSet:
			if table.role!="parameters" and table.tableDef.columns:
				res.tables.append(self._makeTable(res, table))
		return res

	def _setGlobalMeta(self, vot, dataSet):
		"""add meta elements from the resource descriptor to vot.
		"""
		rd = dataSet.dd.rd
		if rd is None:
			return
		vot.description = unicode(rd.getMeta("description", default=""))
		self._addInfo("legal", vot, rd.getMeta("copyright"))

	def makeVOT(self, data):
		"""returns a VOTable object representing data.

		data can be a Data or Table instance.
		"""
		data = rsc.wrapTable(data)
		vot = DM.VOTable()
		self._setGlobalMeta(vot, data)
		vot.resources.append(self._makeResource(data))
		return vot

	def writeVOT(self, vot, destination, encoding="utf-8"):
		writer = Writer(encoding)
		writer.write(vot, destination)


def getAsVOTable(data, tablecoding="binary"):
	"""returns a string containing a VOTable representation of data.

	This is mainly intended for debugging and "known-small" tables.
	data can be a data or a table instance.
	"""
	if isinstance(data, rsc.BaseTable):
		data = rsc.wrapTable(data)
	maker = VOTableMaker(tablecoding=tablecoding)
	dest = StringIO()
	maker.writeVOT(maker.makeVOT(data), dest)
	return dest.getvalue()


def writeDataAsVOTable(data, outputFile, tablecoding="binary"):
	"""a formats.common compliant data writer.
	"""
	maker = VOTableMaker(tablecoding=tablecoding)
	maker.writeVOT(maker.makeVOT(data), outputFile)

common.registerDataWriter("votable", writeDataAsVOTable)
common.registerDataWriter("votabletd", lambda data, outputFile:
	writeDataAsVOTable(data, outputFile, tablecoding="td"))


def _getSTCGroupsFromAny(votObj):
	return [g for g in votObj.groups if g.utype and g.utype.startswith("stc:")]


def _getSTCGroupsFromResource(votRes):
	"""extracts STC groups from the VOTable resource votRes.

	This is a helper for getSTCDefsFromVOTable.
	"""
	stcGroups = []
	stcGroups.extend(_getSTCGroupsFromAny(votRes))
	for t in votRes.tables:
		stcGroups.extend(_getSTCGroupsFromAny(t))
	for child in votRes.resources:
		stcGroups.extend(_getSTCGroupsFromResource(child))
	return stcGroups


def _getSTCGroupsFromVOTable(vot):
	"""extracts STC groups from the VOTable vot.

	This is a helper for getSTCDefsFromVOTable.
	"""
	allSTC = []
	for resource in vot.resources:
		allSTC.extend(_getSTCGroupsFromResource(resource))
	return allSTC


def _getSTCColumnsFromGroups(stcGroups):
	"""returns dictionaries containing STC information for systems and columns
	from raw VOTable stc groups.

	This is a helper for getSTCDefsFromVOTable; the argument is usually
	obtained from _getSTCGroupsFromVOTable.

	We remove the silly stc: "namespace prefix" from everything we can get
	our hands on.
	"""
	systems, columns = {}, {}
	for group in stcGroups:
		if group.utype=="stc:AstroCoords":  # collect id -> (utype, system) map
			for child in group.groups:
				columns[child.ref] = (group.ref, child.utype)
		elif group.utype=="stc:AstroCoordSystem": # parse system
			systems[group.id] = stc.parseFromUtypes([
				(p.utype, p.value) for p in group.params], {}
			).astroSystem
		else:
			raise base.Error("Invalid stc utype '%s'"%group.utype)
	return systems, columns


def getSTCDefsFromVOTable(vot):
	"""returns a map from IDs (of columns, typically) to pairs of STC system
	objects and the column's STC utype.

	This looks at group children of resource and table, gathering groups with
	utypes starting with "stc:"
	"""
	systems, columns = _getSTCColumnsFromGroups(
		_getSTCGroupsFromVOTable(vot))
	resolved = {}
	for colID, (sysID, utype) in columns.iteritems():
		try:
			resolved[colID] = (systems[sysID], utype)
		except KeyError:
			raise base.NotFoundError(sysId, "STC system group", "VOTable",
				hint="You probably have an invalid VOTable.  You could"
					" try removing all STC groups.")
	return resolved


def makeTableDefForVOTable(tableId, votTable, stcColumns, **moreArgs):
	"""returns a TableDef for a Table element parsed from a VOTable.

	Pass additional constructor arguments for the table in moreArgs.
	stcColumns is a dictionary mapping IDs within the source VOTable
	to pairs of stc and utype.
	"""
	columns = []
# it's important to create the names exactly like in VOTableGrammar
	nameMaker = votablegrammar.VOTNameMaker()
	for f in votTable.fields:
		colName = nameMaker.makeName(f)
		kwargs = {"name": colName,
			"tablehead": colName.capitalize(),
			"type": base.voTableToSQLType(f.datatype, f.arraysize)}
		for attName in ["ucd", "description", "unit"]:
			if getattr(f, attName, None) is not None:
				kwargs[attName] = getattr(f, attName)
		columns.append(MS(rscdef.Column, **kwargs))
		# STC info is not in managed attributes
		if f.ID in stcColumns:
			c = columns[-1]
			c.stc, c.stcUtype = stcColumns[f.ID]
	res = MS(rscdef.TableDef, id=tableId, columns=columns,
		**moreArgs)
	res.hackMixinsAfterMakeStruct()
	return res


def makeDDForVOTable(tableId, vot, gunzip=False, **moreArgs):
	"""returns a DD suitable for uploadVOTable.

	moreArgs are additional keywords for the construction of the target
	table.
	"""
	stcDefs = getSTCDefsFromVOTable(vot)
# XXX TODO: locate other resources and tables in them
	tableDef = makeTableDefForVOTable(tableId, vot.resources[0].tables[0],
		stcDefs, **moreArgs)
	return MS(rscdef.DataDescriptor,
		grammar=MS(votablegrammar.VOTableGrammar, gunzip=gunzip),
		makes=[MS(rscdef.Make, table=tableDef)])


def uploadVOTable(tableId, srcFile, connection, gunzip=False, **moreArgs):
	"""creates a temporary table with tableId containing the first table
	of the first resource in the VOTable that can be read from srcFile.

	The corresponding DBTable instance is returned.
	"""
	if gunzip:
		inputFile = StringIO(gzip.GzipFile(fileobj=srcFile, mode="r").read())
	else:
		inputFile = StringIO(srcFile.read())
	srcFile.close()
	vot = VOTable.parse(inputFile)
	myArgs = {"onDisk": True, "temporary": True}
	myArgs.update(moreArgs)
	dd = makeDDForVOTable(tableId, vot, **myArgs)
	inputFile.seek(0)
	return rsc.makeData(dd, forceSource=inputFile, connection=connection,
		).getPrimaryTable()


def _test():
	import doctest, votable
	doctest.testmod(votable)


if __name__=="__main__":
	_test()
	#_profilerun()
