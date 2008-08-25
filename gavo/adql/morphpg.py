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

def _handleContains(node, state):
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


def insertQ3Calls(node):
	"""detects CONTAINS calls q3c can evidently handle and replaces them
	with q3c function calls.

	Basically, it looks for contains(point, [Circle,Rectangle,Polygon])
	calls.

	This has to run *before* morphPG.
	"""
	state = morphhelpers.State()
	def traverse(node):
		for c in node.iterNodes():
			traverse(c)
		if node.type=="regionFunction" and node.funName.upper()=="CONTAINS":
			_handleContains(node, state)
		if node.type=="comparisonPredicate":
			morphhelpers.killGeoBooleanOperator(node, state)
	traverse(node)

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
				" in postgres.  Only literals are allowed.")
	node.type = "psqlLiteral"
	node.children = ["'%s'::polygon"%", ".join(node.args[1:])]

def _morphRegionFunction(node, state):
	if node.funName.upper()=="CONTAINS":
		node.children = ["(%s) ~ (%s)"%(node.args[0], node.args[1])]
	elif node.funName.upper()=="INTERSECTS":
		node.children = ["(%s) ?# (%s)"%(node.args[0], node.args[1])]
	else:
		return  # Leave mess to someone else
	node.type = "psqlLiteral"
	state.killParentOperator = True


_handlers = {
	'circle': _morphCircle,
	'point': _morphPoint,
	'rectangle': _morphRectangle,
	'polygon': _morphPolygon,
	'regionFunction': _morphRegionFunction,
	'comparisonPredicate': morphhelpers.killGeoBooleanOperator,
}


def morphGeometries(tree):
	"""replaces ADQL geometry expressions with postgres geometry
	expressions.

	WARNING: We do not do anything about coordinate systems yet.
	"""
	state = morphhelpers.State()
	def traverse(node):
		for child in node.iterNodes():
			traverse(child)
		if node.type in _handlers:
			_handlers[node.type](node, state)
	traverse(tree)


def morphPG(tree):
	"""replaces all expressions in ADQL not palatable to postgres with
	more-or less equivalent postgress expressions.

	tree is the result of an adql.parseToTree call.
	"""
	morphGeometries(tree)
