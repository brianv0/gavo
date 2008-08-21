"""
Trees of ADQL expressions and operations on them.

In general, I've tried to keep as much in plain strings as possible to
avoid having gargantuous trees when we're really only interested in
rather few "hot spots".

On the downside, this means I have to check literals quite liberally.
"""

import sys
import traceback
import weakref

import grammar
from gavo import unitconv


class Error(Exception):
	pass

class ColumnNotFound(Error):
	"""will be raised if a column name cannot be resolved.
	"""

class AmbiguousColumn(Error):
	"""will be raised if a column name matches more than one column in a
	compound query.
	"""

class NoChild(Error):
	"""will be raised if a node is asked for a non-existing child.
	"""

class MoreThanOneChild(Error):
	"""will be raised if a node is asked for a unique child but has more than
	one."""


class Absent(object):
	"""is a sentinel to pass as default to getChildOfType.
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
	type = None

	def __init__(self, children):
		self.children = children
		try:
			self._processChildren()
		except:
			sys.stderr.write("Panic: exception in processChildren of %s."
				"  Parse will be hosed."%self.__class__.__name__)
			traceback.print_exc()

	def __iter__(self):
		return iter(self.children)

	def __repr__(self):
		return "<%s, %s>"%(self.type, self.children)

	def _processChildren(self):
		pass

	def getChildrenOfType(self, type):
		return [c for c in self if getType(c)==type]
	
	def getChildOfType(self, type, default=None):
		res = self.getChildrenOfType(type)
		if len(res)==0:
			if default is not None: 
				return default
			raise NoChild(type)
		if len(res)!=1:
			raise MoreThanOneChild(type)
		return res[0]

	def flatten(self):
		"""returns a string representation of the text content of the tree.
		"""
		return " ".join([flatten(c) for c in self])

	def getFlattenedChildren(self):
		"""returns a list of all preterminal children of all children of self.

		A child is preterminal if it has string content.
		"""
		fl = [c for c in self.children if isinstance(c, basestring)]
		def recurse(node):
			for c in node.children:
				if isinstance(c, ADQLNode):
					if c.isPreterminal():
						fl.append(c)
					recurse(c)
		recurse(self)
		return fl

	def isPreterminal(self):
		return bool(self.getChildrenOfType(str))

	def asTree(self):
		return tuple(isinstance(c, ADQLNode) and c.asTree() or c
			for c in self)


class FieldInfoedNode(ADQLNode):
	"""is an ADQL node that carries a FieldInfo.

	This is true for basically everything in the tree below a derived
	column.

	You'll usually have to override makeFieldInfo.  The default implementation
	just looks in its immediate children for anything having a fieldInfo,
	and if there's exactly one such child, it adopts that fieldInfo as
	its own, not changing anything.
	"""
	fieldInfo = None

	def _getInfoChildren(self):
		return [c for c in self.children if getattr(c, "fieldInfo", None)]

	def makeFieldInfo(self, colsInfo):
		infoChildren = self._getInfoChildren()
		if len(infoChildren)==1:
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			raise Error("More than one or no child with fieldInfo with"
				" no behaviour defined in %s"%(self.__class__.__name__))


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
		fi = self.columns.get(colName, Absent)
		if fi is Absent:
			raise ColumnNotFound(fieldName)
		return fi


def getUniqueMatch(matches, colName):
		if len(matches)==1:
			return matches[0]
		elif not matches:
			raise ColumnNotFound(colName)
		else:
			raise AmbiguousColumn(colName)


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
		return getUniqueMatch(matches, colName)
	

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
	

class ColBearingMixin(object):
	"""is a mixin for all Node types that provides columns with field infos.

	It is mixed in by queries, tables, etc.
	"""
	fieldInfos = None

	def getFieldInfo(self, name):
		if self.fieldInfos:
			return self.fieldInfos.getFieldInfo(name)



############# Toplevel query language node types (for query analysis)

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
	

class TableReference(ADQLNode, ColBearingMixin):
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
	joinedTables = []
	def __repr__(self):
		return "<tableReference to %s>"%",".join(self.getAllNames())

	def _processChildren(self):
		alias = self.getChildOfType("correlationSpecification", Absent)
		if alias is Absent:
			self.tableName = self.originalTable = self.getChildOfType("tableName")
		else:
			self.tableName = alias
			self.originalTable = self.getChildOfType("tableName")
		self.joinedTables = self.getChildrenOfType("tableReference")

	def getAllNames(self):
		yield self.tableName.qName
		for t in self.joinedTables:
			yield t.tableName.qName


class QuerySpecification(ADQLNode, ColBearingMixin): 
	type = "querySpecification"
	def _processChildren(self):
		self.selectList = self.getChildOfType("selectList")
		self.fromClause = self.getChildOfType("fromClause")
		self.query = weakref.proxy(self)
	
	def getSelectList(self):
		return [c.name for c in self.selectList.selectFields]

	def getSelectFields(self):
		return self.selectList.selectFields

	def getSourceTableNames(self):
		return self.fromClause.getTableNames()
	
	def resolveField(self, fieldName):
		return self.fromClause.resolveField(fieldName)


class AliasedQuerySpecification(QuerySpecification):
	"""is a QuerySpecification with a correlationSpecification.
	"""
	bindings = [] # will be created by dispatchTableReference
	def _processChildren(self):
		try:
			self.tableName = self.getChildOfType("correlationSpecification")
		except NoChild:  # shouldn't happen, but doesn't hurt
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
			if isinstance(t, ColBearingMixin)]
		self._fieldCache = {}
	
	def getTableNames(self):
		res = []
		for t in self.tablesReferenced:
			res.extend(t.getAllNames())
		return res
	
	def resolveField(self, name):
		matches = []
		if not name in self._fieldCache:
			for t in self.tablesReferenced:
				try:
					matches.append(t.fieldInfos.getFieldInfo(name))
				except ColumnNotFound:
					pass
		return getUniqueMatch(matches, name)

	
class ColumnReference(FieldInfoedNode):
	type = "columnReference"
	cat = schema = table = name = None
	def _processChildren(self):
		self.colName = "".join(self.children)
		names = [c for c in self.children if c!="."]
		names = [None]*(4-len(names))+names
		self.cat, self.schema, self.table, self.name = names

	def makeFieldInfo(self, colBearing):
		self.fieldInfo = colBearing.resolveField(self.name)


class AsClause(ADQLNode):
	type = "asClause"
	alias = None

	def _processChildren(self):
		self.alias = self.children[-1]


class DerivedColumn(FieldInfoedNode):
	"""is a column within a select list.

	DerivedColumns have the following attributes for the client's
	convenience:

	* name -- if there's an asClause, it's the alias; if the only
	  child is a ColumnReference, it's its name; otherwise, its an
	  artificial name.
	* columnReferences -- a list of all columnReferences below the expression
	* tainted -- true if there is any content in the expression that cannot
    be safely interpreted in terms of the unit and ucd calculus.  This
	  is true by default whenever there's more than a single columnReference
	  and needs to be reset by things like ColumnResolver.
	"""
	type = "derivedColumn"
	name = None
	columnReferences = None
	tainted = True

	def _processChildren(self):
		fc = [f for f in self.getFlattenedChildren() if getType(f)!="asClause"]
		# typical case: We only have a single column.  Inherit its name
		if len(fc)==1 and getType(fc[0])=="columnReference":
			self.name = fc[0].name
			self.tainted = False
		else:  # come up with an artificial name
			self.name = "column-%x"%(id(self)+0x80000000)
		alias = self.getChildOfType("asClause", Absent)
		if alias is not Absent:
			self.name = alias.alias
		self.columnReferences = [c for c in fc if getType(c)=="columnReference"]


class SelectList(ADQLNode):
	type = "selectList"
	def _processChildren(self):
		self.selectFields = self.getChildrenOfType("derivedColumn")
	

######## all expression parts we need to consider when inferring units and such

class CombiningFINode(FieldInfoedNode):
	def makeFieldInfo(self, colsInfo):
		infoChildren = self._getInfoChildren()
		if not infoChildren:
			self.fieldInfo = scalarFieldInfo
		elif len(infoChildren)==1:
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			self.fieldInfo = self._combineFieldInfos()


class Term(CombiningFINode):
	type = "term"

	def _getMulFieldInfo(fi1, fi2):
		return FieldInfo(fi1.unit+" "+fi2.unit, "", (fi1, fi2))
	
	def _getDivFieldInfo(fi1, fi2):
		return FieldInfo(fi1.unit+"/"+fi2.unit, "", (fi1, fi2))

	def _combineFieldInfos(self):
# These are either multiplication or division
		toDo = self.children[:]
		opd1, opr = toDo[:2]
		toDo = toDo[2:]
		fi1 = opd1.fieldInfo
		while toDo:
			fi2 = toDo.pop(0).fieldInfo
			if opr=="*":
				self._getMulFieldInfo(fi1, fi2)
			elif opr=="/":
				self._getDivFieldInfo(fi1, fi2)
			else:
				raise Error("Invalid multiplicative operator: %s"%opr)
			opr = toDo.pop(0)
		return fi1


class NumericValueExpression(CombiningFINode):
	type = "numericValueExpression"
	def _combineFieldInfos(self):
# These are either addition or subtraction
		toDo = self.children[:]
		fi1 = toDo.pop(0).fieldInfo
		while toDo:
			opr = toDo.pop(0)
			fi2 = toDo.pop(0).fieldInfo
			unit, ucd = "", ""
			if fi1.unit==fi2.unit:
				unit = fi1.unit
			if fi1.ucd==fi2.ucd:
				ucd = fi1.ucd
			fi1 = FieldInfo(unit, ucd, (fi1, fi2))
		return fi1


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
	syms, root = grammar.getADQLGrammarCopy()

	def bind(symName, nodeClass):
		try:
			syms[symName].setParseAction(lambda s, pos, toks: nodeClass(toks))
		except KeyError:
			raise KeyError("%s asks for non-existing symbol %s"%(
				nodeClass.__name__ , symName))

	for ob in globals().itervalues():
		if isinstance(ob, type) and issubclass(ob, ADQLNode):
			for binding in getattr(ob, "bindings", [ob.type]):
				if binding:
					bind(binding, ob)
		if hasattr(ob, "parseActionFor"):
			for sym in ob.parseActionFor:
				bind(sym, ob)
	return root



def _resolveColumns(qTree):
	"""attaches fieldInfo and fieldInfos a column bearing node.

	This includes queries and subqueries.  It will also baptize those
	if they are anyonomyous.
	"""
	def baptizeNode(self, node):
		"""provides a tree-unique artificial name for the column bearing node.
		"""
		name = "vtable%s"%(id(node)+0x80000000)
		node.tableName = TableName([SSubquery, ".", name])

		if not hasattr(colBearingNode, "tableName"):
			self.baptizeNode(colBearingNode)
		colBearingNode.fieldInfos = FieldInfos(colBearingNode)


def attachFieldInfosToTables(node, fieldInfoGetter):
	"""adds fieldInfos attributes mapping column names within the table
	to fieldInfos for all tableReferences.
	"""
	for c in node:
		if isinstance(c, ADQLNode):
			attachFieldInfosToTables(c, fieldInfoGetter)
	if node.type=="tableReference":
		node.fieldInfos = FieldInfosForTable(node, fieldInfoGetter)


def makeFieldInfo(qTree, fieldInfoGetter):
	"""adds field definitions to the parsed query tree qTree.

	For the fieldInfoGetter argument, see ColumnResolver.
	The result of this is that each column bearing node in qTree gets
	a colsInfo attribute.  See ColumnResolver.
	"""
	attachFieldInfosToTables(qTree, fieldInfoGetter)
	def traverse(node, table):
		if hasattr(node, "resolveField"):
			table = node
		for child in node:
			if isinstance(child, ADQLNode):
				traverse(child, table)
		if node.type=="querySpecification":
			node.fieldInfos = FieldInfosForQuery(node)
		if hasattr(node, "fieldInfo"):
			node.makeFieldInfo(table)
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


scalarFieldInfo = FieldInfo("", "", None)


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
	fd = makeFieldInfos(res, fig)
	#print "Res:", res.colsInfo.seq
	print res.getSourceTableNames()
