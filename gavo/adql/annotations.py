"""
Adding field infos to columns and other objects in an ADQL tree.

When we want to generate VOTables from ADQL queries, we must know types,
units, ucds, and the like, and we need to know STC information for
all columns in a query.

We have two kinds of annotations:

* FieldInfos object for columns and expressinos
* fieldInfo attributes for columns

fieldInfo is None in nodes coming from the parser.  Filling these out is the
object of this module.

To do that, we obtain the annotations for all columns actually
coming from the database.  This happens for all nodes having a
feedInfosFromDB attribute.

The fieldInfo attributes are filled out in all nodes having a
getSelectFields method (queryExpression, mainly).  The FieldInfoedNode
class provides addFieldInfo methods that know how to compute the
field infos.
"""

from gavo.adql.common import *


class FieldInfos(object):
	"""A base class for field annotations.

	Subclasses of those are attached to physical tables, joins, and
	subqueries.

	The information on columns is kept in two places:
	
	* seq -- a sequence of attributes of the columns in the
	  order in which they are selected (this is random if the table comes
	  from the db)
	* columns -- maps column names to attributes or None if a column
	  name is not unique.  Column names are normalized by lowercasing here.

	A FieldInfos object is instanciated with the object it will annotate,
	and the annotation (i.e., setting of the fieldInfos attribute on
	the parent) will happen during instanciation.
	"""
	def __init__(self, parent):
		self.seq, self.columns = [], {}
		parent.fieldInfos = self

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


class FieldInfosForTable(FieldInfos):
	"""Field annotations for tables.

	Instanciation needs a fieldInfoGetter that resolves table name and
	column name to field infos.
	"""
	def __init__(self, tableNode, fieldInfoGetter):
		FieldInfos.__init__(self, tableNode)

		# add infos for the table itself.
		for colName, fieldInfo in fieldInfoGetter(tableNode.originalTable):
			self.addColumn(colName, fieldInfo)

		# add infos for joined tables as necessary; since we to a postorder
		# traversal, those have already been annotated.
		for jt in getattr(tableNode, "joinedTables", ()):
			for label, info in jt.fieldInfos.iteritems():
				self.addColumn(label, info)


class FieldInfosForQuery(FieldInfos):
	"""A FieldInfos class that additionally knows how to obtain field infos
	in subtables.

	We want this for FieldInfos on queryExpressions.  When their select
	expressions figure out their fieldInfos, they call getFieldInfoFromSources.

	You must call collectSubTables(node) after construction.  We should
	change this somehow, but let's wait for a good idea.
	"""
	def __init__(self, queryNode):
		FieldInfos.__init__(self, queryNode)
		self._collectSubTables(queryNode)
		self._annotateSelectChildren(queryNode)
		self._collectColumns(queryNode)

	def _annotateSelectChildren(self, queryNode):
		getFieldInfos = queryNode.fieldInfos.getFieldInfo
		def traverse(node):
			for c in node.iterNodeChildren():
				traverse(c)
			if hasattr(node, "addFieldInfo"):
				node.addFieldInfo(getFieldInfos)
		for selField in queryNode.getSelectFields():
			traverse(selField)

	def _collectColumns(self, queryNode):
		for col in queryNode.getSelectFields():
			queryNode.fieldInfos.addColumn(col.name, col.fieldInfo)
	
	def _collectSubTables(self, queryNode):
		self.subTables = {}
		for subRef in queryNode.fromClause.tablesReferenced:
			if hasattr(subRef, "getFieldInfo"):
				self.subTables[subRef.tableName.name] = subRef

	def getFieldInfoFromSources(self, colName):
		"""returns a field info for colName from anything in the from clause.

		That is, the columns in the select clause are ignored.  Use this to
		resolve expressions from the queries' select clause.
		"""
		colName = colName.lower()
		matched = []
		for t in self.subTables.values():
			subCols = t.fieldInfos.columns
			if colName in subCols and subCols[colName]:
				matched.append(subCols[colName])
		return getUniqueMatch(matched, colName)

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


def annotate(node, fieldInfoGetter):
	"""adds annotations to all objects coming from the database.

	This is done by a postorder traversal of the tree, identifying all
	annotable objects.
	"""
	for c in node.iterNodeChildren():
		annotate(c, fieldInfoGetter)
	if hasattr(node, "feedInfosFromDB"):
		FieldInfosForTable(node, fieldInfoGetter)
	if hasattr(node, "getSelectFields"):
		FieldInfosForQuery(node)


def dumpFieldInfoedTree(tree):
	import pprint
	def traverse(node):
		res = []
		if hasattr(node, "fieldInfo"):
			res.append("%s <- %s"%(node.type, repr(node.fieldInfo)))
		if hasattr(node, "fieldInfos"):
			res.append("%s -- %s"%(node.type, repr(node.fieldInfos)))
		res.extend(filter(None, [traverse(child) for child in 
			node.iterNodeChildren()]))
		if len(res)==1:
			return res[0]
		else:
			return res
	pprint.pprint(traverse(tree))

