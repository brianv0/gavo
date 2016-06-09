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


from gavo import votable
from gavo.votable import V


VODML_NAME = "vo-dml"


class AnnotationBase(object):
	"""A base class for of structs.

	Basically, these are pairs of a role name and something else, which
	depends on the actual subclass (e.g., an atomic value, a reference,
	a sequence of key-value pairs, a sequence of other objects, ...).

	They have a method getVOT(ctx, parent) -> xmlstan, which, using a
	votable.Context ctx, will return mapping-document conformant VOTable
	xmlstand.

	Use asSIL() to retrieve a simple string representation.

	Compund annotations (sequences, key-value pairs) should use
	add(thing) to build themselves up.

	AnnotationBase is abstract and doesn't implement some of these methods.
	"""
	_qualifiedRole = None

	def __init__(self, name):
		self.name = name

	def getVOT(self, ctx, parent):
		raise NotImplementedError("AnnotationBase cannot be serialised."
			"  Use one of its subclasses.")

	def asSIL(self):
		raise NotImplementedError("AnnotationBase cannot be serialised."
			"  Use one of its subclasses.")

	def add(self, thing):
		raise ValueError(
			"%s is not a compound annotation."%self.__class__.__name__)


class AtomicAnnotation(AnnotationBase):
	"""An annotation of an atomic value.

	These live within VODMLMeta containers and allow keeping information
	from VO-DML models including what's given there for Quantity
	(unit, ucd...).
	"""
	def __init__(self, name=None, value=None, unit=None, ucd=None):
		AnnotationBase.__init__(self, name)
		self.value, self.unit, self.ucd = value, unit, ucd

	def getTree(self, ctx, parent):
		ob = getattr(parent, self.name)
		attrs = votable.guessParamAttrsForValue(ob)
		attrs.update({
			"unit": self.unit,
			"ucd": self.ucd})

		param = V.PARAM(name=self.name,
			id=ctx.getOrMakeIdFor(ob), **attrs)[
				V.VODML[V.ROLE[self.qualifiedRole]]]
		votable.serializeToParam(param, ob)
		return param

	def asSIL(self):
		return "%s: %s"%(self.name, self.value.asSIL())


class _AttributeGroupAnnotation(AnnotationBase):
	"""An internal base class for DatatypeAnnotation and ObjectAnnotation.
	"""
	def __init__(self, name, type):
		AnnotationBase.__init__(self, name)
		self.type = type
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


class DatatypeAnnotation(_AttributeGroupAnnotation):
	"""An annotation for a datatype.

	Datatypes are essentially simple groups of attributes; they are used
	*within* objects (e.g., to group photometry points, or positions, or
	the like.
	"""


class ObjectAnnotation(_AttributeGroupAnnotation):
	"""An annotation for an object.

	Objects are used for actual DM instances.  In particular,
	every annotation is rooted in an object.
	"""


class CollectionAnnotation(AnnotationBase):
	"""A collection contains 0..n things of the same type.
	"""
	def __init__(self, name, type):
		AnnotationBase.__init__(self, name)
		self.type = type
		self.children = []
	
	def add(self, child):
		self.children.append(child)
	
	def asSIL(self):
		return "%s: (%s) [\n  %s]\n"%(
			self.name,
			self.type,
			"\n  ".join(r.asSIL(suppressType=True) for r in self.children))
