"""
Writing DM instances into VOTables.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo import votable
from gavo.dm import common
from gavo.votable import V


def getSubtrees(ctx, ob):
	"""yields an xmlstan trees of VOTable elements for all annotations
	of an arbitrary ob.
	"""
	for ann in common.getAnnotations(ob):
		ctx.vodmlModels.add(ann.model)
		res = V.GROUP()
		if ann.typeName:
			res[V.VODML[V.TYPE[ann.qTypeName]]]

		for name, itemAnn in ann.iteritems():
			if isinstance(itemAnn, common.Annotation):
				res[_getTreeForAtom(ctx, getattr(ob, name), itemAnn)]

			elif isinstance(itemAnn, common.ColumnAnnotation):
				res[_getTreeForColumnref(ctx, ob, itemAnn)]

			else:
				res[getSubtrees(ctx, getattr(ob, name))]
		
		yield res


def _getTreeForColumnref(ctx, table, annotation):
	destCol = table.getColumnByName(annotation.columnName)
	return V.FIELDref(ref=ctx.getOrMakeIdFor(destCol))[
		V.VODML[V.ROLE[annotation.qualifiedRole]]]

def _getTreeForAtom(ctx, ob, itemAnn):
	"""returns a VO-DML-compliant param for ob within annotation.
	"""
	attrs = votable.guessParamAttrsForValue(ob)
	attrs.update({
		"unit": itemAnn.unit,
		"ucd": itemAnn.ucd})

	param = V.PARAM(name=itemAnn.name,
		id=ctx.getOrMakeIdFor(ob), **attrs)[
			V.VODML[V.ROLE[itemAnn.qualifiedRole]]]
	votable.serializeToParam(param, ob)
	return param


def declareDMs(ctx, stan):
	"""adds the data models mentioned  in ctx to the root element of an
	xmlstan tree.
	"""
	# vo-dml must always be the first model defined
	stan[getSubtrees(ctx, common.VODMLModel)]

	for model in ctx.vodmlModels:
		if model!=common.VODMLModel:
			stan[getSubtrees(ctx, model)]


def getTree(ctx, ob):
	"""returns an xmlstan VOTable serialising ob.

	TODO: I guess this should go, as getSubtrees is called from
	formats.votablewrite.
	"""
	children = list(getSubtrees(ctx, ob))

	res = V.VOTABLE()

	declareDMs(ctx, res)
	
	return res[
		V.RESOURCE[
			children,
			[storedElement
				for storedElement in ctx.storedElements]]]


def asString(ctx, ob):
	"""returns the annotated object ob as a serialised VOTable.

	ctx must be a votablewrite.VOTableContext
	TODO: strike, I guess.
	"""
	tree = getTree(ctx, ob)
	return votable.asString(tree)
