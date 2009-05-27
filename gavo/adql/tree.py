"""
Trees of ADQL expressions and operations on them.

The most important thing happening here is field resolution, which happens
in addFieldInfos.  addFieldInfos needs a function that takes a qualified
table name and returns a sequence of FieldInfo objects for the fields
in the table, maintaining the order they have in the database table.

We then traverse the tree and wrap these in FieldInfosForTable objects
for every tableReference we encounter; these objects are then attached
to the tableReferences in fieldInfo attributes.  

Then we traverse the tree again, this time looking for 
querySpecifications nodes. There receive a FieldInfosForQuery object 
in their fieldInfos attribute from all fieldInfos in their selectList.
This traversal is -- as basically all in this process -- postorder, which
means that by the time the selectList is resolved, all entries in the 
fromClause already have FieldInfos.

The selectList resolution happens in the FieldInfosForQuery constructor
by doing another postorder traversal over every subtree in the selectList.
Literals receive a common.dimlessFieldInfo as their FieldInfo,
columnReferences ask the querySpecification (and this its fromClause)
for fieldInfos, all others get combined according to rules in the
node's addFieldInfo method.
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
	  name is not unique.  Column names are normalized by lowercasing here.
	"""
	def __init__(self):
		self.seq, self.columns = [], {},

	def __repr__(self):
		return "<Column information %s>"%(repr(self.seq))

	def addColumn(self, label, info):
		"""adds a new visible column to this info.

		This entails both entering it in self.columns and in self.seq.
		"""
		# XXX TODO: handle delimited identifiers
		label = label.lower()
		if label in self.columns:
			self.columns[label] = None # Sentinel for ambiguous names
		else:
			self.columns[label] = info
		self.seq.append((label, info))

	def getFieldInfo(self, colName):
		# XXX TODO: handle delimited identifiers
		colName = colName.lower()
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
		self._collectSubTables(node)
		self._resolveSelectChildren(node)
		for col in node.getSelectFields():
			self.addColumn(col.name, col.fieldInfo)
	
	def _resolveSelectChildren(self, queryNode):
		def traverse(node):
			for c in node.iterNodes():
				traverse(c)
			if hasattr(node, "fieldInfo"):
				node.addFieldInfo(self.getFieldInfoFromSources)
		for selField in queryNode.getSelectFields():
			traverse(selField)

	def _collectSubTables(self, node):
		"""creates the subTables attribute with any tables visible from node.
		"""
		self.subTables = {}
		for subRef in node.fromClause.tablesReferenced:
			if hasattr(subRef, "fieldInfos"):
				self.subTables[subRef.tableName.name] = subRef

	def getFieldInfoFromSources(self, colName):
		"""returns a field info for colName from anything in the from clause.

		i.e., the columns in the select clause are ignored.
		"""
		# XXX TODO: handle delimited identifiers
		colName = colName.lower()
		matched = []
		for t in self.subTables.values():
			subCols = t.fieldInfos.columns
			if colName in subCols and subCols[colName]:
				matched.append(subCols[colName])
		return nodes.getUniqueMatch(matched, colName)

	def getFieldInfo(self, colName):
		"""returns a field info for colName in self and the joined tables.

		To do that, it collects all fields of colName in self and subTables and
		returns the matching field if there's exactly one.  Otherwise, it
		will raise ColumnNotFound or AmbiguousColumn.
		"""
		ownMatch = self.columns.get(colName, None)
		if ownMatch:
			return ownMatch
		else:
			return self.getFieldInfoFromSources(colName)
	

class FieldInfosForTable(FieldInfos):
	"""is a container for information on the columns produced by a 
	table reference or a join.
	"""
	def __init__(self, node, fieldInfoGetter):
		FieldInfos.__init__(self)
		for colName, fieldInfo in fieldInfoGetter(
				node.originalTable.qName):
			self.addColumn(colName, fieldInfo)
		self._addInfosFromJoined(node)

	def _addInfosFromJoined(self, node):
		for jt in getattr(node, "joinedTables", ()):
			for label, info in jt.fieldInfos.iteritems():
				self.addColumn(label, info)
	

_grammarCache = None

def autocollapse(nodeBuilder, children):
	"""inhibts the construction via nodeBuilder if children consists of
	a single ADQLNode.

	This function will automatically be inserted into the the constructor
	chain if the node defines an attribute collapsible=True.
	"""
	if len(children)==1 and isinstance(children[0], nodes.ADQLNode):
		return children[0]
	return nodeBuilder(children)


_additionalNodes = []
def registerNode(node):
	"""registers a node class or a symbolAction from a module other than node.

	This is a bit of magic -- some module can call this to register a node
	class that is then bound to some parse action as if it were in nodes.

	I'd expect this to be messy in the presence of chaotic imports (when
	classes are not necessarily singletons and a single module can be
	imported more than once.  For now, I ignore this potential bomb.
	"""
	_additionalNodes.append(node)


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
				syms[symName].addParseAction(lambda s, pos, toks: 
					autocollapse(nodeClass, toks))
			else:
				syms[symName].addParseAction(lambda s, pos, toks: 
					nodeClass(toks))
		except KeyError:
			raise KeyError("%s asks for non-existing symbol %s"%(
				nodeClass.__name__ , symName))

	def bindObject(ob):
		if isinstance(ob, type) and issubclass(ob, nodes.ADQLNode):
			for binding in getattr(ob, "bindings", [ob.type]):
				if binding:
					bind(binding, ob)
		if hasattr(ob, "parseActionFor"):
			for sym in ob.parseActionFor:
				bind(sym, ob)

	for name in dir(nodes):
		bindObject(getattr(nodes, name))

	for ob in _additionalNodes:
		bindObject(ob)

	return syms, root


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
	a fieldInfos attribute.  See ColumnResolver.
	"""
	attachFieldInfosToTables(qTree, fieldInfoGetter)
	def traverse(node, table):
		for child in node.iterNodes():
			traverse(child, table)
		if node.type=="querySpecification":
			node.fieldInfos = FieldInfosForQuery(node)
	traverse(qTree, None)


def dumpFieldInfoedTree(tree):
	import pprint
	def traverse(node):
		res = []
		if hasattr(node, "fieldInfo"):
			res.append("%s <- %s"%(node.type, repr(node.fieldInfo)))
		if hasattr(node, "fieldInfos"):
			res.append("%s -- %s"%(node.type, repr(node.fieldInfos)))
		res.extend(filter(None, [traverse(child) for child in node.iterNodes()]))
		if len(res)==1:
			return res[0]
		else:
			return res
	pprint.pprint(traverse(tree))
		

if __name__=="__main__":
	import pprint
	def fig(tableName):
		if tableName=="z":
			return {"a": "cm", "b": "km", "c": "arcsec/yr"}
		elif tableName=="y":
			return {"ya": "foot", "yb": "furlong", "yc": "inch"}
		else:
			return {}
	s, g = getTreeBuildingGrammar()
	res = g.parseString("select 1+0.1, 'const'||'ab' from spatial")[0]
	pprint.pprint(res.asTree())
	print repr(res)
	fd = addFieldInfos(res, fig)
	#print "Res:", res.fieldInfos.seq
	#print res.getSourceTableNames()
