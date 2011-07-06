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

import re

from gavo.adql import morphhelpers
from gavo.adql import nodes
from gavo.adql.nodes import flatten
from gavo.stc import tapstc


class PostgresMorphError(morphhelpers.MorphError):
	pass


######## Begin q3c specials

def _containsToQ3c(node, state):
	if node.funName!='CONTAINS':
		return node
	args = node.args

	# leave morphing to someone else if we don't check for point in shape
	# or if system transformations are required.
	if len(args)!=2 or nodes.getType(args[0])!="point":
		return node
	if not hasattr(args[0], "cooSys") or not hasattr(args[1], "cooSys"):
		# arguments do not look like geometries; leave it to someone else
		# to blow up
		return node
	if tapstc.getPGSphereTrafo(args[0].cooSys, args[1].cooSys) is not None:
		# we'll need a transform; q3c cannot do this.
		return node

	p, shape = args
	if shape.type=="circle":
		state.killParentOperator = True
		# The pg planner works much smoother if you have constants first.
		if p.x.type=='columnReference':
			return ("q3c_join(%s, %s, %s, %s, %s)"%tuple(map(nodes.flatten, 
				(shape.x, shape.y, p.x, p.y, shape.radius))))
		else:
			return ("q3c_join(%s, %s, %s, %s, %s)"%tuple(map(nodes.flatten, 
				(p.x, p.y, shape.x, shape.y, shape.radius))))
	elif shape=="polygon":
		state.killParentOperator = True
		return "q3c_poly_query(%s, %s, ARRAY[%s])"%(
			nodes.flatten(p.x), nodes.flatten(p.y), ",".join([
				"%s,%s"%(nodes.flatten(x), nodes.flatten(y)) for x,y in shape.coos]))
	else:
		return node


_q3Morphers = {
	'predicateGeometryFunction': _containsToQ3c,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
}


#	This has to run *before* morphPG.
insertQ3Calls = morphhelpers.Morpher(_q3Morphers).morph


######### End q3c specials



######### Begin morphing to pgSphere


class PgSphereCode(object):
	"""A node that contains serialized pgsphere expressions plus
	a coordinate system id for cases in which we must conform.
	"""
	type = "pgsphere literal"

	def __init__(self, cooSys, content):
		self.cooSys, self.content = cooSys, content
	
	def flatten(self):
		return self.content


def _morphCircle(node, state):
	return PgSphereCode(node.cooSys,
		"scircle(spoint(RADIANS(%s), RADIANS(%s)), RADIANS(%s))"%tuple(flatten(a)
			for a in (node.x, node.y, node.radius)))


def _morphPoint(node, state):
	return PgSphereCode(node.cooSys,
		"spoint(RADIANS(%s), RADIANS(%s))"%tuple(
			flatten(a) for a in (node.x, node.y)))


def _makePoly(cooSys, points):
# helper for _morph(Polygon|Box)
	return PgSphereCode(cooSys,
		"(SELECT spoly(q.p) FROM (VALUES %s ORDER BY column1) as q(ind,p))"%", ".join(
			'(%d, %s)'%(i, p) for i, p in enumerate(points)))


def _morphPolygon(node, state):
	points = ['spoint(RADIANS(%s), RADIANS(%s))'%(flatten(a[0]), flatten(a[1]))
		for a in node.coos]
	return _makePoly(node.cooSys, points)


def _morphBox(node, state):
	args = tuple("RADIANS(%s)"%flatten(v) for v in (
			node.x, node.width, node.y, node.height))
	points = [
		"spoint(%s-%s/2, %s-%s/2)"%args,
		"spoint(%s-%s/2, %s+%s/2)"%args,
		"spoint(%s+%s/2, %s+%s/2)"%args,
		"spoint(%s+%s/2, %s-%s/2)"%args]
	return _makePoly(node.cooSys, points)


def _getSystem(node):
	return getattr(node, "cooSys", None)


def _transformSystems(pgLiteral, fromSystem, toSystem):
# a helper to _morphGeometryPredicate
	if fromSystem!=toSystem:
		trafo = tapstc.getPGSphereTrafo(fromSystem, toSystem)
		if trafo is not None:
			pgLiteral = "(%s)%s"%(pgLiteral, trafo)
	return pgLiteral


def _morphGeometryPredicate(node, state):
	if node.funName=="CONTAINS":
		state.killParentOperator = True
		operator = "@"
	elif node.funName=="INTERSECTS":
		state.killParentOperator = True
		operator = "&&"
	else:
		return node # Leave mess to someone else

	sys1, sys2 = _getSystem(node.args[0]), _getSystem(node.args[1])
	if isinstance(node.args[0], tapstc.GeomExpr):
		if isinstance(node.args[1], tapstc.GeomExpr):
			raise NotImplementedError("Cannot have compound regions in both"
				" arguments of a geometry predicate")
		arg2Str = _transformSystems(flatten(node.args[1]), sys1, sys2)
		return node.args[0].asLogic("%%s %s (%s)"%(operator, arg2Str))
	elif isinstance(node.args[1], tapstc.GeomExpr):
		arg1Str = _transformSystems(flatten(node.args[0]), sys2, sys1)
		return node.args[0].asLogic("(%s) %s (%%s)"%(arg1Str, operator))
	else: # both arguments plain
		arg1Str = _transformSystems(flatten(node.args[0]), sys1, sys2)
		arg2Str = flatten(node.args[1])
		return "(%s) %s (%s)"%(arg1Str, operator, arg2Str)



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
	return "(%s) <-> (%s)"%tuple(flatten(a) for a in node.args)


def _centroidToPG(node, state):
	return "@@(%s)"%(flatten(node.args[0]))


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



_pgsphereMorphers = {
	'circle': _morphCircle,
	'point': _morphPoint,
	'box': _morphBox,
	'polygon': _morphPolygon,
	'predicateGeometryFunction': _morphGeometryPredicate,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
	"pointFunction": _computePointFunction,
	"distanceFunction": _distanceToPG,
	"centroid": _centroidToPG,
	"region": _regionToPG,
	"stcsRegion": _stcsRegionToPGSphere,
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
			return "setseed(%s)-setseed(%s)+random()"%(flatten(node.args[0]),
				flatten(node.args[0]))
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



def _removeUploadSchema(node, state):
	"""removes TAP_UPLOAD schema specs.

	This assumes TAP_UPLOADs are handled via temporary tables.  If that
	is not true any more, this needs to be exposed to client code.

	node is a TableName.
	"""
	if node.schema and node.schema.upper()=="TAP_UPLOAD":
		return node.name
	else:
		return node


_miscMorphers = {
	"numericValueFunction": _adqlFunctionToPG,
	"tableName": _removeUploadSchema,
}

def morphMiscFunctions(tree):
	"""replaces ADQL functions with (almost) equivalent expressions from
	postgres or postgastro.

	This is a function mostly for unit tests, morphPG does these 
	transformations.
	"""
	return morphhelpers.morphTreeWithMorphers(tree, _miscMorphers)


class _PGQS(nodes.QuerySpecification):
	_a_offset = None
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
			("LIMIT", "setLimit"),
			("OFFSET", "offset"))


def _insertPGQS(node, state):
	"""wraps a query specification into a query spec that serializes to postgres.
	
	This will turn TOP and ALL into LIMIT and OFFSET 0.

	Turning ALL into OFFSET 0 is a bad hack, but we need some way to let
	people specify the OFFSET 0, and this is probably the least intrusive
	one.
	"""
	offset = None
	if node.setQuantifier and node.setQuantifier.lower()=="all":
		offset = "0"
	res = _PGQS.cloneFrom(node, offset=offset)
	return res


_syntaxMorphers = {
	"querySpecification": _insertPGQS,
}

# Warning: if ever there are two Morphers for the same type, this will
# break, and we'll need to allow lists of Morphers (and need to think
# about their sequence...)
_allMorphers = _pgsphereMorphers.copy()
_allMorphers.update(_miscMorphers)
_allMorphers.update(_syntaxMorphers)


_pgMorpher = morphhelpers.Morpher(_allMorphers)

morphPG = _pgMorpher.morph
