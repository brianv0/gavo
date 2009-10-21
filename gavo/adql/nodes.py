"""
Node classes and factories used in ADQL tree processing.
"""

import itertools
import pyparsing
import sys
import traceback
import weakref

from gavo import utils
from gavo.adql.common import *


################ Various helpers

class Absent(object):
	"""is a sentinel to pass as default to getChildOfType.
	"""


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
		func.fromParseResult = func
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
	elif isinstance(arg, pyparsing.ParseResults):
		return " ".join(flatten(c) for c in arg)
	else:
		return arg.flatten()


def autocollapse(nodeBuilder, children):
	"""inhibts the construction via nodeBuilder if children consists of
	a single ADQLNode.

	This function will automatically be inserted into the the constructor
	chain if the node defines an attribute collapsible=True.
	"""
	if len(children)==1 and isinstance(children[0], ADQLNode):
		return children[0]
	return nodeBuilder.fromParseResult(children)


def collectUserData(infoChildren):
	userData, tainted = (), False
	for c in infoChildren:
		userData = userData+c.fieldInfo.userData
		tainted = tainted or c.fieldInfo.tainted
	return userData, tainted


def flattenKWs(obj, *fmtTuples):
	"""returns a string built from the obj according to format tuples.

	A format tuple is consists of a literal string, and
	an attribute name.  If the corresponding attribute is
	non-None, the plain string and the flattened attribute
	value are inserted into the result string, otherwise
	both are ignored.

	Nonexisting attributes are taken to have None values.

	To allow unconditional literals, the attribute name can
	be None.  The corresponding literal is always inserted.

	All contributions are separated by single blanks.

	This is a helper method for flatten methods of parsed-out
	elements.
	"""
	res = []
	for literal, attName in fmtTuples:
		if attName is None:
			res.append(literal)
		else:
			if getattr(obj, attName, None) is not None:
				if literal:
					res.append(literal)
				res.append(flatten(getattr(obj, attName)))
	return " ".join(res)


def cleanNamespace(ns):
	"""removes all names starting with an underscore from the dict ns.

	This is intended for _getInitKWs methods.  ns is changed in place *and*
	returned for convenience
	"""
	return dict((k,v) for k,v in ns.iteritems() if not k.startswith("_")
		and k!="cls")


def getChildrenOfType(nodeSeq, type):
	"""returns a list of children of type typ in the sequence nodeSeq.
	"""
	return [c for c in nodeSeq if getType(c)==type]


def getChildrenOfClass(nodeSeq, cls):
	return [c for c in nodeSeq if isinstance(c, cls)]


class BOMB_OUT(object): pass

def _uniquify(matches, default, exArgs):
# helper method for getChildOfX -- see there
	if len(matches)==0:
		if default is not BOMB_OUT: 
			return default
		raise NoChild(*exArgs)
	if len(matches)!=1:
		raise MoreThanOneChild(*exArgs)
	return matches[0]

def getChildOfType(nodeSeq, type, default=BOMB_OUT):
	"""returns the unique node of type in nodeSeq.

	If there is no such node in nodeSeq or more than one, a NoChild or
	MoreThanOneChild exception is raised,  Instead of raising NoChild,
	default is returned if given.
	"""
	return _uniquify(getChildrenOfType(nodeSeq, type),
		default, (type, nodeSeq))


def getChildOfClass(nodeSeq, cls, default=BOMB_OUT):
	"""returns the unique node of class in nodeSeq.

	See getChildOfType.
	"""
	return _uniquify(getChildrenOfClass(nodeSeq, cls),
		default, (cls, nodeSeq))


######################### Generic Node definitions

@symbolAction("regularIdentifier")
def normalizeRIdentifier(toks):
	"""returns toks[0] in lowercase.
	"""
	assert len(toks)==1
	return toks[0].lower()


class ADQLNode(utils.AutoNode):
	"""A node within an ADQL parse tree.

	ADQL nodes may be parsed out; in that case, they have individual attributes
	and are craftily flattened in special methods.  We do this for nodes
	that are morphed.

	Other nodes basically just have a children attribute, and their flattening
	is just a concatenation for their flattened children.  This is convenient
	as long as they are not morphed.
	
	To derive actual classes, define 
	
	* the _a_<name> class attributes you need,
	* the type (a nonterminal from the ADQL grammar) 
	* or bindings if the class handles more than one symbol,
	* a class method _getInitKWs(cls, parseResult); see below.
	* a method flatten() -> string if you define a parsed ADQLNode.
	* a method _polish() that is called just before the constructor is
	  done and can be used to create more attributes.  There is no need
	  to call _polish of superclasses.

	The _getInitKWs methods must return a dictionary mapping constructor argument
	names to values.  You do not need to manually call superclass _getInitKWs,
	since the fromParseResult classmethod figures out all _getInitKWs in the
	inheritance tree itself.  It calls all of them in the normal MRO and updates
	the argument dictionary in reverse order.  The fromParseResult
	class method additionally filters out all names starting with an
	underscore; this is to allow easy returning of locals().
	"""
	type = None

	@classmethod
	def fromParseResult(cls, parseResult):
		initArgs = {}
		for superclass in reversed(cls.mro()):
			if hasattr(superclass, "_getInitKWs"):
				initArgs.update(superclass._getInitKWs( parseResult))
		try:
			return cls(**cleanNamespace(initArgs))
		except TypeError:
			raise BadKeywords("%s, %s"%(cls, cleanNamespace(initArgs)))

	def _setupNode(self):
		for cls in reversed(self.__class__.mro()):
			if hasattr(cls, "_polish"):
				cls._polish(self)
		self._setupNodeNext(ADQLNode)

	def __repr__(self):
		return "<ADQL Node %s>"%(self.type)

	def flatten(self):
		"""returns a string representation of the text content of the tree.

		This default implementation will only work if you returned all parsed
		elements as children.  This, in turn, is something you only want to
		do if you are sure that the node is question will not be morphed.

		Otherwise, override it to create an SQL fragment out of the parsed
		attributes.
		"""
		return " ".join(flatten(c) for c in self.children)

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

	def asTree(self):
		res = []
		for name, val in self.iterChildren():
			if isinstance(val, ADQLNode):
				res.append(val.asTree())
		return self._treeRepr()+tuple(res)
	
	def _treeRepr(self):
		return (self.type,)
	

class TransparentMixin(object):
	"""a mixin just pulling through the children and serializing them.
	"""
	_a_children = ()

	@classmethod
	def _getInitKWs(cls, _parseResult):
		return {"children": list(_parseResult)}


class FunctionMixin(object):
	"""is a mixin for ADQLNodes for parsing out arguments and a
	function name.

	The rules having this as action must use the Arg "decorator" in
	grammar.py around their arguments and must have a string-valued
	result "fName".

	Nodes mixing this in have attributes args (unflattened arguments),
	and funName (a string containing the function name, all upper
	case).
	"""
	_a_args = ()
	_a_funName = None

	@classmethod
	def _getInitKWs(cls, _parseResult):
		args = []
		try:
			for _arg in _parseResult["args"]:
				# _arg is either another ParseResult or an ADQLNode
				if isinstance(_arg, ADQLNode):
					args.append(_arg)
				else:
					args.append(autocollapse(NumericValueExpression, _arg))
			args = tuple(args)
		except KeyError: # Zero-Arg function
			pass
		funName = _parseResult["fName"].upper()
		return locals()

	def flatten(self):
		return "%s(%s)"%(self.funName, ", ".join(flatten(a) for a in self.args))


class FieldInfoedNode(ADQLNode):
	"""is an ADQL node that carries a FieldInfo.

	This is true for basically everything in the tree below a derived
	column.  This class is the basis for column annotation.

	You'll usually have to override addFieldInfo.  The default implementation
	just looks in its immediate children for anything having a fieldInfo,
	and if there's exactly one such child, it adopts that fieldInfo as
	its own, not changing anything.

	FieldInfoedNode, when change()d, keep their field info.  This is usually
	what you want when morphing, but sometimes you might need adjustments.
	"""
	fieldInfo = None

	def _getInfoChildren(self):
		return [c for c in self.iterNodeChildren() if hasattr(c, "fieldInfo")]

	def addFieldInfo(self, ignored):
		infoChildren = self._getInfoChildren()
		if len(infoChildren)==1:
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			if len(infoChildren):
				msg = "More than one"
			else:
				msg = "No"
			raise Error("%s child with fieldInfo with"
				" no behaviour defined in %s, children %s"%(
					msg,
					self.__class__.__name__,
					self.children))

	def change(self, **kwargs):
		other = ADQLNode.change(self, **kwargs)
		other.fieldInfo = self.fieldInfo
		return other


class ColumnBearingNode(ADQLNode):
	"""A Node types defining selectable columns.

	These are tables, subqueries, etc.  This class is the basis for the
	annotation of tables and subqueries.

	Their getFieldInfo(name)->fi method gives annotation.FieldInfos 
	objects for their columns, None for unknown columns.

	These keep their fieldInfos on a change()
	"""
	fieldInfos = None

	def getFieldInfo(self, name):
		if self.fieldInfos:
			return self.fieldInfos.getFieldInfo(name)
	
	def getAllNames(self):
		"""yields all relation names mentioned in this node.
		"""
		raise TypeError("Override getAllNames for ColumnBearingNodes.")

	def change(self, **kwargs):
		other = ADQLNode.change(self, **kwargs)
		other.fieldInfos = self.fieldInfos
		return other


############# Toplevel query language node types (for query analysis)

class TableName(ADQLNode):
	type = "tableName"
	_a_cat = None
	_a_schema = None
	_a_name = None

	def _polish(self):
		self.qName = ".".join(n for n in (self.cat, self.schema, self.name) if n)

	@classmethod
	def _getInitKWs(cls, _parseResult):
		_parts = _parseResult[::2]
		cat, schema, name = [None]*(3-len(_parts))+_parts
		return locals()

	def flatten(self):
		return self.qName


class PlainTableRef(ColumnBearingNode):
	"""A reference to a simple table.
	
	The tableName is the name this table can be referenced as from within
	SQL, originalName is the name within the database; they are equal unless
	a correlationSpecification has been given.
	"""
	type = "possiblyAliasedTable"
	feedInfosFromDB = True
	_a_tableName = None
	_a_originalTable = None

	@classmethod
	def _getInitKWs(cls, _parseResult):
		if _parseResult.get("alias"):
			tableName = _parseResult.get("alias")
			originalTable = _parseResult.get("tableName")
		else:
			tableName = getChildOfType(_parseResult, "tableName")
			originalTable = flatten(tableName)
		return locals()

	def _polish(self):
		self.qName = flatten(self.tableName)

	def flatten(self):
		if self.originalTable!=self.qName:
			return "%s AS %s"%(flatten(self.tableName), self.originalTable)
		else:
			return self.qName

	def getAllNames(self):
		yield self.tableName.qName


class DerivedTable(ADQLNode):
	type = "derivedTable"
	_a_query = None
	_a_tableName = None

# These just delegate all column bearing stuff to their embedded query
	def getAllNames(self):
		return self.query.getAllNames()
	def getFieldInfo(self, name):
		return self.query.getFieldInfo(name)
	@property
	def fieldInfos(self):
		return self.query.fieldInfos

	@classmethod
	def _getInitKWs(cls, _parseResult):
		return {'tableName': TableName(name=str(_parseResult.get("alias"))),
			'query': getChildOfClass(_parseResult, QuerySpecification),
		}

	def flatten(self):
		return "(%s) AS %s"%(flatten(self.query), flatten(self.tableName))

	def getAllNames(self):
		yield self.tableName.qName


class JoinedTable(ColumnBearingNode, TransparentMixin):
	type = "joinedTable"
	feedInfosFromDB = True

	def _polish(self):
		self.joinedTables = getChildrenOfClass(self.children, ColumnBearingNode)

	def getAllNames(self):
		"""iterates over all fully qualified table names mentioned in this
		(possibly joined) table reference.
		"""
		for t in self.joinedTables:
			yield t.tableName.qName


class TransparentNode(TransparentMixin, ADQLNode):
	"""An abstract base for Nodes that don't parse out anything.
	"""
	type = None


class WhereClause(TransparentNode):
	type = "whereClause"

class Grouping(TransparentNode):
	type = "groupByClause"

class Having(TransparentNode):
	type = "havingClause"

class OrderBy(TransparentNode):
	type = "sortSpecification"


class QuerySpecification(ColumnBearingNode): 
	type = "querySpecification"

	_a_setQuantifier = None
	_a_setLimit = None
	_a_selectList = None
	_a_fromClause = None
	_a_whereClause = None
	_a_groupby = None
	_a_having = None
	_a_orderBy = None

	def _polish(self):
		self.query = weakref.proxy(self)

	@classmethod
	def _getInitKWs(cls, _parseResult):
		res = {}
		for name in ["setQuantifier", "setLimit", "fromClause",
				"whereClause", "groupby", "having", "orderBy"]:
			res[name] = _parseResult.get(name)
		res["selectList"] = getChildOfType(_parseResult, "selectList")
		return res
	
	def getSelectFields(self):
		if self.selectList.allFieldsQuery:
			return self.fromClause.getAllFields()
		else:
			return self.selectList.selectFields

	def resolveField(self, fieldName):
		return self.fromClause.resolveField(fieldName)

	def getAllNames(self):
		return self.fromClause.getAllNames()

	def flatten(self):
		return flattenKWs(self, ("SELECT", None),
			("", "setQuantifier"),
			("TOP", "setLimit"),
			("", "selectList"),
			("", "fromClause"),
			("", "whereClause"),
			("", "groupby"),
			("", "having"),
			("", "orderBy"),)


class FromClause(ADQLNode):
	type = "fromClause"
	_a_tablesReferenced = ()

	@classmethod
	def _getInitKWs(cls, _parseResult):
		res = {"tablesReferenced": list(_parseResult)[1::2]}
		return res
	
	def flatten(self):
		return "FROM %s"%(", ".join(flatten(r) for r in self.tablesReferenced))
	
	def getAllNames(self):
		"""returns the names of all tables taking part in this from clause.
		"""
		return itertools.chain(*(t.getAllNames() for t in self.tablesReferenced))
	
	def resolveField(self, name):
		matches = []
# XXX TODO: implement matching rules for delimitedIdentifiers
		for t in self.tablesReferenced:
			try:
				matches.append(t.fieldInfos.getFieldInfo(name))
			except ColumnNotFound:
				pass
		return getUniqueMatch(matches, name)

	class FakeSelectField(object):
		"""A helper class to wrap columns into selectFields when resolving
		SELECT *...
		"""
		def __init__(self, name, fieldInfo):
			self.name, self.fieldInfo = name, fieldInfo

		def iterNodeChildren(self):
			return []

		def addFieldInfo(self, ignored):
			pass # we were born with one.

	def getAllFields(self):
		res = []
		for table in self.tablesReferenced:
			for column in table.fieldInfos.seq:
				res.append(self.FakeSelectField(*column))
		return res


class ColumnReference(FieldInfoedNode):
	type = "columnReference"
	_a_cat = None
	_a_schema = None
	_a_table = None
	_a_name = None

	def _polish(self):
		self.colName = "".join(n for n in 
			(self.cat, self.schema, self.table, self.name) if n)

	@classmethod
	def _getInitKWs(cls, _parseResult):
		_names = [_c for _c in _parseResult if _c!="."]
		_names = [None]*(4-len(_names))+_names
		cat, schema, table, name = _names
		return locals()

	def addFieldInfo(self, getFieldInfo):
		self.fieldInfo = getFieldInfo(self.name)
	
	def flatten(self):
		return self.colName

	def _treeRepr(self):
		return (self.type, self.name)


class DerivedColumn(FieldInfoedNode):
	"""A column within a select list.
	"""
	type = "derivedColumn"
	_a_expr = None
	_a_alias = None
	_a_tainted = True
	_a_name = None

	def _polish(self):
		if self.name is None:
			if getType(self.expr)=="columnReference":
				self.name = self.expr.name
			else:
				self.name = utils.intToFunnyWord(id(self))
		if getType(self.expr)=="columnReference":
			self.tainted = False

	@classmethod
	def _getInitKWs(cls, _parseResult):
		expr = _parseResult["expr"]
		alias = _parseResult.get("alias")
		if alias is not None:
			name = alias
		return locals()
	
	def flatten(self):
		return flattenKWs(self,
			("", "expr"),
			("AS", "alias"))

	def _treeRepr(self):
		return (self.type, self.name)

class SelectList(ADQLNode):
	type = "selectList"
	_a_selectFields = ()
	_a_allFieldsQuery = False

	@classmethod
	def _getInitKWs(cls, _parseResult):
		allFieldsQuery = _parseResult.get("starSel", False)
		if allFieldsQuery:
			selectFields = None  # Will be filled in by query, we don't have
			                     # the from clause here.
		else:
			selectFields = list(_parseResult.get("fieldSel"))
		return locals()
	
	def flatten(self):
		if self.allFieldsQuery:
			return self.allFieldsQuery
		else:
			return ", ".join(flatten(sf) for sf in self.selectFields)


######## all expression parts we need to consider when inferring units and such

class Comparison(ADQLNode):
	"""is required when we want to morph the braindead contains(...)=1 into
	a true boolean function call.
	"""
	type = "comparisonPredicate"
	_a_op1 = None
	_a_opr = None
	_a_op2 = None

	@classmethod
	def _getInitKWs(cls, _parseResult):
		op1, opr, op2 = _parseResult
		return locals()
	
	def flatten(self):
		return "%s %s %s"%(flatten(self.op1), self.opr, flatten(self.op2))


class Factor(FieldInfoedNode, TransparentMixin):
	"""is a factor within an SQL expression.

	factors may have only one (direct) child with a field info and copy
	this.  They can have no child with a field info, in which case they're
	dimless.
	"""
	type = "factor"
	collapsible = True

	def addFieldInfo(self, ignored):
		infoChildren = self._getInfoChildren()
		if infoChildren:
			assert len(infoChildren)==1
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			self.fieldInfo = dimlessFieldInfo


class CombiningFINode(FieldInfoedNode):
	def addFieldInfo(self, ignored):
		infoChildren = self._getInfoChildren()
		if not infoChildren:
			self.fieldInfo = dimlessFieldInfo
		elif len(infoChildren)==1:
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			self.fieldInfo = self._combineFieldInfos()


class Term(TransparentMixin, CombiningFINode):
	type = "term"
	collapsible = True

	def _combineFieldInfos(self):
# These are either multiplication or division
		toDo = self.children[:]
		opd1 = toDo.pop(0)
		fi1 = opd1.fieldInfo
		while toDo:
			opr = toDo.pop(0)
			fi1 = FieldInfo.fromMulExpression(opr, fi1, 
				toDo.pop(0).fieldInfo)
		return fi1


class NumericValueExpression(CombiningFINode, TransparentMixin):
	type = "numericValueExpression"
	collapsible = True

	def _combineFieldInfos(self):
# These are either addition or subtraction
		toDo = self.children[:]
		fi1 = toDo.pop(0).fieldInfo
		while toDo:
			opr = toDo.pop(0)
			fi1 = FieldInfo.fromAddExpression(opr, fi1, toDo.pop(0).fieldInfo)
		return fi1


class GenericValueExpression(CombiningFINode, TransparentMixin):
	"""is a container for value expressions that we don't want to look at
	closer.

	It is returned by the makeValueExpression factory below to collect
	stray children.
	"""
	def _combineFieldInfos(self):
		# we don't really know what these children are.  Let's just give up
		# unless all child fieldInfos are more or less equal (which of course
		# is a wild guess).
		childUnits, childUCDs = set(), set()
		infoChildren = self._getInfoChildren()
		for c in infoChildren:
			childUnits.add(c.fieldInfo.unit)
			childUCDs.add(c.fieldInfo.ucd)
		if len(childUnits)==1 and len(childUCDs)==1:
			# let's taint the first info and be done with it
			return infoChildren[0].fieldInfo.copyModified(tainted=True)
		else:
			return dimlessFieldInfo


@symbolAction("valueExpression")
def makeValueExpression(children):
	if len(children)!=1:
		res = GenericValueExpression.fromParseResult(children)
		res.type = "valueExpression"
		return res
	else:
		return children[0]


class CountAll(FieldInfoedNode, TransparentMixin):
	"""is a COUNT(*)-type node.
	"""
	type = "countAll"
	fieldInfo = FieldInfo("", "meta.number")

	# We could inspect parents to figure out *what* we're counting to come up
	# with a better UCD.
	def addFieldInfo(self, ignored):
		pass


class SetFunction(FieldInfoedNode, TransparentMixin):
	"""is an aggregate function.

	These typically amend the ucd by a word from the stat family and copy
	over the unit.  There are exceptions, however, see table in class def.
	"""
	type = "generalSetFunction"

	funcDefs = {
		'AVG': ('stat.mean', None),
		'MAX': ('stat.max', None),
		'MIN': ('stat.min', None),
		'SUM': (None, None),
		'COUNT': ('meta.number', ''),}

	def addFieldInfo(self, ignored):
		ucdPref, newUnit = self.funcDefs[self.children[0].upper()]
		infoChildren = self._getInfoChildren()
		if infoChildren:
			assert len(infoChildren)==1
			fi = infoChildren[0].fieldInfo
		else:
			fi = dimlessFieldInfo
		if ucdPref is None or fi.ucd=="":
			ucd = fi.ucd
		else:
			ucd = ucdPref+";"+fi.ucd
		if newUnit is None:
			unit = fi.unit
		else:
			unit = newUnit
		self.fieldInfo = FieldInfo(unit, ucd, fi.userData, fi.tainted)


class NumericValueFunction(FunctionMixin, FieldInfoedNode):
	"""is a numeric function.

	This is really a mixed bag.  We work through handlers here.  See table
	in class def.  Unknown functions result in dimlesses.
	"""
	type = "numericValueFunction"
	collapsible = True  # if it's a real function call, it has at least
		# a name, parens and an argument and thus won't be collapsed.

	funcDefs = {
		"ACOS": ('rad', '', None),
		"ASIN": ('rad', '', None),
		"ATAN": ('rad', '', None),
		"ATAN2": ('rad', '', None),
		"PI": ('', '', None),
		"RAND": ('', '', None),
		"EXP": ('', '', None),
		"LOG": ('', '', None),
		"LOG10": ('', '', None),
		"SQRT": ('', '', None),
		"SQUARE": ('', '', None),
		"POWER": ('', '', None),
		"ABS": (None, None, "keepMeta"),
		"CEILING": (None, None, "keepMeta"),
		"FLOOR": (None, None, "keepMeta"),
		"ROUND": (None, None, "keepMeta"),
		"TRUNCATE": (None, None, "keepMeta"),
		"DEGREES": ('deg', None, "keepMeta"),
		"RADIANS": ('rad', None, "keepMeta"),
	}

	def _handle_keepMeta(self, infoChildren):
		assert len(infoChildren)==1
		fi = infoChildren[0].fieldInfo
		return fi.unit, fi.ucd

	def addFieldInfo(self, ignored):
		infoChildren = self._getInfoChildren()
		unit, ucd = '', ''
		overrideUnit, overrideUCD, handlerName = self.funcDefs.get(
			self.funName, ('', '', None))
		if handlerName:
			unit, ucd = getattr(self, "_handle_"+handlerName)(infoChildren)
		if overrideUnit:
			unit = overrideUnit
		if overrideUCD:
			ucd = overrideUCD
		self.fieldInfo = FieldInfo(unit, ucd, *collectUserData(infoChildren))


class CharacterStringLiteral(FieldInfoedNode):
	"""according to the current grammar, these are always sequences of
	quoted strings.
	"""
	type = "characterStringLiteral"
	bindings = ["characterStringLiteral", "generalLiteral"]

	_a_value = None

	@classmethod
	def _getInitKWs(cls, _parseResult):
		value = "".join(c[1:-1] for c in _parseResult)
		return locals()

	def flatten(self):
		return "'%s'"%(self.value.replace("'", "\\'"))

	def addFieldInfo(self, ignored):
		self.fieldInfo = dimlessFieldInfo


###################### Geometry and stuff that needs morphing into real SQL

class CoosysMixin(object):
	"""is a mixin that works cooSys into FieldInfos for ADQL geometries.
	"""
	_a_cooSys = None

	def addFieldInfo(self, ignored):
		infoChildren = self._getInfoChildren()
		self.fieldInfo = FieldInfo("", "", collectUserData(infoChildren)[0])
		self.fieldInfo.cooSys = self.cooSys

	@classmethod
	def _getInitKWs(cls, _parseResult):
		return {"cooSys":  _parseResult["coordSys"][0].value}


class _FunctionalNode(FunctionMixin, FieldInfoedNode):
	pass


class Point(CoosysMixin, _FunctionalNode):
	"""points have cooSys, x, and y attributes.
	"""
	type = "point"
	_a_x = _a_y = None

	def _polish(self):
		self.x, self.y = self.args
	

class Circle(CoosysMixin, _FunctionalNode):
	"""circles have cooSys, x, y, and radius attributes.
	"""
	type = "circle"
	_a_x = _a_y = _a_radius = None

	def _polish(self):
		self.x, self.y, self.radius = self.args


class Rectangle(CoosysMixin, _FunctionalNode):
	"""rectangles have cooSys, x0, y0, x1, and y1 attributes.
	"""
	type = "rectangle"
	_a_x0 = _a_y0 = _a_x1 = _a_y1 = None

	def _polish(self):
		self.x0, self.y0, self.x1, self.y1 = self.args


class Polygon(CoosysMixin, _FunctionalNode):
	"""rectangles have a cooSys attribute, and store pairs of
	coordinates in coos.
	""" 
	type = "polygon"
	_a_coos = ()

	def _polish(self):
		toDo = list(self.args)
		coos = []
		while toDo:
			coos.append(tuple(toDo[:2])) 
			del toDo[:2]
		self.coos = tuple(coos)


_regionMakers = [] 
def registerRegionMaker(fun):
	"""adds a region maker to the region resolution chain.

	region makers are functions taking the argument to REGION and
	trying to do something with it.  They should return either some
	kind of FieldInfoedNode that will then replace the REGION or None,
	in which case the next function will be tried.

	As a convention, region specifiers here should always start with
	an identifier (like simbad, siapBbox, etc, basically [A-Za-z]+).
	The rest is up to the region maker, but whitespace should separate
	this rest from the identifier.
	"""
	_regionMakers.append(fun)


@symbolAction("region")
def makeRegion(children):
	if len(children)!=4 or not isinstance(children[2], CharacterStringLiteral):
		raise RegionError("'%s' is not a Region expression I understand"%
			"".join(flatten(c) for c in children))
	arg = children[2].value
	for r in _regionMakers:
		res = r(arg)
		if res is not None:
			return res
	raise RegionError("'%s' is not a region specification I understand."%
		arg)
	

class Centroid(_FunctionalNode):
	type = "centroid"

class Distance(_FunctionalNode):
	type = "distanceFunction"

class predicateGeometryFunction(_FunctionalNode):
	type = "predicateGeometryFunction"

class PointFunction(_FunctionalNode):
	type = "pointFunction"

class Area(_FunctionalNode):
	type = "area"
