"""
This module contains condition generator classes.

Instances of these classes know how to emit HTML for forms giving values
to them and how to emit SQL for queries in which they participate.

They will usually end up within the expression trees generated in
sqlparse.
"""

import re
import weakref
import compiler
import compiler.ast
import compiler.pycodegen

import gavo
from gavo import sqlsupport
from gavo import coords
from gavo import utils
from gavo.web import querulator


class ArgumentError(gavo.Error):
	"""is raised when improper arguments are given to a CondGen constructor.
	"""


class CondGen:
	"""is a condition generator.

	Condition generators are instanciated with a varying number of arguments,
	mostly by the SQL parser.  It is the responsibility of the parser to
	make sure the arguments are "good".  
	
	The only argument strictly necessary is a "name".  This can be any string
	(including the empty string).  It is used to identify the arguments
	across a form->user->query cycle.  It is probably a good idea to keep
	these names uniqe within a query, but this is left to the user.  Classes
	that use these names directly should probably raise an Error on empty
	names.

	All classes derived from CondGen should add to the set expectedKeys
	whatever keys they want to see in the context.  You can then use the
	_contextMatches method to see if the CondGen should "fire".

	CondGens implement a setParent method used by the SQL parser.  Thus,
	if the CondGen is in an SQL parse tree, you can use that method *after*
	the constructor is finished to traverse that tree.
	"""
	def __init__(self, name):
		self.name = name
		self.expectedKeys = set()

	def __repr__(self):
		""" -- define reprs of your own for unit tests and such...
		"""
		return "%s(...)"%self.__class__.__name__

	def setParent(self, parent):
		self.parent = weakref.proxy(parent)
	
	def getParent(self):
		return self.parent

	def _ensureNonEmptyName(self):
		if not self.name:
			raise ArgumentError("%s needs non-empty name"%self.__class__.__name__)

	def getExpectedKeys(self):
		return self.expectedKeys

	def asCondition(self, context):
		return ""

	def _contextMatches(self, context):
		return context.checkArguments(self.expectedKeys)

	def __iter__(self):
		"""stops any iteration.

		This is needed to let us live in parse trees without messing their
		traversal up.
		"""
		raise StopIteration


class OperatorCondGen(CondGen):
	"""is a condition generator for a generic SQL operator with one
	operand.
	
	It is not useful in itself (it's abstract, if you will), so don't
	use it.

	(Technical information:)
	The default implementation assumes you only have one key called
	name.  If that is not true for your case, you need to override
	at least _getSqlOperand and asCondition.
	"""

	setOperators = set(["in"])

	def __init__(self, name, sqlExpr, operator):
		CondGen.__init__(self, name)
		self._ensureNonEmptyName()
		self.sqlExpr = sqlExpr
		self.operator = operator
		self.takesSets = self.operator.lower() in self.setOperators
		self.expectedKeys.add(self.name)

	def __repr__(self):
		return "%s %s %s()"%(self.sqlExpr, self.operator, self.__class__.__name__)

	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		secondOperand, args = self._getSqlOperand(context)
		return "%s %s %s"%(self.sqlExpr, self.operator, secondOperand
			), args

	def _getVal(self, context):
		if self.takesSets:
			return context.getlist(self.name)
		else:
			return context.getfirst(self.name)

	def asCondition(self, context):
		if not self._contextMatches(context):
			return ""
		return "%s %s %s"%(self.sqlExpr, self.operator.lower(), 
			self._getVal(context))

	def _getSqlOperand(self, context):
		return "%%(%s)s"%self.name, {self.name: self._getVal(context)}


class Choice(OperatorCondGen):
	"""is a condition generator for multiple choice boxes.
	
	If the operator is one accepting sets (like IN), you will be able
	to select multiple items.

	Arguments:
	
	* choices --a sequence of 2-tuples of (value, title), where value is 
	  what the form recipient gets and title is what the user sees.
	* size -- an int saying how many rows are visible (optional).

	Examples:

	filter = Choice([("Filter 1", "Johnson U"), ("Filter 2", "Johnson B")])

	  will create a pull-down box to select the two Johnson filters, and
	  the DB will be queried for "Filter 1" if Johnson U is selected, and
	  for "Filter 2" if Johnson B is selected.
	
	filter in Choice([("Filter 1", "Johnson U"), ("Filter 2", "Johnson B")], 
	  size=2)

	  is about the same, only you'll be seeing both choices at the same time.
		Additionally, since there's an "in" operator governing the condGen,
		you can select both entries (which is an implicit "OR").
	"""
	def __init__(self, name, sqlExpr, operator, choices, size=1):
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
		self.choices, self.size = choices, size
		self.expectedKeys.add(self.name)

	def asHtml(self, context):
		selOpt = " size='%d'"%self.size
		if self.takesSets:
			selOpt += " multiple='multiple'"
		formItem = '<select name="%s" %s>\n%s\n</select>'%(
			self.name,
			selOpt,
			"\n".join(['<option value=%s>%s</option>'%(repr(val), opt) 
				for opt, val in self.choices]))
		doc = ""
		if self.takesSets:
			doc = ('<div class="legend">(Zero or more choices allowed; '
				'try shift-click, control-click)</div>')
		return formItem+doc


class SimpleChoice(Choice):
	"""is a condition generator for simple choice boxes.
	
	Choice boxes are simple if (a) they're always "pull down", i.e., you'll
	only see one entry and (b) what you select is what the db sees.

	Argument:

	* choice -- a sequence of items listed in the choice box

	Example:

	obsType = SimpleChoice(["SCIENCE", "CALIB", "BIAS", "FLAT"])
	"""
	def __init__(self, name, sqlExpr, operator, choices):
		Choice.__init__(self, name, sqlExpr, operator,
			[(choice, choice) for choice in choices])


class ChoiceFromDb(Choice):
	"""is a condition generator for building choice boxes from database
	queries.
	
	If the operator before the ChoiceFromDb wants sets as the second
	operand ("IN"), you will be able to select multiple items.

	Arguments:

	* query -- an SQL query the result rows of which make up the choices.
	* prependAny -- prepends an "ANY" entry to the list of choices.  That
	  is not strictly necessary because deselecting all entries would
	  have the same effect, but it may be nice anyway (XXX doesn't quite
	  work as expected right now) (optional, default False)
	* size -- as for Choice

	Example:

	objects in ChoiceFromDb("select distinct objects from observations.frames")
	"""
	def __init__(self, name, sqlExpr, operator, query, 
			prependAny=False, size=1):
		# this is a bit of a hack: since I have no context at construction
		# time, I'm construction the Choice with the query instead of
		# a list of options and only put in the real list at asHtml time.
		Choice.__init__(self, name, sqlExpr, operator, query, size=size)
		self.prependAny = prependAny
		if self.takesSets and size==1:
			self.size=3
	
	def _buildChoices(self, context, query, prependAny):
		querier = context.getQuerier()
		validOptions = [(opt[0], opt[0]) 
			for opt in querier.query(query).fetchall()]
		validOptions.sort()
		if prependAny:
			validOptions.insert(0, ("ANY", ""))
		return validOptions
	
	def asHtml(self, context):
		if isinstance(self.choices, basestring):
			self.choices = self._buildChoices(context, self.choices, 
				self.prependAny)
		return Choice.asHtml(self, context)


class Date(OperatorCondGen):
	"""is a condition generator for dates.
	
	The main effect of using this rather than a StringField is that
	you get a nice little help in the legend.

	Date takes no arguments.

	Example:

	obsDate = Date()
	"""
	def asHtml(self, context=None):
		return ('<input type="text" size="20" name="%s"> '
			'<div class="legend">(YYYY-MM-DD)</div>')%self.name


class StringField(OperatorCondGen):
	"""is a condition generator for just any odd value.
	
	Use this if you have no reason to do otherwise.

	Arguments:

	* size -- the width of the field in chars (optional, default 30)
	* doc -- stuff to put into legend (optional, default "")

	Examples:

	specType = StringField(size=4)

	flag = StringField(size=1, doc="a for left, b for center, c for right")
	"""
	def __init__(self, name, sqlExpr, operator, size=30, doc=""):
		self.size, self.doc = size, doc
		OperatorCondGen.__init__(self, name, sqlExpr, operator)

	def asHtml(self, context=None):
		return ('<input type="text" size="%d" name="%s">'
			'<div class="legend">%s</div>')%(self.size, self.name, self.doc)


class PatternField(StringField):
	"""is a StringField with built-in help for SQL patterns.
	
	Arguments:
	
	* size -- as for StringField
	* doc -- is ignored

	Example:

	specType like PatternField(size=7)
	"""
	def asHtml(self, context=None):
		return ('<input type="text" size="%d" name="%s">'
			'<div class="legend">(_ for any char, %% for'
			' any sequence of chars)</div>')%(self.size, self.name)


class IntField(OperatorCondGen):
	"""is a condition generator for integer fields.
	
	IntFields have no arguments.

	At some point, I might add input validation, so use this when you
	actually expect ints.
	"""
	def asHtml(self, context=None):
		return '<input type="text" size="5" name="%s">'%self.name


class FloatField(OperatorCondGen):
	"""is a condition generator for float fields.
	
	Argument:

	* default -- an intial value to set into the field (optional, default "")

	At some point, I might add input validation, so use this when you
	actually expect floats.
	"""
	def __init__(self, name, sqlExpr, operator, default=""):
		self.default = default
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
	
	def asHtml(self, context={}):
		return '<input type="text" size="10" name="%s" value="%s">'%(
			self.name, self.default or context.get(self.name) or "")


class FloatFieldWithTolerance(OperatorCondGen):
	"""is a condition generator for float fields having an adjustable
	tolerance.
	"""
	def __init__(self, name, sqlExpr, operator):
		assert(operator.lower, "between")
		OperatorCondGen.__init__(self, name, sqlExpr, operator)
		self.expectedKeys.add("%s-tolerance"%self.name)
	
	def asHtml(self, context):
		default = context.get(self.name)
		if default==None:
			default = ""
		return ('<input type="text" size="10" name="%s" value="%s">'
			' &plusmn; <input type="text" size="5" name="%s-tolerance">')%(
			self.name, default, self.name)

	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		mid = float(context.getfirst(self.name))
		tolerance = float(context.getfirst("%s-tolerance"%self.name))
		return "%s BETWEEN %%(%s)s AND %%(%s)s"%(self.sqlExpr,
			"%s-lower"%self.name, "%s-upper"%self.name), {
				"%s-lower"%self.name: mid-tolerance,
				"%s-upper"%self.name: mid+tolerance,}
	
	def asCondition(self, context):
		if not self._contextMatches(context):
			return ""
		return "%s=%s &plusmn; %s"%(self.sqlExpr, context.getfirst(self.name),
			context.getfirst("%s-tolerance"%self.name))


class BetweenCondGen(CondGen):
	"""is a condition generator for generic ranges.
	
	In SQL, this becomes a BETWEEN expression if both upper and lower
	bounds are given, falling back to simple comparsions otherwise.

	BeetweenConds take no arguments.

	Example:

	pm BETWEEN BetweenCondGen()
	"""
	def __init__(self, name, sqlExpr, operator):
		CondGen.__init__(self, name)
		self.sqlExpr, self.operator = sqlExpr, operator
		if self.operator.lower()!="between":
			raise "%s only make sense with the BETWEEN SQL operator"%(
				self.__class__.__name__)
		self.expectedKeys.add(self.name+"-lower")
		self.expectedKeys.add(self.name+"-upper")
	
	def asSql(self, context):
		lowerKey, upperKey = "%s-lower"%self.name, "%s-upper"%self.name
		qString = ""
		argDict = {}
		if lowerKey in context:
			argDict[lowerKey] = context.getfirst(lowerKey)
		if upperKey in context:
			argDict[upperKey] = context.getfirst(upperKey)
		if lowerKey in argDict and upperKey in argDict:
			qString = "%s BETWEEN %%(%s)s AND %%(%s)s"%(
				self.sqlExpr, lowerKey, upperKey)
		elif lowerKey in argDict:
			qString = "%s >= %%(%s)s"%(self.sqlExpr, lowerKey)
		elif upperKey in argDict:
			qString = "%s <= %%(%s)s"%(self.sqlExpr, upperKey)
		return qString, argDict

	def asHtml(self, context=None):
		return ('<input type="text" size="10" name="%s-lower">'
				' and <input type="text" size="10" name="%s-upper">'
				'<div class="legend">Leave any empty for open range.</div>'%(
			self.name, self.name))

	def asCondition(self, context):
		q, vals = self.asSql(context)
		return q%vals


class DateRange(BetweenCondGen):
	"""is a condition generator for date ranges.
	
	This currently is just a BetweenCondGen, with an amended legend.

	Example:

	date between DateRange()
	"""
	def asHtml(self, context=None):
		return ('<input type="text" size="10" name="%s-lower">'
			' and <input type="text" size="10" name="%s-upper">'
			'<div class="legend">Leave any empty for open range.  Use'
			' date format YYYY-MM-DD</div>')%(self.name, self.name)


def buildConeSearchQuery(prefix, ra, dec, sr):
	"""returns an SQL fragment for a cone search around the given
	coordinates.

	This assumes the table being queried satisfies the positions interface.

	This does not have any idea of equinoxes and the like.  That would
	have to be handled on a higher level.

	ra, dec, and sr are all in decimal degrees.
	"""
	c_x, c_y, c_z = coords.computeUnitSphereCoords(float(ra), float(dec))
	return ("sqrt((%%(%sc_x)s-c_x)^2+(%%(%sc_y)s-c_y)^2+"
		"(%%(%sc_z)s-c_z)^2)"%(prefix, prefix, prefix)+
		"<= %%(%ssr)s"%prefix), {
			"%sc_x"%prefix: c_x,
			"%sc_y"%prefix: c_y,
			"%sc_z"%prefix: c_z,
			"%ssr"%prefix: utils.degToRad(sr)}


def buildQ3ConeSearchQuery(prefix, ra, dec, sr):
	"""returns an SQL fragment for a cone search around the given
	coordinates.

	This only works if you have the q3c extension in your postgres engine.
	If you used the q3cscript.template, the queries should be *much*
	faster than with a standard cone search query.

	This assumes the table being queried satisfies the positions interface.

	This does not have any idea of equinoxes and the like.  That would
	have to be handled on a higher level.

	ra, dec, and sr are all in decimal degrees.
	"""
	return "q3c_radial_query(alphaFloat, deltaFloat, %f, %f, %f)"%(
		ra, dec, sr), {}


class StandardConeSearch(CondGen):
	"""is a CondGen that inserts a VO-compatible cone search.
	
	These assume the table supports the positions interface, i.e., 
	has c_x, c_y, c_z fields.

	Instead of coordinates, you can also give Simbad identifiers.

	Arguments:

	* useQ3C -- if True, the SQL will use the q3c extension.  See docs.
	  Optional, defaults to False.  You can only use this when you have
	  q3c installed.

	Examples:

	StandardConeSearch()
	StandardConeSearch(useQ3C=True)
	"""
	def __init__(self, name="", useQ3C=False):
		CondGen.__init__(self, name)
		self.useQ3C = useQ3C
		self.expectedKeys.add("SR")  # all in decimal degrees
		self.expectedKeys.add("RA")
		self.expectedKeys.add("DEC")

	def asHtml(self, context=None):
		return ('<input type="text" size="5" name="SR" value="%s">'
			' degrees around<br>'
			'&alpha; <input type="text" size="10" name="RA" value="%s"><br>'
			'&delta; <input type="text" size="10" name="DEC" value="%s">'
			'<div class="legend">(&alpha;, &delta; decimal degrees in J2000.0)'
			'</div>')%(context.get("SR", ""), context.get("RA", ""),
				context.get("DEC", ""))
	
	def asCondition(self, context):
		if self._contextMatches(context):
			return "Position %s degrees around &alpha; %s, &delta; %s"%(
				context.getfirst("SR"),
				context.getfirst("RA"),
				context.getfirst("DEC"))
		return ""
	
	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		try:
			ra, dec = float(context.getfirst("RA")), float(context.getfirst("DEC"))
			sr = float(context.getfirst("SR"))
		except ValueError, msg:
			raise querulator.Error("RA, DEC, and search radius must be given"
				" as decimal floats in degrees")
		if self.useQ3C:
			return buildQ3ConeSearchQuery(self.name, ra, dec, sr)
		else:
			return buildConeSearchQuery(self.name, ra, dec, sr)


class SexagConeSearch(CondGen):
	"""is a CondGen that does a cone search on sexagesimal coordinates.
	
	These assume the table supports the positions interface, i.e., 
	has c_x, c_y, c_z fields.

	Instead of coordinates, you can also give Simbad identifiers.

	Arguments:

	* useQ3C -- if True, the SQL will use the q3c extension.  See docs.
	  Optional, defaults to False.  You can only use this when you have
	  q3c installed.

	Examples:

	SexagConeSearch()
	SexagConeSearch(useQ3C=True)
	"""
	def __init__(self, name="", useQ3C=False):
		CondGen.__init__(self, name)
		self.useQ3C = useQ3C
		self.expectedKeys.add("%sSRminutes"%self.name)
		self.expectedKeys.add("%ssexagMixedPos"%self.name)

	def asHtml(self, context=None):
		return ('<input type="text" size="5" name="%sSRminutes" value="1">'
			' arcminutes around<br>'
			'<input type="text" size="30" name="%ssexagMixedPos">'
			'<div class="legend">(Position sexagesimal RA and dec in source equinox'
			' with requried sign on dec, or simbad identifier)</div>')%(
			self.name, self.name)
	
	def asCondition(self, context):
		if self._contextMatches(context):
			return "Position %s arcminutes around %s"%(
				context.getfirst("%sSRminutes"%self.name),
				context.getfirst("%ssexagMixedPos"%self.name))
		return ""
	
	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		pos = context.getfirst("%ssexagMixedPos"%self.name)
		mat = re.match("(.*)([+-].*)", pos)
		try:
			ra, dec = coords.hourangleToDeg(mat.group(1)), coords.dmsToDeg(
				mat.group(2))
		except (AttributeError, ValueError):
			try:
				data = context.getSesame().query(pos)
				if not data:
					raise KeyError(pos)
				ra, dec = float(data["RA"]), float(data["dec"])
			except KeyError:
				raise querulator.Error("Sexagesimal mixed positions must"
					" have a format like hh mm ss[.ddd] [+-]dd mm ss[.mmm] (the"
					" sign is important).  %s does not appear to be of this format,"
					" and also cannot be resolved by Simbad."%repr(pos))
		try:
			sr = float(context.getfirst("%sSRminutes"%self.name))/60
		except ValueError:
			raise querulator.Error("Search radius must be given as arcminutes"
				" float. %s is invalid."%repr(context.getfirst("SRminutes")))
		if self.useQ3C:
			return buildQ3ConeSearchQuery(self.name, ra, dec, sr)
		else:
			return buildConeSearchQuery(self.name, ra, dec, sr)


class Q3Join(OperatorCondGen):
	"""is a CondGen that selects stars that have a neighbour within a defined
	distance.

	This uses Q3C.  It works by selecting a certain column from the matches
	which is then entered into the matching process.  That column should
	usually be the primary key.  The only supported operator is "in".

	Argument:

	* tableName -- the name of the table to perform autocorrelation on.
	  This table must implement the q3cpositions interface.

	Example:

	localid in Q3Join("ppmx.data")
	"""
	def __init__(self, name, sqlId, operator, tableName):
		if operator.lower()!="in":
			raise ArgumentError("Q3Join only works with the in operator")
		self.tableName = tableName
		OperatorCondGen.__init__(self, name, sqlId, operator)
	
	def asHtml(self, context=None):
		return ('<input type="text" size="10" name="%s">')%(self.name)

	def _getMasterTableName(self):
		"""returns the name of the table the innermost SELECT queries.
		"""
		node = self.getParent()
		while node:
			try:
				return node.getDefaultTable()
			except AttributeError:
				node = node.getParent()
		raise Error("Q3Join cannot find table name")

	def asSql(self, context):
		if not self._contextMatches(context):
			return "", {}
		masterTableName = self._getMasterTableName()
		aliasBase = context.getUid(self)
		aliasA, aliasB = aliasBase+"A", aliasBase+"B"
		args = {self.name: float(context.getfirst(self.name))/3600.}
		return ("%(key)s in (select %(aliasA)s.%(key)s"
			" from %(masterTable)s as %(aliasA)s,"
			" %(otherTable)s as %(aliasB)s"
			" where %(aliasA)s.%(key)s!=%(aliasB)s.%(key)s"
			" AND q3c_join(%(aliasA)s.alphaFloat,"
			" %(aliasA)s.deltaFloat, %(aliasB)s.alphaFloat, %(aliasB)s.deltaFloat,"
			" %%(%(name)s)s))")%{
				"key": self.sqlExpr,
				"masterTable": masterTableName,
				"otherTable": self.tableName,
				"aliasA": aliasA,
				"aliasB": aliasB,
				"name": self.name}, args

	def asCondition(self, context):
		if not self._contextMatches(context):
			return ""
		return "Another object within %s arcsecs"%(context.getfirst(self.name))


class FeedbackSearch(CondGen):
	"""is a CondGen that enables feedback fields.
	
	This is really only useful in connection with the feedback format
	hint that produces links that define what we are to feedback on.

	Arguments:

	* tableName -- the table to query
	* fields -- a sequence of field names to do feedback on (optional,
	  defaults to all usable fields in the table).
	* name -- a desambiguator if you want to provide more than one
	  feedback query in one form (optional, defaults to "")

	Examples:

	localid=FeedbackSearch("cns4.data")

	localid=FeedbackSearch("cns4.data", ["u_x", "u_y", "u_z"], "spacevel")
	"""
	def __init__(self, name, targetField, ignored, tableName, fields=None, 
			prefix=""):
		self.tableName = tableName
		self.queryKey = "%sfeedback"%prefix
		self.targetField = targetField
		self.fields = fields
		self.hasPositions = True # XXX TODO: Get this from some meta table

	def _buildFields(self, fields, context):
		self.fieldDefs = sqlsupport.MetaTableHandler(context.getQuerier()
			).getFieldDefs(self.tableName)
		if fields:
			fields = set(fields)
			self.fieldDefs = [(name, type, info) 
					for name, type, info in self.fieldDefs
				if name in fields]

	def _getTitleFor(self, name, info):
		"""returns a proper field title for presentation purposes for the field
		name with info (from fieldDefs)
		
		name and info are the first and third components of a fieldDef,
		respectively.
		"""
		unitStr = info.get("unit")
		if unitStr:
			unitStr = " [%s]"%unitStr
		else:
			unitStr = ""
		return "%s %s"%(info.get("tablehead") or name, unitStr)

	def _getKeyFor(self, name):
		"""returns a form key name for the field name
		"""
		return "%s%s"%(self.queryKey, name)

	def _buildExpression(self):
		"""returns an sqlparse.CExpression for the feedback query.
		"""
		from gavo.web.querulator import sqlparse
		children = []
		availableFields = set()
		for name, dbtype, info in self.fieldDefs:
			title, key = self._getTitleFor(name, info), self._getKeyFor(name)
			availableFields.add(name)
			if dbtype=="real":
				children.append(sqlparse.Condition(title,
					("operator",
						(name, "BETWEEN", "FloatFieldWithTolerance()")), key))
				children.append("AND")
		if self.hasPositions:
			children.append(sqlparse.Condition("Cone around",
				("predefined",
					("StandardConeSearch(useQ3C=True)",)), self._getKeyFor("cone")))
			children.append("AND")

		if len(children)==0:
			self.expression = sqlparse.LiteralCondition("1", "=", "1")
		elif len(children)==1:
			self.expression = children[0]
		else:
			self.expression = sqlparse.CExpression(*children[:-1])

	def _getLocalContext(self, context):
		"""returns a context containing the values from the selected
		object.
		"""
		querier = context.getQuerier()
		selectItems = ", ".join([name for name, type, info in
			self.fieldDefs])
		qRes = querier.query("SELECT %s FROM %s WHERE"
			" %s=%%(val)s"%(selectItems, self.tableName, self.targetField), 
				{"val": context.get(self.queryKey)}).fetchall()
		qValues = qRes[0]
		localContext = {}
		for (name, dbtype, info), value in zip(self.fieldDefs, qValues):
			localContext[self._getKeyFor(name)] = value
		if self.hasPositions:
			localContext["RA"] = localContext[self._getKeyFor("alphaFloat")]
			localContext["DEC"] = localContext[self._getKeyFor("deltaFloat")]
		return localContext

	def _build(self, context):
		"""actually makes the sql tree.

		This doesn't take place in the constructor since we need a
		context for that.
		"""
		self._buildFields(self.fields, context)
		self._buildExpression()

	def asHtml(self, context):
		self._build(context)
		if self.queryKey in context:
			try:
				return '<div class="feedback">%s</div>'%(
					self.expression.asHtml(self._getLocalContext(context)))
			except IndexError:
				import traceback
				traceback.print_exc()
				raise querulator.Error("Could not use %s as specifier for feedback"
					" query"%repr(context.get(self.queryKey)))
	
	def asSql(self, context):
		self._build(context)
		return self.expression.asSql(context)


import sys, traceback


def makeCondGen(name, cType, toks):
	"""generates a CondGen.

	name is the name stem for the arguments, cType is "operator" or "predefined",
	and toks a a list of tokens.

	If cType is "operator", then toks[0] is an sqlExpression, toks[1] an
	operator, and toks[2] a python expression.

	If cType is "predefined", then toks[0] contains the python expression
	to build the CondGen from.
	"""
	def findFuncNode(node):
		for child in node.getChildNodes():
			if isinstance(child, compiler.ast.CallFunc):
				return child
			funcNode = findFuncNode(child)
			if funcNode:
				return funcNode

	def getConstructionCode(pythonExpr, additionalArgs):
		pythonExpr = compiler.parse(toks[-1], "eval")
		funcNode = findFuncNode(pythonExpr)
		funcNode.args[0:0] = additionalArgs
		return pythonExpr

	try:
		if cType=="operator":
			ast = getConstructionCode(toks[-1], [compiler.ast.Const(value=name),
				compiler.ast.Const(value=toks[0]), compiler.ast.Const(value=toks[1])])
		else:
			ast = getConstructionCode(toks[-1], [compiler.ast.Const(name)])
		ast.filename = "<Generated>"  # Silly fix for gotcha in compiler
		gen = compiler.pycodegen.ExpressionCodeGenerator(ast)
		return eval(gen.getCode())
	except:
		# I'm spitting out something to sys.stderr since pyparsing will
		# swallow this exception
		sys.stderr.write("Exception happened during CondGen construction.\n")
		sys.stderr.write("Pyparsing will swallow it, so you'll need to read it\n")
		sys.stderr.write("here.")
		traceback.print_exc()
		raise


if __name__=="__main__":
	from gavo.utils import makeClassDocs
	makeClassDocs(CondGen, globals().values())
