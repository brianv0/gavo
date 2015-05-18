"""
Common code for new-style Data Model support.

DM support circles around the Annotation class which can be added to
anything that maps names to values (it's expected in the annotations
attribute).

When we define objects from a DM definition, we use the utils.AutoNode
infrastructure.  To have automatic DM annotation on these, there's the DMNode
class.  However, there's no need to use DMNodes to keep annotated objects.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import utils


class Annotations(object):
	"""annotations for an object.

	This contains a bridge between an object's "native" attributes and
	its VO-DML properties.
	"""
	def __init__(self):
		pass
	
	@classmethod
	def fromRoles(cls, model, typeName, *roleNames):
		"""creates annotations from a model instance, and the names
		of the DM roles present in parent.
		"""
		res = cls()
		res.model = model
		res.typeName = typeName
		res.roleNames = roleNames
		return res

	@property
	def qTypeName(self):
		return self.model.name+":"+self.typeName

	def qualify(self, name):
		"""returns name as a qualified VO-DML attribute name (with model
		and type name).
		"""
		return self.qTypeName+"."+name


class DMNode(utils.AutoNode):
	"""these are AutoNodes with additional annotation to allow serialisation
	into VO-DML instances.

	The entire magic is to add DM_model and DM_typeName class attributes.
	"""
	def _setupNode(self):
		self.annotations = Annotations.fromRoles(self.DM_model, 
			self.DM_typeName,
			*tuple(a[0] for a in self._nodeAttrs))
		self._setupNodeNext(DMNode)


class Model(DMNode):
	"""a data model.

	All DM annotation should have a reference to an instance of Model in
	their model attribute. This way, things like prefix, URI, and version
	can be inspected at any time.

	This could be expanded into something that would actually parse
	VO-DML and validate things.
	"""
	DM_model = None  # filled in when we can define model
	DM_typeName = "Model"

	_a_name = None
	_a_version = None
	_a_url = None


VODMLModel = Model(name="vo-dml", version="1.0", 
	url="http://this.needs.to/be/fixed")
# Monkeypatch to fix hen-and-egg-problem
Model.DM_model = VODMLModel
VODMLModel.annotations.model = VODMLModel


def getAnnotations(el):
	"""returns the annotations on el.

	If there are none, None is returned.
	"""
	return getattr(el, "annotations", None)
