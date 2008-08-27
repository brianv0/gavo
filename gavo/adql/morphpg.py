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


class PostgresMorphError(morphhelpers.MorphError):
	pass


######## Bein q3c specials

def _containsToQ3c(node, state):
	if node.funName!='CONTAINS':
		return
	args = [c for c in node.iterNodes()]
	if len(args)!=2 or args[0].type!="point":
		return
	p, shape = args
	if shape.type=="circle":
		node.children = ["q3c_radial_query(%s, %s, %s, %s, %s)"%(
			p.x, p.y, shape.x, shape.y, shape.radius)]
	elif shape.type=="rectangle":
		node.children = ["q3c_poly_query(%s, %s, ARRAY[%s, %s, %s, %s,"
			" %s, %s, %s, %s])"%(p.x, p.y,
				shape.x0, shape.y0,
				shape.x0, shape.y1,
				shape.x1, shape.y1,
				shape.x1, shape.y0)]
	elif shape=="polygon":
		node.children = ["q3c_poly_query(%s, %s, ARRAY[%s])"%(
			p.x, p.y, ",".join(["%s,%s"%pt for pt in shape.coos]))]
	else:
		return # unknown shape type, leave mess to postgres
	node.type  = "psqlLiteral"
	state.killParentOperator = True


# These have to be applied *before* PG morphing
_q3Handlers = {
	'predicateGeometryFunction': _containsToQ3c,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
}


def insertQ3Calls(tree):
	"""detects CONTAINS calls q3c can evidently handle and replaces them
	with q3c function calls.

	Basically, it looks for contains(point, [Circle,Rectangle,Polygon])
	calls.

	This has to run *before* morphPG.
	"""
	morphhelpers.morphTreeWithHandlers(tree, _q3Handlers)

######### End q3c specials


def _morphCircle(node, state):
	assert len(node.args)==4
	node.type = "psqlLiteral"
	node.children = ["CIRCLE(POINT(%s, %s), %s)"%tuple([nodes.flatten(a)
		for a in node.args[1:]])]

def _morphPoint(node, state):
	assert len(node.args)==3
	node.type = "psqlLiteral"
	node.children = ["POINT(%s, %s)"%tuple([nodes.flatten(a) 
		for a in node.args[1:]])]

def _morphRectangle(node, state):
	assert len(node.args)==5
	node.type = "psqlLiteral"
	node.children = ["POLYGON(BOX(%s, %s, %s, %s))"%tuple([nodes.flatten(a)
		for a in node.args[1:]])]

_cooLiteral = re.compile("[0-9]*(\.([0-9]*([eE][+-]?[0-9]*)?)?)?$")

def _morphPolygon(node, state):
# Postgresql doesn't seem to support construction of polygons from lists of
# points or similar.  We need to construct it using literal syntax, i.e.,
# expressions are forbidden.
	for a in node.args[1:]:
		if not _cooLiteral.match(a):
			raise PostgresMorphError("%s is not a valid argument to polygon"
				" in postgres.  Only literals are allowed."%a)
	node.type = "psqlLiteral"
	node.children = ["'%s'::polygon"%", ".join(node.args[1:])]

def _morphGeometryPredicate(node, state):
	if node.funName=="CONTAINS":
		node.children = ["(%s) ~ (%s)"%(node.args[0], node.args[1])]
	elif node.funName=="INTERSECTS":
		node.children = ["(%s) ?# (%s)"%(node.args[0], node.args[1])]
	else:
		return  # Leave mess to someone else
	node.type = "psqlLiteral"
	state.killParentOperator = True


_geoHandlers = {
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
	morphhelpers.morphTreeWithHandlers(tree, _geoHandlers)


def _pointFunctionToIndexExpression(node, state):
	if node.funName=="COORD1":
		assert len(node.args)==1
		node.children = ["(%s)[0]"%node.args[0]]
	elif node.funName=="COORD2":
		assert len(node.args)==1
		node.children = ["(%s)[1]"%node.args[0]]
	elif node.funName=="COORDSYS":
		# argument is either a geometry expression (take coosys from there)
		# or a column reference (which we can resolve if fieldInfos have
		# been added).
		assert len(node.args)==1
		try:
			if node.children[2].type=="columnReference":
				cSys = node.children[2].fieldInfo.cooSys
			else:
				cSys = node.children[2].cooSys
		except AttributeError: # probably no attached field infos, little I can do.
			cSys = 'unknown'
		node.children = ["'%s'"%(re.sub("[^\w]+", "", cSys))]  # sanitize cSys
	else:
		return   # Can't handle
	node.type = "psqlLiteral"


def _areaToPG(node, state):
# postgres understands AREA, but of course the area is wrong, so:
# XXX TODO: do spherical geometry here.
	state.warnings.append("AREA is currently calculated in a plane"
		" approximation.  AREAs will be severely wrong for larger shapes.")


def _distanceToPG(node, state):
# We need the postgastro extension here.
	node.children = ["celDistPP(%s, %s)"%tuple(node.args)]
	node.type = "psqlLiteral"


def _centroidToPG(node, state):
# XXX TODO: figure out if the (planar) centers computed by postgres are
# badly off and replace with spherical calculation if so.
	node.children = ["center(%s)"%(node.args[0])]
	node.type = "psqlLiteral"


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
		node.children = [_renamedFunctions[node.funName]]+node.children[1:]
	elif node.funName=='RAND':
		if len(node.args)==1:
			node.children = ["setseed(%s)-setseed(%s)+random()"%(node.args[0],
				node.args[0])]
		else:
			node.children = ["random()"]
		node.type = "psqlLiteral"
	elif node.funName=='SQUARE':
		node.children = ["(%s)^2"%node.args[0]]
		node.type = "psqlLiteral"


_miscHandlers = {
	"pointFunction": _pointFunctionToIndexExpression,
	"area": _areaToPG,
	"distanceFunction": _distanceToPG,
	"centroid": _centroidToPG,
	"region": _regionToPG,
	"numericValueFunction": _adqlFunctionToPG,
}

def morphMiscFunctions(tree):
	"""replaces ADQL functions with (almost) equivalent expressions from
	postgres or postgastro.

	This is a function mostly for unit tests, morphPG does these 
	transformations.
	"""
	morphhelpers.morphTreeWithHandlers(tree, _miscHandlers)


def _topToLimit(node, state):
	for index, c in enumerate(node.children):
		if nodes.getType(c)=="setLimit":
			break
	else:
		return
	node.children = list(node.children)
	del node.children[index]
	node.children.extend(["LIMIT", c.limit])

_syntaxHandlers = {
	"querySpecification": _topToLimit,
}

# Warning: if ever there are two handlers for the same type, this will
# break, and we'll need to allow lists of handlers (and need to think
# about their sequence...)
_allHandlers = _geoHandlers.copy()
_allHandlers.update(_miscHandlers)
_allHandlers.update(_syntaxHandlers)


def morphPG(tree):
	"""replaces all expressions in ADQL not palatable to postgres with
	more-or less equivalent postgress expressions.

	tree is the result of an adql.parseToTree call.
	"""
	morphhelpers.morphTreeWithHandlers(tree, _allHandlers)
