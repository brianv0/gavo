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

from gavo import stc
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
		self._collectSubTables(parent)

	def __repr__(self):
		return "<Column information %s>"%(repr(self.seq))

	def _namesMatch(self, table, toName):
		"""returns true when table could be referred to by toName.

		This means that either the name matches or toName is table's original
		name.

		toName is a qualified name (i.e., including schema).
		"""
		return (table.tableName.qName==toName.qName
			or (
				table.originalTable
				and
					table.originalTable==toName.qName))

	def locateTable(self, refName):
		"""returns a table instance matching the node.TableName refName.

		If no such table is in scope, the function raises a TableNotFound.
		"""
		for t in self.subTables:
			if self._namesMatch(t, refName):
				return t
			try:
				return t.fieldInfos.locateTable(refName)
			except TableNotFound:
				pass
		raise TableNotFound("No table %s found."%refName.qName)

	def addColumn(self, label, info):
		"""adds a new visible column to this info.

		This entails both entering it in self.columns and in self.seq.
		"""
		# XXX TODO: handle delimited identifiers
		label = label.lower()
		if label in self.columns:
			if self.columns[label]!=info:
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


# XXX TODO: The following two classes are ugly since the do way too
# much magic during construction.  I guess we should move to factories here.

class FieldInfosForTable(FieldInfos):
	"""Field annotations for tables.

	Instanciation needs an AnnotationContext object.
	"""
	def __init__(self, tableNode, context):
		FieldInfos.__init__(self, tableNode)

		# add infos for the table itself.
		if tableNode.originalTable:
			for colName, fieldInfo in context.retrieveFieldInfos(
					tableNode.originalTable):
				self.addColumn(colName, fieldInfo)

		# add infos for joined tables as necessary; since we to a postorder
		# traversal, those have already been annotated.
		for jt in getattr(tableNode, "joinedTables", ()):
			for label, info in jt.fieldInfos.seq:
				self.addColumn(label, info)

	def _collectSubTables(self, node):
		self.subTables = getattr(node, "joinedTables", [])


class FieldInfosForQuery(FieldInfos):
	"""A FieldInfos class that additionally knows how to obtain field infos
	in subtables.

	We want this for FieldInfos on queryExpressions.  When their select
	expressions figure out their fieldInfos, they call getFieldInfoFromSources.
	"""
	def __init__(self, queryNode, context):
		FieldInfos.__init__(self, queryNode)
		self._annotateSelectChildren(queryNode, context)
		self._collectColumns(queryNode)

	def _annotateSelectChildren(self, queryNode, context):
		def traverse(node, context):
			for c in node.iterNodeChildren():
				traverse(c, context)
			if hasattr(node, "addFieldInfo"):
				node.addFieldInfo(context)

		context.pushCR(queryNode.fieldInfos.getFieldInfo)
		for selField in queryNode.getSelectFields():
			traverse(selField, context)
		context.popCR()

	def _collectColumns(self, queryNode):
		for col in queryNode.getSelectFields():
			queryNode.fieldInfos.addColumn(col.name, col.fieldInfo)
	
	def _collectSubTables(self, queryNode):
		self.subTables = []
		for subRef in queryNode.fromClause.tablesReferenced:
			if hasattr(subRef, "getFieldInfo"):
				self.subTables.append(subRef)

	def getFieldInfoFromSources(self, colName, refName=None):
		"""returns a field info for colName from anything in the from clause.

		That is, the columns in the select clause are ignored.  Use this to
		resolve expressions from the queries' select clause.

		See getFieldInfo for reName
		"""
		colName = colName.lower()
		matched = []
		if refName is not None:
			subCols = self.locateTable(refName).fieldInfos.columns
			if colName in subCols and subCols[colName]:
				matched.append(subCols[colName])

		else: # no explicit table reference, look everywhere
			for t in self.subTables:
				subCols = t.fieldInfos.columns
				if colName in subCols and subCols[colName]:
					matched.append(subCols[colName])
		# XXX TODO: build a qualified colName here if necessary
		return getUniqueMatch(matched, colName)

	def getFieldInfo(self, colName, refName=None):
		"""returns a field info for colName in self and the joined tables.

		To do that, it collects all fields of colName in self and subTables and
		returns the matching field if there's exactly one.  Otherwise, it
		will raise ColumnNotFound or AmbiguousColumn.

		If the node.TableName instance refName is given, the search will be 
		restricted to the matching tables.
		"""
		ownMatch = None
		if refName is None:
			ownMatch = self.columns.get(colName, None)
		if ownMatch:
			return ownMatch
		else:
			return self.getFieldInfoFromSources(colName, refName)


class AnnotationContext(object):
	"""An context object for the annotation process.

	It is constructed with a field info retriever function (see above)
	and an equivalence policy for STC objects.

	It has errors and warnings attributes consisting of user-exposable
	error strings accrued during the annotation process.

	The annotation context also manages the namespaces for column reference
	resolution.  It maintains a stack of getters; when a new namespace
	for column resolution opens, call pushCR ("column resolver") with
	a function resolve(colName, tableName=None) -> fieldInfo.

	When the namespace closes, call popCR.
	"""
	def __init__(self, retrieveFieldInfos, equivalencePolicy=stc.defaultPolicy):
		self.retrieveFieldInfos = retrieveFieldInfos
		self.policy = equivalencePolicy
		self.colResolvers = []
		self.errors, self.warnings = [], []

	def pushCR(self, getter):
		self.colResolvers.append(getter)
	
	def popCR(self):
		return self.colResolvers.pop()

	def getFieldInfo(self, colName, tableName):
		"""returns the value of the current field info getter for tableName.

		This should be a sequence of (colName, common.FieldInfo) pairs.
		"""
		return self.colResolvers[-1](colName, tableName)


def _annotateTraverse(node, context):
	"""does the real tree traversal for annotate.
	"""
	for c in node.iterNodeChildren():
		_annotateTraverse(c, context)
	if hasattr(node, "feedInfosFromDB"):
		FieldInfosForTable(node, context)
	if hasattr(node, "getSelectFields"):
		FieldInfosForQuery(node, context)


def annotate(node, context):
	"""adds annotations to all nodes wanting some.

	This is done by a postorder traversal of the tree, identifying all
	annotable objects.

	context should be an AnnotationContext instance.  You can also just
	pass in a field info getter.  In that case, annotation runs with the
	default stc equivalence policy.

	The function returns the context used in any case.
	"""
	if not isinstance(context, AnnotationContext):
		context = AnnotationContext(context)
	_annotateTraverse(node, context)
	return context


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

