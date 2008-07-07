"""
Trees of ADQL expressions and operations on them.

In general, I've tried to keep as much in plain strings as possible to
avoid having gargantuous trees when we're really only interested in
rather few "hot spots".

On the downside, this means I have to check literals quite liberally.
"""

import weakref

import adql


class Error(Exception):
	pass

class ColumnNotFound(Error):
	"""will be raised if a column name cannot be resolved.
	"""

class AmbiguousColumn(Error):
	"""will be raised if a column name matches more than one column in a
	compound query.
	"""


class _VirtualC(type):
	def __nonzero__(self):
		return False # don't include Virtual in qName calculations

class SSubquery(object):
	"""is a sentinel pseudo-schema for a table not in the db.
	"""
	__metaclass__ = _VirtualC


def symbolAction(*symbols):
	"""is a decorator to mark functions as being a parseAction for symbol.

	This is evaluated by getADQLGrammar below.  Be careful not to alter
	global state in such a handler.
	"""
	def deco(func):
		for symbol in symbols:
			if hasattr(func, "parseActionFor"):
				func.parseActionFor.append(symbol)
			else:
				func.parseActionFor = [symbol]
		return func
	return deco


def getType(arg):
	"""returns the type of an ADQL node or the value of str if arg is a string.
	"""
	if isinstance(arg, basestring):
		return str
	else:
		return arg.type


def flatten(arg):
	"""returns the SQL serialized representation of arg.
	"""
	if isinstance(arg, basestring):
		return arg
	else:
		return arg.flatten()


@symbolAction("regularIdentifier")
def normalizeRIdentifier(toks):
	"""returns toks[0] in lowercase.
	"""
	assert len(toks)==1
	return toks[0].lower()


class ADQLNode(object):
	"""is a node within an ADQL parse tree.

	All ADQLNodes have type and children attributes.  All elements of
	children are either strings or ADQL nodes.

	ADQLNodes have a method flatten that return a string representation of
	the SQL fragment below them.

	Derived classes can override the _processChildren method to do any
	local analysis of self.children at construction time.
	"""
	type = "other"

	def __init__(self, children):
		self.children = children
		self._processChildren()

	def __iter__(self):
		return iter(self.children)

	def __repr__(self):
		return "<%s, %s>"%(self.type, self.children)

	def _processChildren(self):
		pass

	def getChildrenOfType(self, type):
		return [c for c in self if getType(c)==type]
	
	def getChildOfType(self, type):
		res = self.getChildrenOfType(type)
		if len(res)==0:
			raise KeyError("No %s child."%type)
		if len(res)!=1:
			raise ValueError("More than one %s child."%type)
		return res[0]

	def flatten(self):
		return " ".join([flatten(c) for c in self])

	def asTree(self):
		return tuple(isinstance(c, ADQLNode) and c.asTree() or c
			for c in self)


class TableName(ADQLNode):
	type = "tableName"
	cat = schema = name = None
	def _processChildren(self):
		parts = self.children[::2]
		parts = [None]*(3-len(parts))+parts
		self.cat, self.schema, self.name = parts
		self.qName = ".".join([n for n in [self.cat, self.schema, self.name] if n])


class CorrSpec(TableName): 
	type = "correlationSpecification"
	def _processChildren(self):
		self.qName = self.name = self.children[-1]
	

class TableReference(ADQLNode):
	"""is a table reference.

	These always have a name (tableName); if a correlationSpecification
	is given, this is whatever is behind AS.  The joinedTables attribute
	contains further table references if any are joined in.

	They may have an originalName if an actual table name (as opposed to a
	subquery) was used to specify the table.  Otherwise, there's either
	a subquery or a joined table that needs to be consulted to figure out
	what fields are available from the table.
	"""
	type = "tableReference"
	bindings = []  # will be created by dispatchTableReference
	colBearing = None
	joinedTables = []
	def __repr__(self):
		return "<tableReference to %s>"%",".join(self.getAllNames())

	def _processChildren(self):
		try:
			res = self.getChildOfType("correlationSpecification")
			self.tableName = res
			self.originalTable = self.getChildOfType("tableName")
		except KeyError:
			self.tableName = self.originalTable = self.getChildOfType("tableName")
		self.joinedTables = self.getChildrenOfType("tableReference")

	def getAllNames(self):
		yield self.tableName.qName
		for t in self.joinedTables:
			yield t.tableName.qName


class QuerySpecification(ADQLNode): 
	type = "querySpecification"
	colBearing = None
	def _processChildren(self):
		self.selectList = self.getChildOfType("selectList")
		self.fromClause = self.getChildOfType("fromClause")
		self.query = weakref.proxy(self)
	
	def getSelectList(self):
		return [c.colName for c in self.selectList.getColRefs()]

	def getSourceTableNames(self):
		return self.fromClause.getTableNames()


class AliasedQuerySpecification(QuerySpecification):
	"""is a QuerySpecification with a correlationSpecification.
	"""
	bindings = [] # will be created by dispatchTableReference
	def _processChildren(self):
		try:
			self.tableName = self.getChildOfType("correlationSpecification")
		except KeyError:  # shouldn't happen, but doesn't hurt
			pass
		# adopt children of original query specification
		newChildren = []
		for c in self.children:
			if getType(c)=="querySpecification":
				newChildren.extend(c.children)
			else:
				newChildren.append(c)
		self.children = newChildren
		QuerySpecification._processChildren(self)

	def getAllNames(self):
		return self.tableName.qName


@symbolAction("nojoinTableReference")
def dispatchTableReference(children):
	"""returns a TableReference or a QuerySpecification depending on
	wether children contain a querySpecification.
	"""
	for c in children:
		if getType(c)=='querySpecification':
			return AliasedQuerySpecification(children)
	else:
		return TableReference(children)


class FromClause(ADQLNode):
	type = "fromClause"
	def _processChildren(self):
		self.tablesReferenced = [t for t in self.children
			if hasattr(t, "colBearing")]
	
	def getTableNames(self):
		res = []
		for t in self.tablesReferenced:
			res.extend(t.getAllNames())
		return res


class ColumnReference(ADQLNode):
	type = "columnReference"
	cat = schema = table = name = None
	def _processChildren(self):
		self.colName = "".join(self.children)
		names = [c for c in self.children if c!="."]
		names = [None]*(4-len(names))+names
		self.cat, self.schema, self.table, self.name = names


class SelectList(ADQLNode):
	type = "selectList"
	def _processChildren(self):
		self.colRefs = self.getChildrenOfType("columnReference")
	
	def getColRefs(self):
		return self.colRefs


_grammarCache = None

def getADQLGrammar():
	"""returns a pyparsing symbol that can parse ADQL expressions into
	simple trees of ADQLNodes.

	This symbol is shared, so don't change anything on it.
	"""
# To do the bindings, we iterate over all children classes derived
# from ADQLNode (but not ADQLNode itself and first check for a bindings
# attribute and then their type attribute.  These are then used to
# add actions to the corresponding symbols.
	global _grammarCache
	if _grammarCache:
		return _grammarCache
	syms, root = adql.getADQLGrammarCopy()

	def bind(symName, nodeClass):
		syms[symName].setParseAction(lambda s, pos, toks: nodeClass(toks))

	for ob in globals().itervalues():
		if isinstance(ob, type) and issubclass(ob, ADQLNode) and ob is not ADQLNode:
			for binding in getattr(ob, "bindings", [ob.type]):
				bind(binding, ob)
		if hasattr(ob, "parseActionFor"):
			for sym in ob.parseActionFor:
				bind(sym, ob)
	return root


class ColsInfo(object):
	"""is a container for information about the columns and the subtables
	of a table.

	It consists of the following attributes:
	
	* seq -- a sequence of attributes of the columns in the
	  order in which they are selected (this is random if the table comes
	  from the db)
	* columns -- maps column names to attributes or None if a column
	  name is not unique.
	* subTables -- maps table names of subtables to their nodes (that in
	  turn have subTables if they already have been visited by the 
	  ColumnResolver)
	"""
	def __init__(self, node, fieldInfoGetter):
		self.seq, self.columns, self.subTables = [], {}, {}
		self._findRefdTables(node)
		if hasattr(node, "originalTable"): # reference to physical table
			self._addInfosForPhysTable(node, fieldInfoGetter)
		for child in getattr(node, "joinedTables", []):
			self._addInfosFromJoined(child)
		if hasattr(node, "query"): # subquery
			self._addInfosForQuery(node.query)

	def addColumn(self, label, info):
		"""adds a new visible column to this info.

		This entails both entering it in self.columns and in self.seq.
		"""
		if label in self.columns:
			self.columns[label] = None # Sentinel for ambiguous names
		else:
			self.columns[label] = info
		self.seq.append((label, info))

	def _addInfosForPhysTable(self, node, fieldInfoGetter):
		qName = node.originalTable.qName
		for label, info in fieldInfoGetter(qName).iteritems():
			self.addColumn(label, info) # WARNING: Order random here.

	def _addInfosForQuery(self, queryNode):
		# self is going to become the colsInfo for this query node.
		for colRef in queryNode.selectList.getColRefs():
			self.addColumn(colRef, 
				self.resolveFieldReference(colRef))

	def _addInfosFromJoined(self, node):
		for jt in getattr(node, "joinedTables", ()):
			for label, info in jt.colsInfo.iteritems():
				self.addColumn(label, info)

	def _findRefdTables(self, node):
		"""fills out the subTables attribute with any tables visible from node.
		"""
		if hasattr(node, "fromClause"):
			for subRef in node.fromClause.tablesReferenced:
				if hasattr(subRef, "colsInfo"):
					self.subTables[subRef.tableName.name] = subRef

	def _resolveNameInSubtables(self, colName):
		"""tries to locate colName in one of the node's referenced tables.

		To do that, it collects all fields of this names in subTables and
		returns the matching field if there's exactly one.  Otherwise, it
		will raise ColumnNotFound or AmbiguousColumn.
		"""
		matched = []
		for t in self.subTables.values():
			subCols = t.colsInfo.columns
			if colName in subCols and subCols[colName]:
				matched.append(subCols[colName])
		if len(matched)==1:
			return matched[0]
		elif not matched:
			raise ColumnNotFound(colName)
		else:
			raise AmbiguousColumn(colName)

	def resolveFieldReference(self, colRef):
		"""returns the fieldDef for a ColumnReference or a plain name from 
		this query.

		The function may raise ColumnNotFound or AmbiguousColumn exceptions.
		"""
# XXX TODO: check for schema, catalog?
		if isinstance(colRef, basestring):
			return self.columns[colRef]
		if colRef.table:
			return self.subTables[colRef.table].colsInfo.resolveFieldReference(
				colRef.name)
		if colRef.name in self.columns:
			return self.columns[colRef.name]
		return self._resolveNameInSubtables(colRef.name)

class ColumnResolver(object):
	"""is a container for collecting and gathering column information.

	It is constructed with fieldInfoGetter is a function taking a
	table name and returning a dictionary mapping column names to
	objects meaningful to the application.

	Its addColsInfo method will furnish its argument (which must
	be a colBearing node) with a colsInfo attribute.  Behind this
	is a ColsInfo object.  They will futher baptize "nameless"
	querySpecifications if necessary.
	"""
	def __init__(self, fieldInfoGetter):
		self.fieldInfoGetter = fieldInfoGetter

	def _baptizeNode(self, node):
		"""provides a tree-unique artificial name for the column bearing node.
		"""
		if hasattr(node, "tableName"):
			return
		name = "vtable%s"%id(node)
		node.tableName = TableName([SSubquery, ".", name])

	def addColsInfo(self, colBearingNode):
		"""adds the field definitions provided by colBearingNode to self.
		"""
		if not hasattr(colBearingNode, "tableName"):
			self._baptizeNode(colBearingNode)
		colBearingNode.colsInfo = ColsInfo(colBearingNode, self.fieldInfoGetter)


def makeFieldDefs(qTree, fieldInfoGetter):
	"""adds field definitions to the parsed query tree qTree.

	For the fieldInfoGetter argument, see ColumnResolver.
	"""
	colRes = ColumnResolver(fieldInfoGetter)
	def traverse(node):
		for child in node:
			if isinstance(child, ADQLNode):
				traverse(child)
		if hasattr(node, "colBearing"):
			colRes.addColsInfo(node)
	traverse(qTree)
	return colRes


class FieldInfo(object):
	"""is a container for everything that is known about a field at parse
	time.

	The user constructs it with a "token" that is opaque to the library
	and can later retrieve either an expression showing how an output
	column is generated from input columns (the tokens passed in) or
	simple the tokens that went into the field info.
	"""
	def __init__(self, token):
		self.tokens = (token)
		self.expression = (token)
	
	def getUsedTokens(token):
		return self.tokens


if __name__=="__main__":
	import pprint
	def fig(tableName):
		if tableName=="z":
			return {"a": "cm", "b": "km", "c": "arcsec/yr"}
		elif tableName=="y":
			return {"ya": "foot", "yb": "furlong", "yc": "inch"}
		else:
			return {}
	g = getADQLGrammar()
	res = g.parseString("select * from (select * from z) as q, a")[0]
#	pprint.pprint(res.asTree())
	print repr(res)
	fd = makeFieldDefs(res, fig)
	#print "Res:", res.colsInfo.seq
	print res.getSourceTableNames()
