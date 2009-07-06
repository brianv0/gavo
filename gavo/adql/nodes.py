"""
Node classes and factories used in ADQL tree processing.
"""

import sys
import traceback
import weakref

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


def getUniqueMatch(matches, colName):
	"""returns the only item of matches if there is exactly one, raises an
	appropriate exception if not.
	"""
	if len(matches)==1:
		return matches[0]
	elif not matches:
		raise ColumnNotFound(colName)
	else:
		raise AmbiguousColumn(colName)


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


######################### Generic Node definitions

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
	local analysis of self.children at construction time.  If they need to
	call _processChildren of a superclass, the *must* use 
	_processChildrenNext(cls) to do so.
	"""
	type = None

	def __init__(self, children):
		self.children = children
		try:
			self._processChildren()
		except:
			# Careful here: these exceptions may be masked by pyparsing,
			# though I haven't yet investigated how that happens.
			raise

	def __iter__(self):
		return iter(self.children)

	def __repr__(self):
		return "<%s, %s>"%(self.type, self.children)

	def iterNodes(self):
		"""iterates over all children, ignoring string children.
		"""
		for c in self:
			if isinstance(c, ADQLNode):
				yield c

	def _processChildrenNext(self, cls):
		try:
			pc = super(cls, self)._processChildren
		except AttributeError:
			pass
		else:
			pc()

	def _processChildren(self):
		self._processChildrenNext(ADQLNode)

	def getChildrenOfType(self, type):
		return [c for c in self if getType(c)==type]
	
	def getChildOfType(self, type, default=None):
		res = self.getChildrenOfType(type)
		if len(res)==0:
			if default is not None: 
				return default
			raise NoChild(type, self)
		if len(res)!=1:
			raise MoreThanOneChild(type, self)
		return res[0]

	def flatten(self):
		"""returns a string representation of the text content of the tree.

		You will have to override this if there are Ignored elements
		or if you do tree manipulations without updating children (which
		in general is a good thing, since self.children manipulations
		probably are quite brittle).

		See also the flattenKWs function.
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
	
	def find(self, type):
		"""returns the leftmost node of type t below self.

		The function returns None if no such node exists.

		Actually, each node is tested first, so "leftmost" should be something
		like "top-leftmost" or so, but you'll usually get what you expect.
		"""
		for c in self.iterNodes():
			if c.type==type:
				return c
			res = c.find(type)
			if res is not None:
				return res
			

class FunctionMixin(object):
	"""is a mixin for ADQLNodes for parsing out arguments and a
	function name.

	The arguments have to be put into nodes at least so far that
	no literal parens and commas are left in the function node's
	children.

	What you get is an attribute funName (always uppercased for
	convenience) and and an attribute args containing strings
	flattened from the arguments.
	"""
	def _parseFuncArgs(self):
		toDo = self.children[:]
		self.args, self.rawArgs, newArg = [], [], []
		# before the opening paren: the name
		self.funName = toDo.pop(0).upper()
		assert toDo.pop(0)=='('
		while 1:
			tok = toDo.pop(0)
			if tok==')':
				break
			elif tok==',':
				self.args.append(" ".join(newArg))
				self.rawArgs.append(newArg)
				newArg = []
			else:
				newArg.append(flatten(tok))
				self.rawArgs.append(tok)
		if newArg:
			self.args.append(" ".join(newArg))
			self.rawArgs.append(newArg)

	def _processChildren(self):
		self._parseFuncArgs()
		self._processChildrenNext(FunctionMixin)


class FieldInfoedNode(ADQLNode):
	"""is an ADQL node that carries a FieldInfo.

	This is true for basically everything in the tree below a derived
	column.

	You'll usually have to override addFieldInfo.  The default implementation
	just looks in its immediate children for anything having a fieldInfo,
	and if there's exactly one such child, it adopts that fieldInfo as
	its own, not changing anything.
	"""
	fieldInfo = None

	def _getInfoChildren(self):
		return [c for c in self.children if getattr(c, "fieldInfo", None)]

	def addFieldInfo(self, colsInfo):
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


class CorrelationSpecification(ADQLNode):
	type = "correlationSpecification"
	def _processChildren(self):
		self.name = self.qName = self.children.get("alias")


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
	type = "possiblyAliasedTable"
	joinedTables = []
	def __repr__(self):
		return "<tableReference to %s>"%",".join(self.getAllNames())

	def _processChildren(self):
		if self.children.get("corrSpec"):
			self.tableName = self.children.get("corrSpec")
			self.originalTable = self.children.get("tableName")
		else:
			self.tableName = self.originalTable = self.getChildOfType("tableName")
		self.joinedTables = self.getChildrenOfType("tableReference")

	def getAllNames(self):
		"""iterates over all fully qualified table names mentioned in this
		(possibly joined) table reference.
		"""
		yield self.tableName.qName
		for t in self.joinedTables:
			yield t.tableName.qName


class WhereClause(ADQLNode):
	type = "whereClause"

class Grouping(ADQLNode):
	type = "groupByClause"

class Having(ADQLNode):
	type = "havingClause"

class OrderBy(ADQLNode):
	type = "sortSpecification"


class QuerySpecification(ADQLNode, ColBearingMixin): 
	type = "statement"

	def _processChildren(self):
		for name in ["setQuantifier", "setLimit", "selectList", "fromClause",
				"whereClause", "grouping", "having", "orderBy"]:
			setattr(self, name, self.children.get(name))
		self.query = weakref.proxy(self)
		self._processChildrenNext(QuerySpecification)
	
	def getSelectFields(self):
		if self.selectList.isAllFieldsQuery:
			return self.fromClause.getAllFields()
		else:
			return self.selectList.selectFields

	def getSourceTableNames(self):
		return self.fromClause.getTableNames()
	
	def resolveField(self, fieldName):
		return self.fromClause.resolveField(fieldName)

	def getAllNames(self):
		for n in self.fromClause.getTableNames():
			yield n

	def flatten(self):
		return flattenKWs(self, ("SELECT", None),
			("", "setQuantifier"),
			("TOP", "setLimit"),
			("", "selectList"),
			("", "fromClause"),
			("", "whereClause"),
			("", "grouping"),
			("", "having"),
			("", "orderBy"),)


class DerivedTable(QuerySpecification):
	type = "derivedTable"
	def _processChildren(self):
		self._processChildrenNext(DerivedTable)
		self.tableName = self.children.get("corrSpec")

	def getAllNames(self):
		yield self.tableName.qName
		for n in QuerySpecification.getAllNames(self):
			yield n

	def flatten(self):
		return "(%s) AS %s"%(QuerySpecification.flatten(self),
			self.tableName.qName)


class FromClause(ADQLNode):
	type = "fromClause"

	def _processChildren(self):
		self.tablesReferenced = [t for t in self.children
			if isinstance(t, ColBearingMixin)]
	
	def getTableNames(self):
		res = []
		for t in self.tablesReferenced:
			res.append(t.tableName.qName)
		return res
	
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
		def __init__(self, name, fieldInfo):
			self.name, self.fieldInfo = name, fieldInfo

		def iterNodes(self):
			return []

		def addFieldInfo(self, resolve):
			pass # we were born with one.

	def getAllFields(self):
		res = []
		for table in self.tablesReferenced:
			for column in table.fieldInfos.seq:
				res.append(self.FakeSelectField(*column))
		return res


class ColumnReference(FieldInfoedNode):
	type = "columnReference"
	cat = schema = table = name = None
	def _processChildren(self):
		self.colName = "".join(self.children)
		names = [c for c in self.children if c!="."]
		names = [None]*(4-len(names))+names
		self.cat, self.schema, self.table, self.name = names

	def addFieldInfo(self, fieldResolver):
		self.fieldInfo = fieldResolver(self.name)


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
		self.isAllFieldsQuery = len(self.children)==1 and self.children[0] == '*'
		if self.isAllFieldsQuery:
			self.selectFields = None  # Will be filled in by query, we don't have
				# the from clause here.
		else:
			self.selectFields = self.getChildrenOfType("derivedColumn")


######## all expression parts we need to consider when inferring units and such

class Comparison(ADQLNode):
	"""is required when we want to morph the braindead contains(...)=1 into
	a true boolean function call.
	"""
	type = "comparisonPredicate"

	def _processChildren(self):
		self.op1, self.opr, self.op2 = self.children


class Factor(FieldInfoedNode):
	"""is a factor within an SQL expression.

	factors may have only one (direct) child with a field info and copy
	this.  The can have no child with a field info, in which case they're
	dimless.
	"""
	type = "factor"
	collapsible = True

	def addFieldInfo(self, colsInfo):
		infoChildren = self._getInfoChildren()
		if infoChildren:
			assert len(infoChildren)==1
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			self.fieldInfo = dimlessFieldInfo


class CombiningFINode(FieldInfoedNode):
	def addFieldInfo(self, colsInfo):
		infoChildren = self._getInfoChildren()
		if not infoChildren:
			self.fieldInfo = dimlessFieldInfo
		elif len(infoChildren)==1:
			self.fieldInfo = infoChildren[0].fieldInfo
		else:
			self.fieldInfo = self._combineFieldInfos()


class Term(CombiningFINode):
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


class NumericValueExpression(CombiningFINode):
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


class GenericValueExpression(CombiningFINode):
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
		res = GenericValueExpression(children)
		res.type = "valueExpression"
		return res
	else:
		return children[0]


class CountAll(FieldInfoedNode):
	"""is a COUNT(*)-type node.
	"""
	type = "countAll"
	fieldInfo = FieldInfo("", "meta.number")

	# XXX TODO: We could inspect parents to figure out *what* we're counting
	def addFieldInfo(self, colsInfo):
		pass


class SetFunction(FieldInfoedNode):
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

	def addFieldInfo(self, colsInfo):
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


class NumericValueFunction(FieldInfoedNode, FunctionMixin):
	"""is a numeric function.

	This is really a mixed bag.  We work through handlers here.  See table
	in class def.  Unknown functions result in dimlesses.
	"""
	type = "numericValueFunction"
	collapsible = True  # if it's a real function call, it has at least
		# a name, parens and an argument and thus won't be collapsed.

# XXX TODO: we could check and warn if there's something wrong with the
# arguments in the handlers.
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

	def addFieldInfo(self, colsInfo):
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

	def _processChildren(self):
		self.value = "".join(c[1:-1] for c in self.children)

	def addFieldInfo(self, ignored):
		self.fieldInfo = dimlessFieldInfo

###################### Geometry and stuff that needs morphing into real SQL


class CoosysMixin(object):
	"""is a mixin that works cooSys into FieldInfos for ADQL geometries.
	"""
	def addFieldInfo(self, colsInfo):
		infoChildren = self._getInfoChildren()
		self.fieldInfo = FieldInfo("", "", collectUserData(infoChildren)[0])
		self.fieldInfo.cooSys = self.cooSys

	def _processChildren(self):
		self._processChildrenNext(CoosysMixin)
		self.cooSys = self.children[2].value

class _FunctionalNode(FieldInfoedNode, FunctionMixin):
	pass


class Point(CoosysMixin, _FunctionalNode):
	"""points have cooSys, x, and y attributes.
	"""
	type = "point"

	def _processChildren(self):
		self._processChildrenNext(Point)
		self.x, self.y = self.args[1:]
	

class Circle(CoosysMixin, _FunctionalNode):
	"""circles have cooSys, x, y, and radius attributes.
	"""
	type = "circle"

	def _processChildren(self):
		self._processChildrenNext(Circle)
		self.x, self.y, self.radius = self.args[1:]


class Rectangle(CoosysMixin, _FunctionalNode):
	"""rectangles have cooSys, x0, y0, x1, and y1 attributes.
	"""
	type = "rectangle"

	def _processChildren(self):
		self._processChildrenNext(Rectangle)
		self.x0, self.y0, self.x1, self.y1 = self.args[1:]


class Polygon(CoosysMixin, _FunctionalNode):
	"""rectangles have a cooSys attribute, and store pairs of
	coordinates in coos.
	""" 
	type = "polygon"

	def _processChildren(self):
		self._processChildrenNext(Polygon) 
		toDo = self.args[1:]
		self.coos = [] 
		while toDo:
			self.coos.append(tuple(toDo[:2])) 
			del toDo[:2]


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
	"""centroids have an expression attribute.
	"""
	type = "centroid"

	def _processChildren(self):
		self._processChildrenNext(Centroid)
		assert len(self.args)==1
		self.expression = self.args[0]


class Distance(_FunctionalNode):
	"""The distance function -- 2 arguments, both points.
	"""
	type = "distanceFunction"


class predicateGeometryFunction(_FunctionalNode):
	"""CONTAINS or INTERSECTS calls -- two arguments, geometry expressions.
	"""
	type = "predicateGeometryFunction"


class PointFunction(_FunctionalNode):
	"""LONGITUDE or LATITUDE calls -- one argument, a geometry expression 
	evaluating to a point.
	"""
	type = "pointFunction"


class Area(_FunctionalNode):
	"""one argument, a geometry expression.
	"""
	type = "area"
