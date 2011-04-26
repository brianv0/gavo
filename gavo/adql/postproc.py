"""
Operations on annotated ADQL trees done by parseAnnotated.

These can be considered "bug fixes" for ADQL, where we try to
make the parse tree more suitable for later translation into
SQL.
"""

from gavo.adql import morphhelpers


############## INTERSECTS to CONTAINS
# Unfortunately, the ADQL spec mandates that any INTERSECTS with a
# POINT argument should be treated as if it were CONTAINs with
# arguments swapped as required.  This morphing code tries to do 
# this before translation.  One major reason to do this within
# the translation layer rather than relying on the SQL code
# generation is that probably all generators profit from knowing
# that there's a special case "point within <geometry>".

def _intersectsWithPointToContains(node, state):
	if node.funName=='INTERSECTS':
		print ">>>>", node.args[0].fieldInfo
		print ">>>>", node.args[1].fieldInfo
	return node
	

_builtinMorphs = {
	'predicateGeometryFunction': _intersectsWithPointToContains,
}

_morpher = morphhelpers.Morpher(_builtinMorphs)

builtinMorph = _morpher.morph

