"""
Common code for new-style Data Model support.

DM support circles around the VODMLMeta class which can be added to
anything that maps names to values (it's expected in the annotations
attribute, which is a sequence of such objects).

When we define objects from a DM definition, we use the utils.AutoNode
infrastructure.  To have automatic DM annotation on these, there's the DMNode
class.  However, there's no need to use DMNodes to keep annotated objects.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import utils
from gavo.utils import autonode


VODML_NAME = "vo-dml"


class AnnotationBase(object):
	"""A base class for annotations.

	These always have a role name and are useless before they're adopted
	by a VODMLMeta instance (using becomeChild).

	You'll normally want to use one of the subclasses.
	"""
	_qualifiedRole = None

	def __init__(self, name):
		self.name = name

	def becomeChild(self, parent):
		"""must be called by the parent VODMLMeta when the Annotation
		is adopted.
		"""
		self._qualifiedRole = parent.qualify(self.name)

	@property
	def qualifiedRole(self):
		if self._qualifiedRole is None:
			raise TypeError("Un-adopted Annotation has no qualified role name.")
		return self._qualifiedRole


class Annotation(AnnotationBase):
	"""An annotation of an atomic value.

	These live within VODMLMeta containers and allow keeping information
	from VO-DML models including what's given there for Quantity
	(unit, ucd...).
	"""
	def __init__(self, name=None, value=None, unit=None, ucd=None):
		AnnotationBase.__init__(self, name)
		self.default, self.unit, self.ucd = value, unit, ucd


class ColumnAnnotation(AnnotationBase):
	"""An annotation of a table column.

	These live in tables and hold a reference to one of the table's
	columns.
	"""
	def __init__(self, name, columnName):
		AnnotationBase.__init__(self, name)
		self.columnName = columnName


class VODMLMeta(object):
	"""annotations for an object.

	This contains a bridge between an object's "native" attributes and
	its VO-DML properties.

	VODMLMeta is always constructed with a Model instance and
	a type name; such annotations have no roles.  Although they
	can be added later (as is required when parsing them  from
	VOTables without having the DM available), you'll usually want
	to use alternative constructors.

	These have a limited dict-like interface; you can index them, iterate
	over them (attribute names), and there's get.
	"""
	def __init__(self, model, typeName):
		self.model, self.typeName = model, typeName
		self.roles = {}

	def __getitem__(self, attrName):
		return self.roles[attrName]

	def __iter__(self):
		return iter(self.roles)

	@classmethod
	def fromRoles(cls, model, typeName, *roles):
		"""creates annotations from a model instance, and the roles
		within the DM.

		See addRole for what you can pass as  a role
		"""
		res = cls(model, typeName)
		for role in roles:
			res.addRole(role)
		return res

	@property
	def qTypeName(self):
		return self.model.name+":"+self.typeName

	def addRole(self, role):
		"""adds a role to be annotated.

		A role may be given as a plain string or as an annotation.
		"""
		if not isinstance(role, AnnotationBase):
			role = Annotation(name=role)

		if role.name is None:
				raise TypeError("Cannot add an anonymoous role")

		role.becomeChild(self)
		self.roles[role.name] = role

	def qualify(self, name):
		"""returns name as a qualified VO-DML attribute name (with model
		and type name).
		"""
		return self.qTypeName+"."+name
	
	def get(self, *args):
		return self.roles.get(*args)

	def iteritems(self):
		return self.roles.iteritems()


class DMNodeType(autonode.AutoNodeType):
	"""a type for nodes in data models.

	Essentially, these make allow to use Annotation objects to
	define autonode attributes.
	"""
	def _collectAttributes(cls):
		cls.annotations = [VODMLMeta(cls.DM_model,
			cls.DM_typeName)]
		for name in dir(cls):
			if name.startswith("_a_"):
				val = getattr(cls, name)
				if isinstance(val, AnnotationBase):
					val.name = name[3:]
					cls.annotations[0].addRole(val)
					setattr(cls, name, val.default)
				else:
					cls.annotations[0].addRole(name[3:])

		autonode.AutoNodeType._collectAttributes(cls)


class DMNode(utils.AutoNode):
	"""these are AutoNodes with additional annotation to allow serialisation
	into VO-DML instances.

	The entire magic is to add DM_model and DM_typeName class attributes
	(which have to be overridden).

	These essentially correspond to VO-DML's ObjectType instances.

	DMNodes have their "native" annotation in annotations[0]; more annotations
	could later be added as necessary.
	"""
	__metaclass__ = DMNodeType

	DM_model = None
	DM_typeName = None


# (*) We have a hen-and-egg problem with Model's data model.  Circumvent
# by emergency stand-in and later monkeypatching
class _modelStrut(object):
	name = VODML_NAME


class Model(DMNode):
	"""a data model.

	All DM annotation should have a reference to an instance of Model in
	their model attribute. This way, things like prefix, URI, and version
	can be inspected at any time.

	This could be expanded into something that would actually parse
	VO-DML and validate things.
	"""
	DM_model = _modelStrut  # to be monkeypatched; see (*)
	DM_typeName = "Model"

	_a_name = None
	_a_version = None
	_a_url = None

del _modelStrut


VODMLModel = Model(name="vo-dml", version="1.0", 
	url="http://this.needs.to/be/fixed")
# Monkeypatch (see (*))
Model.DM_model = VODMLModel
VODMLModel.annotations[0].model = VODMLModel


def getAnnotations(ob):
	"""returns a sequence of VODMLMeta objects for ob.

	If there are none, an empty sequence is returned.
	"""
	return getattr(ob, "annotations", [])
