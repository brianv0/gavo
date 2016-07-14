"""
The specialised annotations for the various entities of VO-DML.

As it's needed for the definition of models, the annotation of immediate
atoms is already defined in common; also see there for the base class
of these.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import weakref

from gavo.dm import common
from gavo.votable import V


class ColumnAnnotation(common.AnnotationBase):
	"""An annotation of a table column.

	These reference DaCHS columns.
	"""
	def __init__(self, name, column):
		common.AnnotationBase.__init__(self, name)
		self.weakref = weakref.ref(column)

	@property
	def value(self):
		return self.weakref()

	def getVOT(self, ctx):
		return V.FIELDref(ref=ctx.getOrMakeIdFor(self.value))[
			V.VODML[V.ROLE[common.completeVODMLId(ctx, self.name)]]]


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


class GroupRefAnnotation(common.AnnotationBase):
	"""An annotation always referencing a group that's not lexically
	within the parent.
	"""
	def __init__(self, name, objectReferenced):
		common.AnnotationBase.__init__(self, name)
		self.objectReferenced = objectReferenced
	
	def getVOT(self, ctx):
		if id(self.objectReferenced) not in ctx.alreadyInTree:
			ctx.getEnclosingContainer()[
				_the(# fix this: dmvot.getSubtrees(ctx, self.objectReferenced))(
					ID=ctx.getOrMakeIdFor(self.objectReferenced))]
			ctx.alreadyInTree.add(id(self.objectReferenced))

		return V.GROUP(ref=ctx.getIdFor(self.objectReferenced))[
			V.VODML[V.TYPE["vo-dml:GROUPref"]],
			V.VODML[V.ROLE[common.completeVODMLId(ctx, self.name)]]]


class ForeignKeyAnnotation(common.AnnotationBase):
	"""An annotation pointing to an annotation in a different table.

	These are constructed with the attribute name and the foreign key RD
	object.
	"""
	def __init__(self, name, fk):
		common.AnnotationBase.__init__(self, name)
		self.value = weakref.proxy(fk)

	def getVOT(self, ctx):
		# the main trouble here is: What if there's multiple foreign keys
		# into destTD?  To prevent multiple inclusions of a single
		# table, we add a reference to our serialised VOTable stan in
		# destTD's _FKR_serializedVOT attribute.  That will fail
		# if we produce two VOTables from the same table at the same time,
		# but let's worry about that later.
		
		destTD = self.value.inTable
		srcTD = self.value.parent

		pkDecl = V.GROUP[
			V.VODML[V.ROLE["vo-dml:ObjectTypeInstance.ID"]],
			[V.FIELDref(ref=ctx.getOrMakeIdFor(
					destTD.tableDef.getColumnByName(colName)))
				for colName in self.foreignKey.dest]]
		pkDecl(ID=ctx.getOrMakeIdFor(pkDecl))

		fkDecl = V.GROUP(ref=ctx.getOrMakeIdFor(pkDecl))[
			V.VODML[V.TYPE["vo-dml:ORMReference"]],
			[V.FIELDref(ref=ctx.getIdFor(srcTD.getColumnByName(colName)))
				for colName in self.foreignKey.source]]

		targetVOT = getattr(destTD, "_FKR_serializedVOT",
			lambda: None)()
		# weakrefs are None if expired
		if targetVOT is None:
			targetVOT = ctx.makeTable(destTD)
			destTD._FKR_serializedVOT = weakref.ref(targetVOT)
			ctx.getEnclosingResource()[targetVOT]
		
		targetVOT[pkDecl]

		return fkDecl
