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

import weakref

from gavo.dm import common
from gavo.dm import dmvot
from gavo.votable import V


class ColumnAnnotation(common.AnnotationBase):
	"""An annotation of a table column.

	These live in the annotations of tables and hold a reference to 
	one of the table's columns.
	"""
	def __init__(self, name=None, columnName=None):
		common.AnnotationBase.__init__(self, name)
		self.columnName = columnName
		self.default = None

	def getTree(self, ctx, parent):
		destCol = ctx.currentTable.tableDef.getColumnByName(self.columnName)
		return V.FIELDref(ref=ctx.getOrMakeIdFor(destCol))[
			V.VODML[V.ROLE[self.qualifiedRole]]]


class DataTypeAnnotation(common.AnnotationBase):
	"""An annotation of a complex value serialised  as a direct group child.
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


class GroupRefAnnotation(common.AnnotationBase):
	"""An annotation always referencing a group that's not lexically
	within the parent.
	"""
	def __init__(self, name, objectReferenced):
		common.AnnotationBase.__init__(self, name)
		self.objectReferenced = objectReferenced
	
	def getTree(self, ctx, parent):
		if id(self.objectReferenced) not in ctx.alreadyInTree:
			ctx.getEnclosingContainer()[
				_the(dmvot.getSubtrees(ctx, self.objectReferenced))(
					ID=ctx.getOrMakeIdFor(self.objectReferenced))]
			ctx.alreadyInTree.add(id(self.objectReferenced))

		return V.GROUP(ref=ctx.getIdFor(self.objectReferenced))[
			V.VODML[V.TYPE["vo-dml:GROUPref"]],
			V.VODML[V.ROLE[self.qualifiedRole]]]


class ForeignKeyRefAnnotation(common.AnnotationBase):
	"""An annotation to a table satisfying foreign keys.

	The constructor right now requires actual DaCHS ForeignKey and Table
	objects; also, the tables referenced must be within Table's parent
	Data instance.
	"""
	name = "ID"

	def __init__(self, srcTable, foreignKey):
		self.srcTable = srcTable
		self.foreignKey = foreignKey

	def getTree(self, ctx, parent):
		# the main trouble here is: What if there's multiple foreign keys
		# into destTable?  To prevent multiple inclusions of a single
		# table, we add a reference to our serialised VOTable stan in
		# destTable's _FKR_serializedVOT attribute.  That will fail
		# if we produce two VOTables from the same table at the same time,
		# but let's worry about that later.

		srcTD = self.srcTable.tableDef
		destTable = self.srcTable.parent.tables[self.foreignKey.inTable.id]

		pkDecl = V.GROUP[
			V.VODML[V.ROLE["vo-dml:ObjectTypeInstance.ID"]],
			[V.FIELDref(ref=ctx.getOrMakeIdFor(
					destTable.tableDef.getColumnByName(colName)))
				for colName in self.foreignKey.dest]]
		pkDecl(ID=ctx.getOrMakeIdFor(pkDecl))

		fkDecl = V.GROUP(ref=ctx.getOrMakeIdFor(pkDecl))[
			V.VODML[V.TYPE["vo-dml:ORMReference"]],
			[V.FIELDref(ref=ctx.getIdFor(srcTD.getColumnByName(colName)))
				for colName in self.foreignKey.source]]

		targetVOT = getattr(destTable, "_FKR_serializedVOT",
			lambda: None)()
		# weakrefs are None if expired
		if targetVOT is None:
			targetVOT = ctx.makeTable(destTable)
			destTable._FKR_serializedVOT = weakref.ref(targetVOT)
			ctx.getEnclosingResource()[targetVOT]
		
		targetVOT[pkDecl]

		return fkDecl


################### utilities

def addFKAnnotations(table):
	"""adds annotations on foreign keys to from table's definition
	as necessary.

	A foreign key will be declared if the destination table is part of the
	enclosing data and if all columns of the foreign key are part of an
	annotation.
	"""
	fks = {}
	for fk in table.tableDef.foreignKeys:
		fks[frozenset(fk.source)] = fk
	if not fks:
		return

	for ann in common.getAnnotations(table.tableDef):
		colsInAnn = set(role.columnName for role in ann.itervalues()
			if isinstance(role, ColumnAnnotation))
		for cols in fks:
			if not cols-colsInAnn:
				# All FK columns are in current annotation
				ann.addRole(ForeignKeyRefAnnotation(table, fks[cols]))
