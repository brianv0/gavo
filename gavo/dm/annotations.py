"""
The specialised annotations for the various entities of VO-DML.

As it's needed for the definition of models, the annotation of immediate
atoms is already defined in common; also see there for the base class
of these.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

from gavo.dm import common
from gavo.dm import votablewrite
from gavo.votable import V


class ColumnAnnotation(common.AnnotationBase):
	"""An annotation of a table column.

	These live in tables and hold a reference to one of the table's
	columns.
	"""
	def __init__(self, name, columnName):
		common.AnnotationBase.__init__(self, name)
		self.columnName = columnName

	def getTree(self, ctx, parent):
		destCol = parent.getColumnByName(self.columnName)
		return V.FIELDref(ref=ctx.getOrMakeIdFor(destCol))[
			V.VODML[V.ROLE[self.qualifiedRole]]]


class DataTypeAnnotation(common.AnnotationBase):
	"""An annotation of a complex value without identitiy.
	"""
	def __init__(self, name, typeName):
		common.AnnotationBase.__init__(self, name)
		self.typeName = typeName


def _the(gen):
	"""returns the first thing the generator gen spits out and makes sure 
	there's nothing more
	"""
	res = gen.next()
	try:
		extra = gen.next()
	except StopIteration:
		return res
	raise TypeError("Generator expected to only return one thing returned"
		" extra %s"%repr(extra))


class SingletonRefAnnotation(common.AnnotationBase):
	"""An annotation always referencing the same object.
	"""
	def __init__(self, name, objectReferenced):
		common.AnnotationBase.__init__(self, name)
		self.objectReferenced = objectReferenced
	
	def getTree(self, ctx, parent):
		if id(self.objectReferenced) not in ctx.alreadyInTree:
			ctx.getEnclosingContainer()[
				_the(votablewrite.getSubtrees(ctx, self.objectReferenced))(
					ID=ctx.getOrMakeIdFor(self.objectReferenced))]
			ctx.alreadyInTree.add(id(self.objectReferenced))

		return V.GROUP(ref=ctx.getIdFor(self.objectReferenced))[
			V.VODML[V.ROLE[self.qualifiedRole]]]

