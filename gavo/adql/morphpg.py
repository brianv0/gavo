"""
Morphing ADQL into queries that postgres/pgSphere can understand.

Basically, Postgres support most of the stuff out of the box, and it's
just a matter of syntax.

We morph most of the geometry stuff to pgsphere; while some of it would
work with plain postgres in a plane approximation, it's certainly not
worth the effort.

There's also code to replace certain CONTAINS calls with q3c function
calls.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.adql import common
from gavo.adql import morphhelpers
from gavo.adql import nodes
from gavo.adql.nodes import flatten
from gavo.stc import tapstc


class PostgresMorphError(common.MorphError):
	pass



######## Begin q3c specials
# q3c morphing must happen before pgsphere morphs all the mess to
# become spoints and stuff (at least the way we built things so far).
# Hence, this is written as a fairly freaky early morpher.

def _flatAndMorph(node):
# This helper flattens a node after applying standard morphs on it.
# I need this for the arguments of q3c stuff, since there may
# be ADQL specifics in there.
	return nodes.flatten(morphPG(node)[1])


def _booleanizeContainsQ3C(node, operator, operand):
	"""turns ADQL CONTAINS calls into q3c expressions if appropriate.

	This will only work if the arguments have been morphed into pgsphere
	geometries already.  It will leave alone anything it doesn't understand,
	hopefully for pgsphere to pick it up.
	"""
	args = []
	for arg in node.args:
		if hasattr(arg, "original"): # recover pre-pgsphere-morph object
			args.append(arg.original)
		else:
			args.append(arg)

	# leave morphing to someone else if we don't check for point in shape
	# or if system transformations are required.
	if len(args)!=2:
		return None
	if not hasattr(args[0], "cooSys") or not hasattr(args[1], "cooSys"):
		# arguments do not look like geometries; leave it to someone else
		# to blow up
		return None
	if tapstc.getPGSphereTrafo(args[0].cooSys, args[1].cooSys) is not None:
		# we'll need a transform; q3c cannot do this.
		return None

	expr = None
	p, shape = args

	if shape.type=="circle":
		# The pg planner works much smoother if you have constants first.
		if p.x.type=='columnReference':
			expr = ("q3c_join(%s, %s, %s, %s, %s)"%tuple(map(_flatAndMorph,
				(shape.x, shape.y, p.x, p.y, shape.radius))))
		else:
			expr = ("q3c_join(%s, %s, %s, %s, %s)"%tuple(map(_flatAndMorph, 
				(p.x, p.y, shape.x, shape.y, shape.radius))))

	elif shape.type=="polygon":
		expr = "q3c_poly_query(%s, %s, ARRAY[%s])"%(
			_flatAndMorph(p.x), _flatAndMorph(p.y), ",".join([
				"%s,%s"%(_flatAndMorph(x), _flatAndMorph(y)) for x,y in shape.coos]))

	return morphhelpers.addNotToBooleanized(expr, operator, operand)

morphhelpers.registerBooleanizer("CONTAINS", _booleanizeContainsQ3C)


def _booleanizeCROSSMATCH(node, operator, operand):
	node.funName = "q3c_join"
	return morphhelpers.addNotToBooleanized(
		_flatAndMorph(node), operator, operand)


morphhelpers.registerBooleanizer("CROSSMATCH", _booleanizeCROSSMATCH)

######### End q3c specials



######### Begin morphing to pgSphere


class PgSphereCode(object):
	"""A node that contains serialized pgsphere expressions plus
	a coordinate system id for cases in which we must conform.

	Pass the optional original (the node that generates the stuff)
	to allow code like the q3c booleanizer above to still work on
	things if necessary.
	"""
	type = "pgsphere literal"

	def __init__(self, cooSys, content, original=None):
		self.cooSys, self.content = cooSys, content
		self.original = original
	
	def flatten(self):
		return self.content


def _morphCircle(node, state):
	return PgSphereCode(node.cooSys,
		"scircle(spoint(RADIANS(%s), RADIANS(%s)), RADIANS(%s))"%tuple(flatten(a)
			for a in (node.x, node.y, node.radius)),
		original=node)


def _morphPoint(node, state):
	return PgSphereCode(node.cooSys,
		"spoint(RADIANS(%s), RADIANS(%s))"%tuple(
			flatten(a) for a in (node.x, node.y)),
		original=node)


def _makePoly(cooSys, points, node):
# helper for _morph(Polygon|Box)
	return PgSphereCode(cooSys,
		"(SELECT spoly(q.p) FROM (VALUES %s ORDER BY column1) as q(ind,p))"%", ".join(
			'(%d, %s)'%(i, p) for i, p in enumerate(points)),
		original=node)


def _morphPolygon(node, state):
	points = ['spoint(RADIANS(%s), RADIANS(%s))'%(flatten(a[0]), flatten(a[1]))
		for a in node.coos]
	return _makePoly(node.cooSys, points, node)


def _morphBox(node, state):
	args = tuple("RADIANS(%s)"%flatten(v) for v in (
			node.x, node.width, node.y, node.height))
	points = [
		"spoint(%s-%s/2, %s-%s/2)"%args,
		"spoint(%s-%s/2, %s+%s/2)"%args,
		"spoint(%s+%s/2, %s+%s/2)"%args,
		"spoint(%s+%s/2, %s-%s/2)"%args]
	return _makePoly(node.cooSys, points, node)


def _getSystem(node):
	return getattr(node, "cooSys", None)


def _transformSystems(pgLiteral, fromSystem, toSystem):
# a helper to _booleanizeGeoPredsPGS
	if fromSystem!=toSystem:
		trafo = tapstc.getPGSphereTrafo(fromSystem, toSystem)
		if trafo is not None:
			pgLiteral = "(%s)%s"%(pgLiteral, trafo)
	return pgLiteral


def _booleanizeGeoPredsPGS(node, operator, operand):
	"""morphs contains and intersects to pgsphere expressions when
	they are arguments to a suitable comparison.
	"""
	if node.funName=="CONTAINS":
		geoOp = "@"
	elif node.funName=="INTERSECTS":
		geoOp = "&&"
	else:
		return None

	expr = None
	sys1, sys2 = _getSystem(node.args[0]), _getSystem(node.args[1])
	if isinstance(node.args[0], tapstc.GeomExpr):
		if isinstance(node.args[1], tapstc.GeomExpr):
			raise NotImplementedError("Cannot have compound regions in both"
				" arguments of a geometry predicate")
		arg2Str = _transformSystems(flatten(node.args[1]), sys1, sys2)
		expr = node.args[0].asLogic("(%%s %s (%s))"%(geoOp, arg2Str))
	elif isinstance(node.args[1], tapstc.GeomExpr):
		arg1Str = _transformSystems(flatten(node.args[0]), sys2, sys1)
		expr = node.args[0].asLogic("((%s) %s (%%s))"%(arg1Str, geoOp))
	else: # both arguments plain
		arg1Str = _transformSystems(flatten(node.args[0]), sys1, sys2)
		arg2Str = flatten(node.args[1])
		expr = "((%s) %s (%s))"%(arg1Str, geoOp, arg2Str)

	return morphhelpers.addNotToBooleanized(expr, operator, operand)


morphhelpers.registerBooleanizer("CONTAINS", _booleanizeGeoPredsPGS)
morphhelpers.registerBooleanizer("INTERSECTS", _booleanizeGeoPredsPGS)


def _computePointFunction(node, state):
	if node.funName=="COORD1":
		node.funName = "long"
		return node
	elif node.funName=="COORD2":
		node.funName = "lat"
		return node
	elif node.funName=="COORDSYS":
		if node.args[0].fieldInfo:
			cSys = tapstc.getTAPSTC(node.args[0].fieldInfo.stc)
		else:
			cSys = getattr(node.args[0], "cooSys", "UNKNOWN")
		return "'%s'"%cSys
	else:
		return node


def _distanceToPG(node, state):
	return "DEGREES((%s) <-> (%s))"%tuple(flatten(a) for a in node.args)


def _centroidToPG(node, state):
	# pgsphere right now can only to centroids of points and circles.  Try
	# to come up with a good error message otherwise.

	def _fail():
		raise PostgresMorphError("Can only compute centroids of circles and points"
			" yet.  Complain to make us implement other geometries faster.")

	arg = node.args[0]
	if hasattr(arg, "original"):
		arg = arg.original
	if arg.type=="polygon" or arg.type=="box":
		_fail()

	if getattr(arg, "fieldInfo", None):
		fi = arg.fieldInfo
		if fi.type=="spoly" or fi.type=="sbox":
			_fail()

	return "@@(%s)"%(flatten(node.args[0]))


def _areaToPGSphere(node, state):
	# pgsphere returns rad**2, adql wants deg**2
	return "3282.806350011744*%s"%flatten(node)


def _regionToPG(node, state):
# Too obscure right now.
	raise NotImplementedError("The REGION string you supplied is not"
		" supported on this server")


def _stcsRegionToPGSphere(node, state):
	# STCSRegions embed something returned by tapstc's parser.  This is
	# a pgsphere instance if we're lucky (just dump the thing as a string)
	# or a tapstc.GeomExpr object if we're unlucky -- in that case, we
	# leave the GeomExpr here and leave it to a contains or intersects
	# handler to rewrite the entire expression.
	if isinstance(node.tapstcObj, tapstc.GeomExpr):
		return node.tapstcObj
	else:
		return PgSphereCode(node.cooSys, node.tapstcObj.asPgSphere())



_geometricMorphers = {
	'circle': _morphCircle,
	'point': _morphPoint,
	'box': _morphBox,
	'polygon': _morphPolygon,
	"pointFunction": _computePointFunction,
	"distanceFunction": _distanceToPG,
	"centroid": _centroidToPG,
	"region": _regionToPG,
	"stcsRegion": _stcsRegionToPGSphere,
	"area": _areaToPGSphere,
}


########## End morphing to pgSphere



_renamedFunctions = {
	"LOG": "LN",
	"LOG10": "LOG",
	"TRUNCATE": "TRUNC",
}


def _adqlFunctionToPG(node, state):
	if node.funName in _renamedFunctions:
		node.funName = _renamedFunctions[node.funName]
	
	# ADQL lets RAND set a seed, fake this in an ugly way
	if node.funName=='RAND':
		if len(node.args)==1:
			# I suppose we should execute a separate query here with
			# a crafted call to setseed.  There's no way to do
			# that right now, and I'm not forcing it at this point since
			# the semantics in the ADQL spec are dubious anyway.
			return "random()"
		else:
			return "random()"
	
	# ADQL has two-arg TRUNCATE/ROUND -- these become expressions,
	# so we play it easy and return strings
	elif node.funName=='TRUNC' or node.funName=='ROUND':
		if len(node.args)==2:
			val, prec = flatten(node.args[0]), flatten(node.args[1])
			newTerm = nodes.Term(children=[
				node.change(args=['(%s)*10^(%s)'%(val, prec)]),
				"/",
				"10^(%s)"%prec])
			newTerm.addFieldInfo(None)
			return newTerm
	
	# ADQL SQUARE becomes a PG expression.  Again, we downgrade to a string.
	elif node.funName=='SQUARE':
		return "(%s)^2"%flatten(node.args[0])
	return node


_miscMorphers = {
	"numericValueFunction": _adqlFunctionToPG,
}

def morphMiscFunctions(tree):
	"""replaces ADQL functions with (almost) equivalent expressions from
	postgres or postgastro.

	This is a function mostly for unit tests, morphPG does these 
	transformations.
	"""
	return morphhelpers.morphTreeWithMorphers(tree, _miscMorphers)


class _PGSC(nodes.SelectNoParens):
	"""A modifield selectNoParens that fixes the syntactic differences
	between ADQL and postgres.
	"""
	def flatten(self):
		return nodes.flattenKWs(self,
			("SELECT", None),
			("", "setQuantifier"),
			("", "selectList"),
			("", "fromClause"),
			("", "whereClause"),
			("", "groupby"),
			("", "having"),
			("", "orderBy"),
			("LIMIT", "setLimit"))


class _PGQS(nodes.ADQLNode):
	"""A wrapper for a postgres query specification.  
	
	The only funciton here is to make sure there's just one LIMIT part
	at the very end (except, of course, in deeper subqueries).

	Nuking operand setLimits is already performed by _fixSetLimit below.
	"""
	type = "postgres query specification"
	_a_original = None
	_a_setLimit = None
	_a_offset = None

	def flatten(self):
		return nodes.flattenKWs(self,
			("", "original"),
			("LIMIT", "setLimit"),
			("OFFSET", "offset"))


def _insertPGSC(node, state):
	"""wraps a select clause into something that serializes to postgres.
	"""
	return _PGSC.cloneFrom(node)


def _expandStars(node, state):
	"""tries to replace all expressions with * in a select list.

	I'm forcing this because that seems easier than figuring out how
	to apply the sequencing rules from sql1992, 7.5, to joins with more
	than two operands.
	"""
	# only work if annotation has taken place (else it's probably a test
	# run anyway)
	if state.nodeStack[-1].fieldInfos:
		if node.allFieldsQuery:
			return nodes.SelectList(
				selectFields=state.nodeStack[-1].getSelectFields())
		else:
			newCols = []
			for col in node.selectFields:
				if isinstance(col, nodes.QualifiedStar):
					newCols.extend(state.nodeStack[-1].fromClause.getFieldsForTable(
						col.sourceTable))
				else:
					newCols.append(col)
			return node.change(selectFields=tuple(newCols))

	return node


def _forceAlias(node, state):
	"""forces anonymous expressions to have an alias.

	We need this as we expand stars here, and with these we need some
	way to refer to the items.
	"""
	if isinstance(node.expr, basestring):
		# this can happen if node.expr has been morphed.  Though it may be
		# silly, unconditionally add an alias (unless there already is one)
		if node.alias is None:
			node.alias = node.name
		return node

	if not isinstance(node.expr, nodes.ColumnReference) and node.alias is None:
		node.alias = node.name
	return node


def _fixSetLimit(node, state):
	"""postgres only wants a global limit on set expressions.
	"""
	for n in node.getSelectClauses():
		n.setLimit = None
	offset = node.offset
	node.offset = None
	return _PGQS(original=node, 
		setLimit=node.setLimit and str(node.setLimit),
		offset=offset)


_syntaxMorphers = {
	"selectNoParens": _insertPGSC,
	'comparisonPredicate': morphhelpers.booleanizeComparisons,
	'selectList': _expandStars,
	'derivedColumn': _forceAlias,
	"querySpecification": _fixSetLimit,
}

# Warning: if ever there are two Morphers for the same type, this will
# break, and we'll need to allow lists of Morphers (and need to think
# about their sequence...)
_allMorphers = _geometricMorphers.copy()
_allMorphers.update(_miscMorphers)
_allMorphers.update(_syntaxMorphers)


_pgMorpher = morphhelpers.Morpher(_allMorphers)

morphPG = _pgMorpher.morph
