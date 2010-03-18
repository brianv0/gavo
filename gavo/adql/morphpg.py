"""
Morphing ADQL into queries that postgres can understand.

Basically, Postgres support most of the stuff out of the box, and it's
just a matter of syntax.

However, we use BOXes internally.  When formatting results, we cannot use
them since there are already rules on how to deserialize them, which is bad
for when we need to format geometries in result columns.  So, for
geometries, we only use POINT, CIRCLE, and POLYGON, mapping RECTANGLEs
to POLYGONs.

There's also code to replace certain CONTAINS calls with q3c function
calls.
"""

import re

from gavo.adql import morphhelpers
from gavo.adql import nodes
from gavo.adql.nodes import flatten


class PostgresMorphError(morphhelpers.MorphError):
	pass


######## Begin q3c specials

def _containsToQ3c(node, state):
	if node.funName!='CONTAINS':
		return node
	args = node.args
	if len(args)!=2 or nodes.getType(args[0])!="point":
		return node
	p, shape = args
	if shape.type=="circle":
		state.killParentOperator = True
		return ("q3c_join(%s, %s, %s, %s, %s)"%tuple(map(nodes.flatten, 
			(shape.x, shape.y, p.x, p.y, shape.radius))))
	elif shape.type=="rectangle":
		state.killParentOperator = True
		return ("q3c_poly_query(%s, %s, ARRAY[%s, %s, %s, %s,"
			" %s, %s, %s, %s])"%tuple(map(nodes.flatten, (p.x, p.y,
				shape.x0, shape.y0,
				shape.x0, shape.y1,
				shape.x1, shape.y1,
				shape.x1, shape.y0))))
	elif shape=="polygon":
		state.killParentOperator = True
		return "q3c_poly_query(%s, %s, ARRAY[%s])"%(
			nodes.flatten(p.x), nodes.flatten(p.y), ",".join([
				"%s,%s"%(nodes.flatten(x), nodes.flatten(y)) for x,y in shape.coos]))
	else:
		return node


# These have to be applied *before* PG morphing
_q3Morphers = {
	'predicateGeometryFunction': _containsToQ3c,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
}


# The following detects CONTAINS calls q3c can evidently handle and replaces
# them with q3c function calls.
#
#	Basically, it looks for contains(point, [Circle,Rectangle,Polygon]) calls.
#
#	This has to run *before* morphPG.

insertQ3Calls = morphhelpers.Morpher(_q3Morphers).morph

######### End q3c specials


def _morphCircle(node, state):
	return "CIRCLE(POINT(%s, %s), %s)"%tuple(flatten(a)
		for a in (node.x, node.y, node.radius))

def _morphPoint(node, state):
	return "POINT(%s, %s)"%tuple(flatten(a) 
		for a in (node.x, node.y))

def _morphRectangle(node, state):
	return "POLYGON(BOX(%s, %s, %s, %s))"%tuple(flatten(a)
		for a in (node.x0, node.y0, node.x1, node.y1))

# SUCK, SUCK -- we don't actually check for these any more.  Move to
# pgsphere, and quick.
_cooLiteral = re.compile("[0-9]*(\.([0-9]*([eE][+-]?[0-9]*)?)?)?,.*$")

def _morphPolygon(node, state):
# Postgresql doesn't seem to support construction of polygons from lists of
# points or similar.  We need to construct it using literal syntax, i.e.,
# expressions are forbidden.
	flArgs = [flatten(a[0])+", "+flatten(a[1]) for a in node.coos]
	for a in flArgs:
		if not _cooLiteral.match(a):
			raise PostgresMorphError("%s is not a valid argument to polygon"
				" in postgres.  Only literals are allowed."%a)
	return "'%s'::polygon"%", ".join(flArgs)

def _morphGeometryPredicate(node, state):
	if node.funName=="CONTAINS":
		state.killParentOperator = True
		return "(%s) ~ (%s)"%(flatten(node.args[0]), flatten(node.args[1]))
	elif node.funName=="INTERSECTS":
		state.killParentOperator = True
		return "(%s) ?# (%s)"%(flatten(node.args[0]), flatten(node.args[1]))
	else:
		return node # Leave mess to someone else


_geoMorphers = {
	'circle': _morphCircle,
	'point': _morphPoint,
	'rectangle': _morphRectangle,
	'polygon': _morphPolygon,
	'predicateGeometryFunction': _morphGeometryPredicate,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
}


def morphGeometries(tree):
	"""replaces ADQL geometry expressions with postgres geometry
	expressions.

	WARNING: We do not do anything about coordinate systems yet.

	This is a function mostly for unit tests, morphPG does these 
	transformations.
	"""
	return morphhelpers.morphTreeWithMorphers(tree, _geoMorphers)


def _pointFunctionToIndexExpression(node, state):
	if node.funName=="COORD1":
		assert len(node.args)==1
		return "(%s)[0]"%flatten(node.args[0])
	elif node.funName=="COORD2":
		assert len(node.args)==1
		return "(%s)[1]"%flatten(node.args[0])
	elif node.funName=="COORDSYS":
		try:
			cSys = repr(node.args[0].fieldInfo.stc.spaceFrame.refFrame)
		except AttributeError: # bad field info, give up
			cSys = "'NULL'"
		return cSys
	else:
		return node


def _areaToPG(node, state):
# postgres understands AREA, but of course the area is wrong, so:
# XXX TODO: do spherical geometry here.
	state.warnings.append("AREA is currently calculated in a plane"
		" approximation.  AREAs will be severely wrong for larger shapes.")
	return node


def _distanceToPG(node, state):
# We need the postgastro extension here.
	return "celDistPP(%s, %s)"%tuple(flatten(a) for a in node.args)


def _centroidToPG(node, state):
# XXX TODO: figure out if the (planar) centers computed by postgres are
# badly off and replace with spherical calculation if so.
	return "center(%s)"%(flatten(node.args[0]))


def _regionToPG(node, state):
# This one is too dangerous for me.  Maybe I'll allow STC/s expressions
# here at some point
	raise NotImplementedError("REGION is not supported on this server.")


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


def _stcRegionToPGSphere(node, state):
	# We only look at areas[0] -- maybe we should allow points, too?
	area = node.stc.areas[0]
# XXX TODO: Go on here.

_miscMorphers = {
	"pointFunction": _pointFunctionToIndexExpression,
	"area": _areaToPG,
	"distanceFunction": _distanceToPG,
	"centroid": _centroidToPG,
	"region": _regionToPG,
	"numericValueFunction": _adqlFunctionToPG,
	"stcRegion": _stcRegionToPGSphere,
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
_allMorphers = _geoMorphers.copy()
_allMorphers.update(_miscMorphers)
_allMorphers.update(_syntaxMorphers)


_pgMorpher = morphhelpers.Morpher(_allMorphers)

morphPG = _pgMorpher.morph
