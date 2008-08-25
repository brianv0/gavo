"""
Trees of ADQL expressions and operations on them.
"""

import sys
import traceback
import weakref

from gavo.adql import grammar
from gavo.adql import nodes
from gavo.adql.common import *


class FieldInfos(object):
	"""is a container for information about columns and such.

	Subclasses of those are attached to physical tables, joins, and
	subqueries.

	It consists of the following attributes:
	
	* seq -- a sequence of attributes of the columns in the
	  order in which they are selected (this is random if the table comes
	  from the db)
	* columns -- maps column names to attributes or None if a column
	  name is not unique.
	"""
	def __init__(self):
		self.seq, self.columns = [], {},

	def __repr__(self):
		return "<Column information %s>"%(repr(self.seq))

	def addColumn(self, label, info):
		"""adds a new visible column to this info.

		This entails both entering it in self.columns and in self.seq.
		"""
		if label in self.columns:
			self.columns[label] = None # Sentinel for ambiguous names
		else:
			self.columns[label] = info
		self.seq.append((label, info))

	def getFieldInfo(self, colName):
		fi = self.columns.get(colName, nodes.Absent)
		if fi is nodes.Absent:
			raise ColumnNotFound(colName)
		return fi


class FieldInfosForQuery(FieldInfos):
	"""is a container for information on the columns produced by a
	subquery.

	In addition to FieldInfos' attributes, it has: 

	* subTables -- maps table names of subtables to their nodes (that in
	  turn have subTables if they already have been visited by the 
	  ColumnResolver)

	"""
	def __init__(self, node):
		FieldInfos.__init__(self)
		for col in node.selectList.selectFields:
			self.addColumn(col.name, col.fieldInfo)
		self._collectSubTables(node)

	def _collectSubTables(self, node):
		"""creates the subTables attribute with any tables visible from node.
		"""
		for subRef in node.fromClause.tablesReferenced:
			if hasattr(subRef, "colsInfo"):
				self.subTables[subRef.tableName.name] = subRef

	def getFieldInfo(self, colName):
		"""returns a field info for colName in self and the joined tables.

		To do that, it collects all fields of colName in self and subTables and
		returns the matching field if there's exactly one.  Otherwise, it
		will raise ColumnNotFound or AmbiguousColumn.
		"""
		ownMatch = self.columns.get(colName, None)
		if ownMatch:
			matched = [ownMatch]
		else:
			matched = []
		for t in self.subTables.values():
			subCols = t.colsInfo.columns
			if colName in subCols and subCols[colName]:
				matched.append(subCols[colName])
		return nodes.getUniqueMatch(matches, colName)
	

class FieldInfosForTable(FieldInfos):
	"""is a container for information on the columns produced by a 
	table reference or a join.

	Note that the order of fields in seq is essentially random here.
	"""
	def __init__(self, node, fieldInfoGetter):
		FieldInfos.__init__(self)
		for colName, fieldInfo in fieldInfoGetter(
				node.originalTable.qName).iteritems():
			self.addColumn(colName, fieldInfo)
		self._addInfosFromJoined(node)

	def _addInfosFromJoined(self, node):
		for jt in getattr(node, "joinedTables", ()):
			for label, info in jt.colsInfo.iteritems():
				self.addColumn(label, info)
	

_grammarCache = None

def autocollapse(nodeBuilder, children):
	"""inhibts the construction via nodeBuilder if children consists of
	a single ADQLNode.

	This function will automatically be inserted into the the constructor
	chain if the node defines an attribute collapsible=True.
	"""
	if (len(children)==1 and isinstance(children[0], nodes.ADQLNode)):
		return children[0]
	return nodeBuilder(children)


def getTreeBuildingGrammar():
	"""returns a pyparsing symbol that can parse ADQL expressions into
	simple trees of ADQLNodes.

	This symbol is shared, so don't change anything on it.
	"""
# To do the bindings, we iterate over the names in the node module, look for
# all children classes derived from nodes.ADQLNode (but not ADQLNode itself) and
# first check for a bindings attribute and then their type attribute.  These
# are then used to add actions to the corresponding symbols.

	global _grammarCache
	if _grammarCache:
		return _grammarCache
	syms, root = grammar.getADQLGrammarCopy()

	def bind(symName, nodeClass):
		try:
			if getattr(nodeClass, "collapsible", False):
				syms[symName].setParseAction(lambda s, pos, toks: 
					autocollapse(nodeClass, toks))
			else:
				syms[symName].setParseAction(lambda s, pos, toks: 
					nodeClass(toks))
		except KeyError:
			raise KeyError("%s asks for non-existing symbol %s"%(
				nodeClass.__name__ , symName))

	for name in dir(nodes):
		ob = getattr(nodes, name)
		if isinstance(ob, type) and issubclass(ob, nodes.ADQLNode):
			for binding in getattr(ob, "bindings", [ob.type]):
				if binding:
					bind(binding, ob)
		if hasattr(ob, "parseActionFor"):
			for sym in ob.parseActionFor:
				bind(sym, ob)
	return root


def attachFieldInfosToTables(node, fieldInfoGetter):
	"""adds fieldInfos attributes mapping column names within the table
	to fieldInfos for all tableReferences.
	"""
	for c in node.iterNodes():
		attachFieldInfosToTables(c, fieldInfoGetter)
	if node.type=="tableReference":
		node.fieldInfos = FieldInfosForTable(node, fieldInfoGetter)


def addFieldInfos(qTree, fieldInfoGetter):
	"""adds field definitions to the parsed query tree qTree.

	For the fieldInfoGetter argument, see ColumnResolver.
	The result of this is that each column bearing node in qTree gets
	a colsInfo attribute.  See ColumnResolver.
	"""
	attachFieldInfosToTables(qTree, fieldInfoGetter)
	def traverse(node, table):
		if hasattr(node, "resolveField"):
			table = node
		for child in node.iterNodes():
			traverse(child, table)
		if node.type=="querySpecification":
			node.fieldInfos = FieldInfosForQuery(node)
		if hasattr(node, "fieldInfo"):
			node.addFieldInfo(table)
	traverse(qTree, None)


class FieldInfo(object):
	"""is a container for meta information on columns.

	It is constructed with a unit, a ucd and userData.  UserData is
	opaque to the library and is just collected on operations.
	"""
	tainted = False

	def __init__(self, unit, ucd, userData):
		self.ucd = ucd
		self.warnings = []
		self.errors = []
		self.userData = userData
		self.unit = unit
	
	def __repr__(self):
		return "FieldInfo(%s, %s, %s)"%(repr(self.unit), repr(self.ucd),
			repr(self.userData))


if __name__=="__main__":
	import pprint
	def fig(tableName):
		if tableName=="z":
			return {"a": "cm", "b": "km", "c": "arcsec/yr"}
		elif tableName=="y":
			return {"ya": "foot", "yb": "furlong", "yc": "inch"}
		else:
			return {}
	g = getTreeBuildingGrammar()
	res = g.parseString("select * from stars where CONTAINS(POINT('ICRS', raj2000, dej2000), CIRCLE('ICRS', 34.0, 33.2, 1))=1")[0]
#	pprint.pprint(res.asTree())
	print repr(res)
#	fd = addFieldInfos(res, fig)
	#print "Res:", res.colsInfo.seq
	print res.getSourceTableNames()
