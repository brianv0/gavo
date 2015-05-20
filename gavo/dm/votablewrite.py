"""
Writing DM instances into VOTables.

This for now depends on gavo.formats and hence the whole DaCHS package.
Let's see if we can clean this up later.
"""

# TODO: actually do something about object serialisation; infer types
# from python values, etc.


#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo import votable
from gavo.dm import common
from gavo.formats import votablewrite
from gavo.votable import V


def getSubtree(ob, ctx):
	"""returns an xmlstan tree of VOTable elements for an annotated object ob.
	"""
	ann = common.getAnnotations(ob)
	assert ann

	ctx.vodmlModels.add(ann.model)
	res = V.GROUP()
	if ann.typeName:
		res[V.VODML[V.TYPE[ann.qTypeName]]]

	for name, itemAnn in ann.iteritems():
		val = getattr(ob, name)

		if common.getAnnotations(val) is None:
			res[_getTreeForAtom(val, itemAnn, name, ctx)]
		else:
			res[getTree(ob, ctx)]
	
	return res


def _getTreeForAtom(ob, itemAnn, role, ctx):
	"""returns a VO-DML-compliant param for ob within annotation.
	"""
	attrs = votable.guessParamAttrsForValue(ob)
	attrs.update({
		"unit": itemAnn.unit,
		"ucd": itemAnn.ucd})

	param = V.PARAM(name=role,
		id=ctx.getOrMakeIdFor(ob), **attrs)[
			V.VODML[V.ROLE[itemAnn.qualifiedRole]]]
	votable.serializeToParam(param, ob)
	return param


def getTree(ob, ctx):
	"""returns an xmlstan VOTable serialising ob.
	"""
	child = getSubtree(ob, ctx)

	res = V.VOTABLE()

	# vo-dml must always be the first model defined
	res[getSubtree(common.VODMLModel, ctx)]

	for model in ctx.vodmlModels:
		if model!=common.VODMLModel:
			res[getSubtree(model, ctx)]
	
	return res[
		V.RESOURCE[
			child,
			[child[storedElement]
				for storedElement in ctx.storedElements]]]


def asString(ob, ctx=None):
	"""returns the annotated object ob as a serialised VOTable.
	"""
	if ctx is None:
		ctx = votablewrite.VOTableContext()

	# Furnish the normal context with some extra attributes we need for DM
	# serialisation (TODO: merge into "normal" context)
	# * space to memorise models used within the document.
	ctx.vodmlModels = set([common.VODMLModel])
	# * a sequence of xmlstan that should be appended to some container
	#   (used by dm, and subject to change for now)
	ctx.storedElements = []

	tree = getTree(ob, ctx)
	return votable.asString(tree)
