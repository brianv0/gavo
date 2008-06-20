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


class _VirtualC(type):
	def __nonzero__(self):
		return False # don't include Virtual in qName calculations

class SSubquery(object):
	"""is a sentinel pseudo-schema for a table not in the db.
	"""
	__metaclass__ = _VirtualC


def symbolAction(symbol):
	"""is a decorator to mark functions as being a parseAction for symbol.

	This is evaluated by getADQLGrammar below.  Be careful not to alter
	global state in such a handler.
	"""
	def deco(func):
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
	is given, this is whatever is behind AS.

	They may have an originalName if an actual table name (as opposed to a
	subquery) was used to specify the table.  Otherwise, there's either
	a subquery or a joined table that needs to be consulted to figure out
	what fields are available from the table.
	"""
	type = "tableReference"
	bindings = []  # will be created by makeTableReference
	colBearing = None
	def __repr__(self):
		return "<tableReference to %s>"%self.tableName

	def _processChildren(self):
		try:
			res = self.getChildOfType("correlationSpecification")
			self.tableName = res
			self.originalTable = self.getChildOfType("tableName")
		except KeyError:
			self.tableName = self.originalTable = self.getChildOfType("tableName")


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

	def resolveFieldReference(self, colRef):
		"""returns the fieldDef for a ColumnReference or a plain name from 
		this query.

		The object must have been processed with a ColumnResolver before
		this works.
		"""
# XXX TODO: check for schema, catalog?
		if isinstance(colRef, basestring):
			return self._columns[colRef]
		if colRef.table:
			return self._subTables[colRef.table].resolveFieldReference(
				colRef.name)
		return self._columns[colRef.name]


class AliasedQuerySpecification(QuerySpecification):
	"""is a QuerySpecification with a correlationSpecification.
	"""
	bindings = [] # will be created by makeTableReference
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

@symbolAction("tableReference")
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
		self.tablesReferenced = [c 
			for c in self.children if hasattr(c, "tableName")]
	
	def getTableNames(self):
		return [t.tableName.qName for t in self.tablesReferenced]


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


class ColumnResolver(object):
	"""is a container for collecting and gathering column information.

	It is constructed with fieldInfoGetter is a function taking a
	table name and returning a dictionary mapping column names to
	objects meaningful to the application.
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

	def _addFieldInfosReal(self, colBearingNode):
		"""returns a fieldInfos dictionary for real tables.
		"""
		qName = colBearingNode.originalTable.qName
		colBearingNode._columns = self.fieldInfoGetter(qName)

	def _addFieldInfosSubquery(self, subqueryNode):
		self._baptizeNode(subqueryNode)

		def getSubtableInfo(subqueryNode):
			subTables, columns = {}, {}
			print subqueryNode.fromClause
			for fs in subqueryNode.fromClause:
				if not hasattr(fs, "tableName"):
					continue
				subTables[fs.tableName.name] = fs
				for label, info in fs._columns.iteritems():
					if label in columns:
						columns[label] = None # Sentinel for ambiguous names
					else:
						columns[label] = info
			return subTables, columns
	
		def getColSeq(subqueryNode):
			cols = []
			for colRef in subqueryNode.selectList.getColRefs():
				cols.append((colRef, subqueryNode.resolveFieldReference(colRef)))
			return cols

		subqueryNode._subTables, subqueryNode._columns = getSubtableInfo(
			subqueryNode)
		subqueryNode.columnSequence = getColSeq(subqueryNode)

	def addFieldDefs(self, colBearingNode):
		"""adds the field definitions provided by colBearingNode to self.
		"""
		if not hasattr(colBearingNode, "tableName"):
			self._baptizeNode(colBearingNode)
		tableName = colBearingNode.tableName
		if getType(colBearingNode)=="querySpecification":
			self._addFieldInfosSubquery(colBearingNode.query)
		else:
			self._addFieldInfosReal(colBearingNode)


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
			colRes.addFieldDefs(node)
	traverse(qTree)
	return colRes


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
	res = g.parseString("select a,b,v.ya from z, (select ya from y) as v")[0]
#	pprint.pprint(res.asTree())
#	print repr(res)
	fd = makeFieldDefs(res, fig)
