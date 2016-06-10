"""
Common code for new-style Data Model support.

In particular, this defines a hierachy of Annotation objects.  The annotation
of DaCHS tables is an ObjectAnnotation, the other Annotation classes
(conceptually, all are key-value pairs) make up their inner structure.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

import re

from gavo import votable
from gavo.votable import V


VODML_NAME = "vo-dml"


def parseTypeName(typename):
	"""returns modelname, package (None for the empty package), name
	for a VO-DML type name.

	Malformed names raise a ValueError.

	>>> parseTypeName("dm:type")
	('dm', None, 'type')
	>>> parseTypeName("dm:pck.type")
	('dm', 'pck', 'type')
	>>> parseTypeName(":malformed.typeid")
	Traceback (most recent call last):
	ValueError: ':malformed.typeid' is not a valid VO-DML type name
	"""
	mat = re.match("([\w_-]+):(?:([\w_-]+)\.)?([\w_-]+)", typename)
	if not mat:
		raise ValueError("'%s' is not a valid VO-DML type name"%typename)
	return mat.groups()


class AnnotationBase(object):
	"""A base class for of structs.

	Basically, these are pairs of a role name and something else, which
	depends on the actual subclass (e.g., an atomic value, a reference,
	a sequence of key-value pairs, a sequence of other objects, ...).

	They have a method getVOT(ctx) -> xmlstan, which, using a
	votablewrite.Context ctx, will return mapping-document conformant VOTable
	xmlstand.

	Use asSIL() to retrieve a simple string representation.

	Compund annotations (sequences, key-value pairs) should use
	add(thing) to build themselves up.

	AnnotationBase is abstract and doesn't implement some of these methods.
	"""
	def __init__(self, name):
		self.name = name

	def getVOT(self, ctx):
		raise NotImplementedError("%s cannot be serialised (override getVOT)."%
			self.__class__.__name__)

	def asSIL(self):
		raise NotImplementedError("%s cannot be serialised (override asSIL)."%
			self.__class__.__name__)

	def add(self, thing):
		raise ValueError(
			"%s is not a compound annotation."%self.__class__.__name__)

	def iterNodes(self):
		yield self


class AtomicAnnotation(AnnotationBase):
	"""An annotation of an atomic value, i.e., a key-value pair.

	These can take optional metadata.
	"""
	def __init__(self, name=None, value=None, unit=None, ucd=None):
		AnnotationBase.__init__(self, name)
		self.value, self.unit, self.ucd = value, unit, ucd

	def getVOT(self, ctx):
		attrs = votable.guessParamAttrsForValue(self.value)
		attrs.update({
			"unit": self.unit,
			"ucd": self.ucd})

		param = V.PARAM(name=self.name,
			id=ctx.getOrMakeIdFor(self.value), **attrs)[
				V.VODML[V.ROLE[self.name]]]
		votable.serializeToParam(param, self.value)
		return param

	def asSIL(self):
		return "%s: %s"%(self.name, self.value.asSIL())


class _AttributeGroupAnnotation(AnnotationBase):
	"""An internal base class for DatatypeAnnotation and ObjectAnnotation.
	"""
	def __init__(self, name, type):
		AnnotationBase.__init__(self, name)
		self.type = type
		self.modelPrefix, _, _ = parseTypeName(type)
		self.childRoles = {}
	
	def add(self, role):
		assert role.name not in self.childRoles
		self.childRoles[role.name] = role

	def asSIL(self, suppressType=False):
		if suppressType:
			typeAnn = ""
		else:
			typeAnn = "(%s) "%self.type

		return "%s{\n  %s}\n"%(typeAnn,
			"\n  ".join(r.asSIL() for r in self.childRoles.values()))

	def _makeVOTGroup(self, ctx):
		"""helps getVOT.
		"""
		return V.GROUP[
			V.VODML[V.TYPE[self.type]], [ann.getVOT(ctx)
				for ann in self.childRoles.values()]]

	def getVOT(self, ctx):
		ctx.addVODMLPrefix(self.modelPrefix)
		group = self._makeVOTGroup(ctx)
		ctx.getEnclosingResource()[group]
		if self.name is not None:
			# group in an attribute: return a reference to it
			ctx.makeIdFor(self)
			ctx.addID(self, group)
			return V.GROUP(ref=group.ID)[
				V.VODML[V.ROLE[self.name]]]


class DatatypeAnnotation(_AttributeGroupAnnotation):
	"""An annotation for a datatype.

	Datatypes are essentially simple groups of attributes; they are used
	*within* objects (e.g., to group photometry points, or positions, or
	the like.
	"""


class ObjectAnnotation(_AttributeGroupAnnotation):
	"""An annotation for an object.

	Objects are used for actual DM instances.  In particular,
	every annotation of a DaCHS table is rooted in an object.
	"""


class CollectionAnnotation(AnnotationBase):
	"""A collection contains 0..n things of the same type.
	"""
	def __init__(self, name, type):
		AnnotationBase.__init__(self, name)
		self.type = type
		self.modelPrefix, _, _ = parseTypeName(type)
		self.children = []
	
	def add(self, child):
		self.children.append(child)
	
	def asSIL(self):
		return "%s: (%s) [\n  %s]\n"%(
			self.name,
			self.type,
			"\n  ".join(r.asSIL(suppressType=True) for r in self.children))

	def getVOT(self, ctx):
		ctx.addVODMLPrefix(self.modelPrefix)
		return []    # TODO: how do we want this?  is this really supposed
			# to be a table even for literals?
	

def _test():
	import doctest, common
	doctest.testmod(common)


if __name__=="__main__":
	_test()
